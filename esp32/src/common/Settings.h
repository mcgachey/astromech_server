#pragma once

// Persistent key/value settings in NVS (survive reflashing the app, cleared by
// "factory reset" in the web UI). Keys are at most 15 characters.

#include <Arduino.h>
#include <Preferences.h>

namespace app {

class Settings {
 public:
  void begin();
  String get(const char* key, const char* def = "");
  long getInt(const char* key, long def);
  void put(const char* key, const String& value);
  void clear();

 private:
  Preferences prefs_;
};

extern Settings settings;

}  // namespace app
