#include "Settings.h"

namespace app {

Settings settings;

static const char* const kNamespace = "astromech";

void Settings::begin() { prefs_.begin(kNamespace, false); }

String Settings::get(const char* key, const char* def) {
  return prefs_.isKey(key) ? prefs_.getString(key, def) : String(def);
}

long Settings::getInt(const char* key, long def) {
  String v = get(key, "");
  if (v.length() == 0) return def;
  return v.toInt();
}

void Settings::put(const char* key, const String& value) { prefs_.putString(key, value); }

void Settings::clear() { prefs_.clear(); }

}  // namespace app
