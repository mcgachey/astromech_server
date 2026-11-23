#include "Commands.h"

#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

#include "Link.h"
#include "Settings.h"
#include "Version.h"

namespace app {

static const char* g_role = "unknown";
static const size_t kQueueDepth = 8;

void setRole(const char* role) { g_role = role; }

// ---- Request ----------------------------------------------------------------

JsonObjectConst Request::args() const {
  JsonVariantConst a = doc_["args"];
  return a.is<JsonObjectConst>() ? a.as<JsonObjectConst>() : JsonObjectConst();
}

JsonObject Request::result() {
  if (result_.isNull()) result_.to<JsonObject>();
  return result_.as<JsonObject>();
}

void Request::send(bool ok) {
  JsonDocument out;
  out["id"] = doc_["id"];  // null if the request had none
  out["ok"] = ok;
  replied_ = true;
  if (ok) {
    out["result"] = result();
  } else {
    out["error"] = result_["error"];
  }
  serialLink.send(out);
}

void Request::ok() { send(true); }

void Request::fail(const char* code, const String& message) {
  result_.clear();
  result_["error"]["code"] = code;
  result_["error"]["message"] = message;
  send(false);
}

// ---- CommandServer ----------------------------------------------------------

void CommandServer::run(Request& req, Handler fn) {
  fn(req);
  if (!req.replied()) req.fail(err::kInternal, "handler did not reply");
}

void CommandServer::workerEntry(void* arg) {
  CommandServer* self = static_cast<CommandServer*>(arg);
  struct Job {
    Request* req;
    Handler fn;
  } job;
  for (;;) {
    if (xQueueReceive((QueueHandle_t)self->queue_, &job, portMAX_DELAY) == pdTRUE) {
      self->run(*job.req, job.fn);
      delete job.req;
    }
  }
}

void CommandServer::begin() {
  struct Job {
    Request* req;
    Handler fn;
  };
  queue_ = xQueueCreate(kQueueDepth, sizeof(Job));
  xTaskCreate(workerEntry, "worker", 10240, this, 1, nullptr);
}

void CommandServer::poll() {
  String line;
  for (;;) {
    Link::ReadResult r = serialLink.readLine(line);
    if (r == Link::kNothing) return;
    if (r == Link::kOverflow) {
      JsonDocument out;
      out["id"] = nullptr;
      out["ok"] = false;
      out["error"]["code"] = err::kBadRequest;
      out["error"]["message"] = "line too long";
      serialLink.send(out);
      continue;
    }
    if (line[0] != '{') continue;  // not protocol traffic
    dispatch(line);
  }
}

void CommandServer::dispatch(const String& line) {
  JsonDocument doc;
  DeserializationError e = deserializeJson(doc, line);
  if (e || !doc.is<JsonObject>()) {
    JsonDocument out;
    out["id"] = nullptr;
    out["ok"] = false;
    out["error"]["code"] = err::kBadJson;
    out["error"]["message"] = e ? e.c_str() : "not an object";
    serialLink.send(out);
    return;
  }
  Request* req = new Request(static_cast<JsonDocument&&>(doc));
  if (!req->cmd()[0]) {
    req->fail(err::kBadRequest, "missing \"cmd\"");
    delete req;
    return;
  }
  for (size_t i = 0; i < count_; i++) {
    if (strcmp(table_[i].name, req->cmd()) != 0) continue;
    if (!table_[i].queued) {
      run(*req, table_[i].fn);
      delete req;
      return;
    }
    struct Job {
      Request* req;
      Handler fn;
    } job = {req, table_[i].fn};
    if (xQueueSend((QueueHandle_t)queue_, &job, 0) != pdTRUE) {
      req->fail(err::kBusy, "command queue full");
      delete req;
    }
    return;  // the worker owns req now
  }
  req->fail(err::kUnknownCommand, String("unknown command: ") + req->cmd());
  delete req;
}

// ---- shared commands --------------------------------------------------------

void fillHello(JsonObject out) {
  char id[13];
  snprintf(id, sizeof(id), "%012llx", (unsigned long long)ESP.getEfuseMac());
  out["role"] = g_role;
  out["firmware_version"] = FIRMWARE_VERSION;
  out["protocol"] = PROTOCOL_VERSION;
  out["device_id"] = (const char*)id;
  out["uptime_ms"] = millis();
  out["build"] = FIRMWARE_BUILD_ID " " __DATE__ " " __TIME__;
}

void announceBoot() {
  JsonDocument d;
  fillHello(d.to<JsonObject>());
  serialLink.event("boot", d);
}

void cmdHello(Request& r) {
  fillHello(r.result());
  r.ok();
}

void cmdPing(Request& r) {
  r.result()["uptime_ms"] = millis();
  r.ok();
}

static void restartSoon() {
  Serial.flush();
  delay(100);
  ESP.restart();
}

void cmdReboot(Request& r) {
  r.ok();
  restartSoon();
}

void cmdFactoryReset(Request& r) {
  settings.clear();
  r.ok();
  restartSoon();
}

}  // namespace app
