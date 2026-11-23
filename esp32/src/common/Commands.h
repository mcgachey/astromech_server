#pragma once

// Request parsing, dispatch and the commands shared by both firmwares
// (hello, ping, reboot, factory_reset). See docs/PROTOCOL.md.

#include <Arduino.h>
#include <ArduinoJson.h>

namespace app {

// Error codes (the "code" field of an error response).
namespace err {
static const char* const kBadJson = "bad_json";
static const char* const kBadRequest = "bad_request";
static const char* const kUnknownCommand = "unknown_command";
static const char* const kInvalidArgument = "invalid_argument";
static const char* const kBusy = "busy";
static const char* const kNotConfigured = "not_configured";
static const char* const kDroidUnavailable = "droid_unavailable";
static const char* const kUnsupported = "unsupported";
static const char* const kInternal = "internal";
}  // namespace err

class Request {
 public:
  explicit Request(JsonDocument&& doc) : doc_(static_cast<JsonDocument&&>(doc)) {}

  const char* cmd() const { return doc_["cmd"] | ""; }
  // Empty (null) object if the request had no "args".
  JsonObjectConst args() const;
  // Fill this, then call ok().
  JsonObject result();
  void ok();
  void fail(const char* code, const String& message);
  bool replied() const { return replied_; }

 private:
  void send(bool ok);
  JsonDocument doc_;
  JsonDocument result_;
  bool replied_ = false;
};

class CommandServer {
 public:
  typedef void (*Handler)(Request&);
  // queued=true: run on the worker task (for commands that block for a while);
  // queued=false: run inline, must be fast.
  struct Command {
    const char* name;
    Handler fn;
    bool queued;
  };

  CommandServer(const Command* table, size_t count) : table_(table), count_(count) {}
  void begin();  // starts the worker task
  void poll();   // call often from loop(); reads and dispatches requests

 private:
  void dispatch(const String& line);
  void run(Request& req, Handler fn);
  static void workerEntry(void* arg);

  const Command* table_;
  size_t count_;
  void* queue_ = nullptr;  // QueueHandle_t
};

// Set once at startup ("droid" or "beacon"); reported by hello.
void setRole(const char* role);
void fillHello(JsonObject out);
// Sends the unsolicited {"event":"boot"} message.
void announceBoot();

// Shared handlers; include them in each firmware's command table.
void cmdHello(Request& r);
void cmdPing(Request& r);
void cmdReboot(Request& r);
void cmdFactoryReset(Request& r);

}  // namespace app
