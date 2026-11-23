#pragma once

// Owns the single droid this board controls: connection, heartbeat and
// availability tracking. Command handlers use it via droidService.

#include <Arduino.h>
#include <ArduinoJson.h>

#include <mutex>

#include "BBUnit.h"
#include "R2Unit.h"

namespace app {

class DroidService {
 public:
  // Reads settings and builds the droid object. Returns false (and stays
  // unconfigured) if the address is missing or malformed.
  bool begin();
  // Starts the heartbeat task: connects, then pings every 30 s and reconnects.
  void startHeartbeat();

  bool configured() const { return base_ != nullptr; }
  bool isR2() const { return r2_ != nullptr; }
  astromech::Astromech* droid() { return base_; }
  astromech::R2Unit* r2() { return r2_; }
  astromech::BBUnit* bb() { return bb_; }

  const String& alias() const { return alias_; }
  const String& mac() const { return mac_; }
  const String& type() const { return type_; }
  const String& personalityName() const { return personality_; }

  // Last known availability (updated by the heartbeat and by commands).
  bool available() const { return available_; }
  // Milliseconds since the droid last answered; -1 if never.
  long lastSeenMsAgo() const;

  // Connect if not already connected. False if the droid can't be reached.
  bool ensureConnected(uint32_t timeout_ms = 10000);
  // Explicit connect; reports how long the attempt took.
  bool connectNow(uint32_t timeout_ms, uint32_t* elapsed_ms);
  void disconnect();
  bool checkAlive();

  // While false the heartbeat does not (re)connect, e.g. so a stock remote can
  // take over. Set by disconnect(), cleared by connectNow().
  void setAutoConnect(bool on) { auto_connect_ = on; }

  // Scan for the droid, connect and ping, filling `out`. Blocks up to ~45 s.
  void diagnose(JsonObject out);

  // Called from the heartbeat/command tasks when availability changes.
  void onStateChange(void (*cb)(bool available)) { state_cb_ = cb; }

 private:
  static void taskEntry(void* arg);
  void heartbeatLoop();
  void markAvailable(bool ok);

  astromech::Astromech* base_ = nullptr;
  astromech::R2Unit* r2_ = nullptr;
  astromech::BBUnit* bb_ = nullptr;
  String alias_, mac_, type_, personality_;
  volatile bool available_ = false;
  volatile bool auto_connect_ = true;
  volatile uint32_t last_seen_ms_ = 0;
  volatile bool ever_seen_ = false;
  void (*state_cb_)(bool) = nullptr;
  // Serialises connect/ping attempts and the diagnostic (which also scans).
  std::timed_mutex ble_mutex_;
};

extern DroidService droidService;

bool validMac(const String& m);

}  // namespace app
