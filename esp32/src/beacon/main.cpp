// Beacon board: broadcasts the keep-awake beacon, and is configured by a master
// over USB serial (docs/PROTOCOL.md). No Wi-Fi, no network.
//
// It starts broadcasting from its saved configuration at power-on, with or
// without a master attached. Default is the same beacon as the Raspberry Pi
// server: a "silent" personality beacon, which keeps nearby droids awake and
// stops them reacting to each other.
#include <Arduino.h>

#include "Beacon.h"
#include "Commands.h"
#include "Link.h"
#include "Settings.h"

using namespace app;

static astromech::Beacon beacon;
static uint32_t g_restarts = 0;
static bool g_stopped = false;  // stopped by the master; the watchdog respects it
static String g_kind;
static long g_location_id = 4;

static astromech::protocol::BeaconPayload currentPayload() {
  using namespace astromech::protocol;
  return g_kind == "location" ? locationBeacon((uint8_t)g_location_id)
                              : personalityBeacon(Affiliation::Silent, kChipRSeriesDefault);
}

static void loadConfig() {
  g_kind = settings.get("beacon_kind", "silent");
  if (g_kind != "location") g_kind = "silent";
  g_location_id = settings.getInt("location_id", 4);
}

static void fillStatus(JsonObject o) {
  o["advertising"] = beacon.isAdvertising();
  o["kind"] = g_kind;
  if (g_kind == "location") o["location_id"] = g_location_id;
  o["stopped_by_master"] = g_stopped;
  o["running_ms"] = beacon.msSinceStarted();
  o["watchdog_restarts"] = g_restarts;
}

static void cmdStatus(Request& r) {
  fillStatus(r.result());
  r.ok();
}

static void cmdGetConfig(Request& r) {
  r.result()["kind"] = g_kind;
  r.result()["location_id"] = g_location_id;
  r.ok();
}

// args: kind ("silent"|"location"), location_id (0-255, location only),
//       persist (bool, default true). Applies immediately.
static void cmdSetBeacon(Request& r) {
  JsonObjectConst a = r.args();
  String kind = a["kind"].isNull() ? g_kind : String(a["kind"] | "");
  if (kind != "silent" && kind != "location") return r.fail(err::kInvalidArgument, "kind must be silent or location");
  long loc = g_location_id;
  if (!a["location_id"].isNull()) {
    if (!a["location_id"].is<int>()) return r.fail(err::kInvalidArgument, "location_id must be an integer");
    loc = a["location_id"];
    if (loc < 0 || loc > 255) return r.fail(err::kInvalidArgument, "location_id must be 0-255");
  }
  g_kind = kind;
  g_location_id = loc;
  if (a["persist"] | true) {
    settings.put("beacon_kind", g_kind);
    settings.put("location_id", String(g_location_id));
  }
  g_stopped = false;
  if (!beacon.start(currentPayload())) return r.fail(err::kInternal, "failed to start advertising");
  fillStatus(r.result());
  r.ok();
}

static void cmdStopBeacon(Request& r) {
  g_stopped = true;
  beacon.stop();
  fillStatus(r.result());
  r.ok();
}

static void cmdStartBeacon(Request& r) {
  g_stopped = false;
  if (!beacon.start(currentPayload())) return r.fail(err::kInternal, "failed to start advertising");
  fillStatus(r.result());
  r.ok();
}

static const CommandServer::Command kCommands[] = {
    {"hello", cmdHello, false},
    {"ping", cmdPing, false},
    {"reboot", cmdReboot, false},
    {"factory_reset", cmdFactoryReset, false},
    {"status", cmdStatus, false},
    {"get_config", cmdGetConfig, false},
    {"set_beacon", cmdSetBeacon, false},
    {"stop_beacon", cmdStopBeacon, false},
    {"start_beacon", cmdStartBeacon, false},
};

static CommandServer server(kCommands, sizeof(kCommands) / sizeof(kCommands[0]));

void setup() {
  serialLink.begin();
  settings.begin();
  setRole("beacon");
  astromech::initBle("astromech-beacon");
  loadConfig();
  beacon.start(currentPayload());
  server.begin();
  announceBoot();
}

void loop() {
  server.poll();
  // Watchdog: restart advertising if it ever stops. The analogue of the Pi
  // server's restart-on-crash loop.
  static uint32_t last = 0;
  if (millis() - last >= 5000) {
    last = millis();
    if (!g_stopped && !beacon.isAdvertising()) {
      g_restarts++;
      serialLink.log("advertising stopped, restarting");
      beacon.ensureRunning();
    }
  }
  delay(2);
}
