#include "DroidService.h"

#include <chrono>

#include "Link.h"
#include "Settings.h"

namespace app {

DroidService droidService;

static const uint32_t kHeartbeatMs = 30000;
static const uint32_t kRetryMs = 5000;  // reconnect interval while disconnected

bool validMac(const String& m) {
  if (m.length() != 17) return false;
  for (int i = 0; i < 17; i++) {
    char c = m[i];
    if (i % 3 == 2) {
      if (c != ':') return false;
    } else if (!isxdigit((unsigned char)c)) {
      return false;
    }
  }
  return true;
}

bool DroidService::begin() {
  mac_ = settings.get("droid_mac");
  mac_.trim();
  mac_.toUpperCase();
  alias_ = settings.get("droid_alias", "droid");
  type_ = settings.get("droid_type", "r2");
  personality_ = settings.get("personality", "resistance_blue");

  if (!validMac(mac_)) return false;
  const astromech::Personality* p = astromech::findPersonality(personality_.c_str());
  if (type_ == "bb") {
    bb_ = new astromech::BBUnit(mac_.c_str(), p);
    base_ = bb_;
  } else {
    r2_ = new astromech::R2Unit(mac_.c_str(), p);
    base_ = r2_;
  }
  return true;
}

long DroidService::lastSeenMsAgo() const {
  return ever_seen_ ? (long)(millis() - last_seen_ms_) : -1;
}

void DroidService::markAvailable(bool ok) {
  if (ok) {
    last_seen_ms_ = millis();
    ever_seen_ = true;
  }
  if (ok != available_) {
    available_ = ok;
    if (state_cb_) state_cb_(ok);
  }
}

bool DroidService::connectNow(uint32_t timeout_ms, uint32_t* elapsed_ms) {
  std::unique_lock<std::timed_mutex> lock(ble_mutex_, std::defer_lock);
  if (!lock.try_lock_for(std::chrono::seconds(45))) {
    if (elapsed_ms) *elapsed_ms = 0;
    return false;
  }
  auto_connect_ = true;
  const uint32_t t0 = millis();
  bool ok = base_->connect(timeout_ms);
  if (elapsed_ms) *elapsed_ms = millis() - t0;
  markAvailable(ok);
  return ok;
}

bool DroidService::ensureConnected(uint32_t timeout_ms) {
  if (base_->isConnected()) return true;
  uint32_t ms;
  return connectNow(timeout_ms, &ms);
}

void DroidService::disconnect() {
  auto_connect_ = false;
  std::lock_guard<std::timed_mutex> lock(ble_mutex_);
  base_->disconnect();
  markAvailable(false);
}

bool DroidService::checkAlive() {
  std::lock_guard<std::timed_mutex> lock(ble_mutex_);
  bool ok = base_->checkAlive();
  markAvailable(ok);
  return ok;
}

void DroidService::taskEntry(void* arg) { static_cast<DroidService*>(arg)->heartbeatLoop(); }

void DroidService::startHeartbeat() {
  if (base_) xTaskCreate(taskEntry, "heartbeat", 8192, this, 1, nullptr);
}

void DroidService::heartbeatLoop() {
  uint32_t last_check = 0;
  bool first = true;
  for (;;) {
    // Notice a dropped link promptly; reconnect/ping only every kHeartbeatMs.
    if (available_ && !base_->isConnected()) markAvailable(false);
    const uint32_t interval = base_->isConnected() ? kHeartbeatMs : kRetryMs;
    if (auto_connect_ && (first || millis() - last_check >= interval)) {
      first = false;
      last_check = millis();
      if (base_->isConnected() && base_->msSinceLastSuccess() < kHeartbeatMs) {
        markAvailable(true);  // a command succeeded recently
      } else if (base_->isConnected()) {
        checkAlive();
      } else {
        uint32_t ms;
        connectNow(15000, &ms);
        last_check = millis();
      }
    }
    delay(1000);
  }
}

void DroidService::diagnose(JsonObject out) {
  out["address"] = mac_;
  std::unique_lock<std::timed_mutex> lock(ble_mutex_, std::defer_lock);
  if (!lock.try_lock_for(std::chrono::seconds(45))) {
    out["error"] = "busy with another connection attempt";
    return;
  }
  if (base_->isConnected()) {
    out["already_connected"] = true;
    const uint32_t t0 = millis();
    bool ok = base_->ping();
    out["ping_ok"] = ok;
    out["ping_ms"] = millis() - t0;
    markAvailable(ok);
    return;
  }
  out["already_connected"] = false;

  // Step 1: is the droid advertising? A connected or sleeping droid is not.
  NimBLEScan* scan = NimBLEDevice::getScan();
  scan->setActiveScan(true);
  NimBLEScanResults results = scan->getResults(4000, false);
  bool found = false;
  JsonArray others = out["other_droids"].to<JsonArray>();
  for (int i = 0; i < results.getCount(); i++) {
    const NimBLEAdvertisedDevice* d = results.getDevice(i);
    String addr = d->getAddress().toString().c_str();
    if (addr.equalsIgnoreCase(mac_)) {
      found = true;
      out["rssi"] = d->getRSSI();
      out["address_type"] = d->getAddress().getType();
    } else if (d->getName() == "DROID" && others.size() < 5) {
      JsonObject o = others.add<JsonObject>();
      o["address"] = addr;
      o["rssi"] = d->getRSSI();
    }
  }
  out["advertising"] = found;
  out["ble_devices_seen"] = results.getCount();
  scan->clearResults();

  // Step 2: connect and ping, as the heartbeat would.
  uint32_t t0 = millis();
  bool ok = base_->connect(15000);
  out["connect_ok"] = ok;
  out["connect_ms"] = millis() - t0;
  if (ok) {
    t0 = millis();
    bool pong = base_->ping();
    out["ping_ok"] = pong;
    out["ping_ms"] = millis() - t0;
    ok = pong;
  }
  markAvailable(ok);
}

}  // namespace app
