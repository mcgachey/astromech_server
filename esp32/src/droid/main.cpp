// Droid controller board: connects to exactly one droid over BLE and is driven
// by a master over USB serial (docs/PROTOCOL.md). No Wi-Fi, no network.
#include <Arduino.h>

#include "Commands.h"
#include "DroidService.h"
#include "Link.h"
#include "Settings.h"

using namespace app;

// ---- helpers ---------------------------------------------------------------

// Common checks for commands that talk to the droid. Replies and returns false
// if the droid can't be used.
static bool needDroid(Request& r) {
  if (!droidService.configured()) {
    r.fail(err::kNotConfigured, "no droid address configured (set_config, then reboot)");
    return false;
  }
  if (!droidService.ensureConnected()) {
    r.fail(err::kDroidUnavailable, "could not connect to the droid (awake? remote off? in range?)");
    return false;
  }
  return true;
}

static bool needR2(Request& r) {
  if (!droidService.isR2()) {
    r.fail(err::kUnsupported, "only supported on R-series droids");
    return false;
  }
  return true;
}

static void unavailable(Request& r) { r.fail(err::kDroidUnavailable, "droid did not accept the command"); }

// Python's asyncio.gather(a, b): run lookAround() in its own task while the
// caller does something else. The library's mutex serialises the BLE writes.
struct ConcurrentHead {
  SemaphoreHandle_t done;
  bool ok;
};

static void headTask(void* arg) {
  ConcurrentHead* c = static_cast<ConcurrentHead*>(arg);
  c->ok = droidService.r2()->lookAround();
  xSemaphoreGive(c->done);
  vTaskDelete(nullptr);
}

static bool startHead(ConcurrentHead& c) {
  c.ok = false;
  c.done = xSemaphoreCreateBinary();
  if (!c.done) return false;
  if (xTaskCreate(headTask, "head", 8192, &c, 1, nullptr) != pdPASS) {
    vSemaphoreDelete(c.done);
    return false;
  }
  return true;
}

static bool finishHead(ConcurrentHead& c) {
  xSemaphoreTake(c.done, portMAX_DELAY);
  vSemaphoreDelete(c.done);
  return c.ok;
}

// ---- inline commands (fast) -------------------------------------------------

static void cmdStatus(Request& r) {
  DroidService& d = droidService;
  JsonObject o = r.result();
  o["configured"] = d.configured();
  if (d.configured()) {
    o["alias"] = d.alias();
    o["address"] = d.mac();
    o["type"] = d.type();
    o["personality"] = d.personalityName();
    o["connected"] = d.droid()->isConnected();
    long ago = d.lastSeenMsAgo();
    if (ago >= 0) o["last_seen_ms_ago"] = ago;
    else o["last_seen_ms_ago"] = nullptr;
  }
  o["free_heap"] = ESP.getFreeHeap();
  r.ok();
}

static void cmdGetConfig(Request& r) {
  JsonObject o = r.result();
  o["alias"] = settings.get("droid_alias", "droid");
  o["address"] = settings.get("droid_mac");
  o["type"] = settings.get("droid_type", "r2");
  o["personality"] = settings.get("personality", "resistance_blue");
  JsonArray names = o["available_personalities"].to<JsonArray>();
  for (size_t i = 0; i < astromech::kPersonalityCount; i++) names.add(astromech::kPersonalityNames[i]);
  r.ok();
}

// Validates everything before storing anything. Applies on next boot.
static void cmdSetConfig(Request& r) {
  JsonObjectConst a = r.args();
  String alias, mac, type, personality;
  if (!a["alias"].isNull()) {
    alias = a["alias"] | "";
    if (alias.length() == 0 || alias.length() > 32) return r.fail(err::kInvalidArgument, "alias must be 1-32 characters");
  }
  if (!a["address"].isNull()) {
    mac = a["address"] | "";
    mac.trim();
    mac.toUpperCase();
    if (!validMac(mac)) return r.fail(err::kInvalidArgument, "address must look like AA:BB:CC:DD:EE:FF");
  }
  if (!a["type"].isNull()) {
    type = a["type"] | "";
    if (type != "r2" && type != "bb") return r.fail(err::kInvalidArgument, "type must be r2 or bb");
  }
  if (!a["personality"].isNull()) {
    personality = a["personality"] | "";
    if (!astromech::findPersonality(personality.c_str())) return r.fail(err::kInvalidArgument, "unknown personality");
  }
  if (alias.length()) settings.put("droid_alias", alias);
  if (mac.length()) settings.put("droid_mac", mac);
  if (type.length()) settings.put("droid_type", type);
  if (personality.length()) settings.put("personality", personality);
  r.result()["restart_required"] = true;
  r.ok();
}

static void cmdSounds(Request& r) {
  const astromech::Personality* p = droidService.configured() ? droidService.droid()->personality() : nullptr;
  if (!p) return r.fail(err::kNotConfigured, "no personality available");
  JsonObject o = r.result();
  o["personality"] = p->name;
  JsonArray list = o["sounds"].to<JsonArray>();
  for (size_t i = 0; i < p->count; i++) {
    JsonObject s = list.add<JsonObject>();
    s["index"] = i;
    s["group"] = p->sounds[i].group;
    s["sound"] = p->sounds[i].sound;
    s["ms"] = p->sounds[i].ms;
  }
  r.ok();
}

