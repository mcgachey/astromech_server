#include "Link.h"

#include <stdarg.h>

namespace app {

Link serialLink;

static const size_t kMaxLine = 1024;

void Link::begin(unsigned long baud) {
  Serial.setRxBufferSize(2048);
  Serial.begin(baud);
  buf_.reserve(256);
}

Link::ReadResult Link::readLine(String& line) {
  while (Serial.available() > 0) {
    int c = Serial.read();
    if (c < 0) break;
    if (c == '\n') {
      bool was_overflow = overflow_;
      overflow_ = false;
      if (was_overflow) {
        buf_ = "";
        return kOverflow;
      }
      line = buf_;
      buf_ = "";
      line.trim();
      if (line.length() == 0) continue;
      return kLine;
    }
    if (overflow_) continue;
    if (buf_.length() >= kMaxLine) {
      overflow_ = true;
      buf_ = "";
      continue;
    }
    buf_ += (char)c;
  }
  return kNothing;
}

void Link::send(const JsonDocument& doc) {
  String s;
  serializeJson(doc, s);
  s += '\n';
  std::lock_guard<std::mutex> lock(tx_);
  Serial.write(reinterpret_cast<const uint8_t*>(s.c_str()), s.length());
}

void Link::event(const char* name, JsonVariantConst data) {
  JsonDocument doc;
  doc["event"] = name;
  if (!data.isNull()) doc["data"] = data;
  send(doc);
}

void Link::log(const char* fmt, ...) {
  char msg[160];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(msg, sizeof(msg), fmt, ap);
  va_end(ap);
  JsonDocument doc;
  doc["event"] = "log";
  doc["data"]["msg"] = (const char*)msg;
  send(doc);
}

}  // namespace app
