#pragma once

// Newline-delimited JSON over the USB serial port. One JSON object per line.
// Lines that do not start with '{' are ignored on input, and nothing but JSON
// lines is ever written on output (log text goes out as "log" events), so ROM
// boot messages and stray bytes cannot corrupt the stream.

#include <Arduino.h>
#include <ArduinoJson.h>

#include <mutex>

namespace app {

class Link {
 public:
  enum ReadResult { kNothing, kLine, kOverflow };

  void begin(unsigned long baud = 115200);
  // Non-blocking. kLine: a complete line (no newline) is in `line`.
  // kOverflow: an over-long line was discarded.
  ReadResult readLine(String& line);

  // Thread-safe: writes the document as a single line.
  void send(const JsonDocument& doc);
  // {"event": name, "data": data}
  void event(const char* name, JsonVariantConst data = JsonVariantConst());
  // {"event": "log", "data": {"msg": ...}}
  void log(const char* fmt, ...) __attribute__((format(printf, 2, 3)));

 private:
  std::mutex tx_;
  String buf_;
  bool overflow_ = false;
};

extern Link serialLink;

}  // namespace app