// ---- queued commands (talk to the droid; may block) --------------------------

static void cmdConnect(Request& r) {
  if (!droidService.configured()) return r.fail(err::kNotConfigured, "no droid address configured");
  uint32_t ms = 0;
  bool ok = droidService.connectNow(15000, &ms);
  if (!ok) return r.fail(err::kDroidUnavailable, "connect failed after " + String(ms) + " ms");
  r.result()["connect_ms"] = ms;
  r.ok();
}

static void cmdDisconnect(Request& r) {
  if (!droidService.configured()) return r.fail(err::kNotConfigured, "no droid address configured");
  droidService.disconnect();
  r.ok();
}

static void cmdCheck(Request& r) {
  if (!droidService.configured()) return r.fail(err::kNotConfigured, "no droid address configured");
  bool ok = droidService.checkAlive();
  r.result()["available"] = ok;
  r.ok();
}

static void cmdDiagnose(Request& r) {
  if (!droidService.configured()) return r.fail(err::kNotConfigured, "no droid address configured");
  droidService.diagnose(r.result());
  r.ok();
}

// args: sound (index, required); turn_head (bool, R-series); wait (bool)
static void cmdBeep(Request& r) {
  JsonObjectConst a = r.args();
  if (!droidService.configured()) return r.fail(err::kNotConfigured, "no droid address configured");
  const astromech::Personality* p = droidService.droid()->personality();
  if (!p) return r.fail(err::kNotConfigured, "droid has no personality");
  if (!a["sound"].is<int>()) return r.fail(err::kInvalidArgument, "sound (integer index) is required");
  int idx = a["sound"];
  if (idx < 0 || (size_t)idx >= p->count)
    return r.fail(err::kInvalidArgument, "sound out of range (0-" + String(p->count - 1) + ")");
  bool turn_head = a["turn_head"] | false;
  bool wait = a["wait"] | false;
  if (turn_head && !needR2(r)) return;
  if (!needDroid(r)) return;

  const astromech::Sound& sound = p->sounds[idx];
  bool ok;
  if (turn_head) {
    ConcurrentHead head;
    bool started = startHead(head);
    ok = droidService.droid()->play(sound, wait);
    ok = (started ? finishHead(head) : false) && ok;
  } else {
    ok = droidService.droid()->play(sound, wait);
  }
  if (!ok) return unavailable(r);
  r.result()["ms"] = sound.ms;
  r.result()["turn_head"] = turn_head;
  r.ok();
}

// Plays one clip by raw group:sound number, ignoring the personality. Used to catalogue a
// personality chip's sounds, so the numbers are only range-checked as bytes.
static void cmdPlay(Request& r) {
  JsonObjectConst a = r.args();
  if (!a["group"].is<int>() || !a["sound"].is<int>())
    return r.fail(err::kInvalidArgument, "group and sound (integers) are required");
  int group = a["group"], sound = a["sound"];
  if (group < 0 || group > 255) return r.fail(err::kInvalidArgument, "group must be 0-255");
  if (sound < 0 || sound > 255) return r.fail(err::kInvalidArgument, "sound must be 0-255");
  if (!needDroid(r)) return;
  astromech::Sound clip = {(uint8_t)group, (uint8_t)sound, 0};
  if (!droidService.droid()->play(clip, false)) return unavailable(r);
  r.ok();
}

static void cmdVolume(Request& r) {
  JsonObjectConst a = r.args();
  if (!a["level"].is<int>()) return r.fail(err::kInvalidArgument, "level (0-31) is required");
  int level = a["level"];
  if (level < 0 || level > 31) return r.fail(err::kInvalidArgument, "level must be 0-31");
  if (!needDroid(r)) return;
  if (!droidService.droid()->setVolume((uint8_t)level)) return unavailable(r);
  r.ok();
}

static void cmdCenterHead(Request& r) {
  if (!droidService.configured()) return r.fail(err::kNotConfigured, "no droid address configured");
  if (!needR2(r) || !needDroid(r)) return;
  if (!droidService.r2()->centerHead()) return unavailable(r);
  r.ok();
}

static void cmdLookAround(Request& r) {
  if (!droidService.configured()) return r.fail(err::kNotConfigured, "no droid address configured");
  if (!needR2(r) || !needDroid(r)) return;
  if (!droidService.r2()->lookAround()) return unavailable(r);
  r.ok();
}

// Center head, look around while playing the first 7 sounds, center head.
// Moves the head only; never the wheels.
static void cmdDemo(Request& r) {
  if (!droidService.configured()) return r.fail(err::kNotConfigured, "no droid address configured");
  if (!needR2(r) || !needDroid(r)) return;
  const astromech::Personality* p = droidService.droid()->personality();
  if (!p) return r.fail(err::kNotConfigured, "droid has no personality");
  if (!droidService.r2()->centerHead()) return unavailable(r);
  ConcurrentHead head;
  if (!startHead(head)) return r.fail(err::kInternal, "out of resources");
  bool audio_ok = true;
  const size_t n = min((size_t)7, p->count);
  for (size_t i = 0; i < n && audio_ok; i++) audio_ok = droidService.droid()->play(p->sounds[i], true);
  bool head_ok = finishHead(head);
  if (!audio_ok || !head_ok || !droidService.r2()->centerHead()) return unavailable(r);
  r.ok();
}

// Wheel movement. args: direction (forward|backward|spin_cw|spin_ccw|turn_cw|turn_ccw),
// ms (1-kMaxMoveMs, required), speed (1-255, optional; droid default if absent).
// BB units support forward/backward only. Blocks for `ms`; `stop` can interrupt.
static const uint32_t kMaxMoveMs = 5000;

static void cmdMove(Request& r) {
  JsonObjectConst a = r.args();
  if (!droidService.configured()) return r.fail(err::kNotConfigured, "no droid address configured");
  if (!a["direction"].is<const char*>()) return r.fail(err::kInvalidArgument, "direction is required");
  String dir = a["direction"].as<const char*>();
  if (!a["ms"].is<int>()) return r.fail(err::kInvalidArgument, "ms (duration) is required");
  int ms = a["ms"];
  if (ms < 1 || ms > (int)kMaxMoveMs) return r.fail(err::kInvalidArgument, "ms must be 1-" + String(kMaxMoveMs));
  int speed = astromech::kDefault;
  if (!a["speed"].isNull()) {
    if (!a["speed"].is<int>()) return r.fail(err::kInvalidArgument, "speed must be an integer 1-255");
    speed = a["speed"];
    if (speed < 1 || speed > 255) return r.fail(err::kInvalidArgument, "speed must be 1-255");
  }
  const bool fwd = dir == "forward", back = dir == "backward";
  if (!fwd && !back && !(dir == "spin_cw" || dir == "spin_ccw" || dir == "turn_cw" || dir == "turn_ccw"))
    return r.fail(err::kInvalidArgument, "direction must be forward, backward, spin_cw, spin_ccw, turn_cw or turn_ccw");
  if (!fwd && !back && !needR2(r)) return;
  if (!needDroid(r)) return;

  bool ok;
  if (droidService.isR2()) {
    astromech::R2Unit* d = droidService.r2();
    if (fwd) ok = d->moveForward(ms, speed);
    else if (back) ok = d->moveBackward(ms, speed);
    else if (dir == "spin_cw") ok = d->spinClockwise(ms, speed);
    else if (dir == "spin_ccw") ok = d->spinCounterClockwise(ms, speed);
    else if (dir == "turn_cw") ok = d->turnClockwise(ms, speed);
    else ok = d->turnCounterClockwise(ms, speed);
  } else {
    astromech::BBUnit* d = droidService.bb();
    ok = fwd ? d->moveForward(ms, speed) : d->moveBackward(ms, speed);
  }
  if (!ok) return unavailable(r);
  r.result()["ms"] = ms;
  r.ok();
}

// Immediate wheel stop. Inline so it is answered while a `move` is running.
static void cmdStop(Request& r) {
  if (!droidService.configured()) return r.fail(err::kNotConfigured, "no droid address configured");
  if (!droidService.droid()->isConnected()) return r.fail(err::kDroidUnavailable, "droid is not connected");
  if (!droidService.droid()->stop()) return unavailable(r);
  r.ok();
}

static const CommandServer::Command kCommands[] = {
    {"hello", cmdHello, false},
    {"ping", cmdPing, false},
    {"reboot", cmdReboot, false},
    {"factory_reset", cmdFactoryReset, false},
    {"status", cmdStatus, false},
    {"get_config", cmdGetConfig, false},
    {"set_config", cmdSetConfig, false},
    {"sounds", cmdSounds, false},
    {"stop", cmdStop, false},
    {"connect", cmdConnect, true},
    {"disconnect", cmdDisconnect, true},
    {"check", cmdCheck, true},
    {"diagnose", cmdDiagnose, true},
    {"beep", cmdBeep, true},
    {"play", cmdPlay, true},
    {"volume", cmdVolume, true},
    {"center_head", cmdCenterHead, true},
    {"look_around", cmdLookAround, true},
    {"demo", cmdDemo, true},
    {"move", cmdMove, true},
};

static CommandServer server(kCommands, sizeof(kCommands) / sizeof(kCommands[0]));

static void onDroidState(bool available) {
  JsonDocument d;
  d["connected"] = available;
  serialLink.event("droid_state", d);
}

void setup() {
  serialLink.begin();
  settings.begin();
  setRole("droid");
  astromech::initBle("astromech-droid");
  droidService.begin();
  droidService.onStateChange(onDroidState);
  server.begin();
  announceBoot();
  droidService.startHeartbeat();
}

void loop() {
  server.poll();
  delay(2);
}
