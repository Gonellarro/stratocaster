// =============================================================================
//  RXLora.ino  —  LoRa GPS Receiver  →  MQTT + Web
//  Receives LoRa GPS packets, publishes to MQTT, serves a local status page.
// =============================================================================

#include <LoRa.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ESPAsyncWebServer.h>

// Inclusión del archivo externo con las credenciales ocultas
#include "secrets.h"

// -----------------------------------------------------------------------------
//  CONFIGURATION  —  Hardware & Protocol Settings Only
// -----------------------------------------------------------------------------

// MQTT topic
#define MQTT_TOPIC  "sonda/lora/rx_sonda/telemetry"

// LoRa pins (TTGO / LilyGO T-Beam typical wiring)
#define LORA_SCK        5
#define LORA_MISO       19
#define LORA_MOSI       27
#define LORA_SS         18
#define LORA_RST        14
#define LORA_DIO0       26

// LoRa frequency: 868E6 for Europe, 915E6 for Americas
#define LORA_FREQUENCY  868E6

// Watchdog: restart LoRa if no packet received for this many ms
#define LORA_WATCHDOG_MS  60000UL

// MQTT reconnect: minimum ms between reconnect attempts (non-blocking)
#define MQTT_RETRY_MS     5000UL

// -----------------------------------------------------------------------------
//  DATA MODEL
// -----------------------------------------------------------------------------

struct GpsData {
  String lat       = "";
  String lng       = "";
  String date      = "";
  String time      = "";
  String altitude  = "";
  String course    = "";
  String speed     = "";
  bool   valid     = false;
};

// Last successfully parsed fix — used by web server and MQTT
GpsData lastFix;
String  lastRawPacket = "No data received yet.";

// -----------------------------------------------------------------------------
//  GLOBALS
// -----------------------------------------------------------------------------

AsyncWebServer  webServer(80);
WiFiClient      wifiClient;
PubSubClient    mqttClient(wifiClient);

unsigned long lastPacketMillis  = 0;   // Watchdog: time of last received packet
unsigned long lastMqttRetry     = 0;   // Non-blocking MQTT reconnect

// -----------------------------------------------------------------------------
//  LORA
// -----------------------------------------------------------------------------

bool initLoRa() {
  SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_SS);
  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
  return LoRa.begin(LORA_FREQUENCY);
}

// Watchdog: attempt LoRa restart if silent for LORA_WATCHDOG_MS
void checkLoRaWatchdog() {
  if (millis() - lastPacketMillis < LORA_WATCHDOG_MS) return;

  lastPacketMillis = millis();
  Serial.println("[LoRa] Watchdog triggered — restarting LoRa...");
  LoRa.end();
  delay(500);
  if (!initLoRa()) {
    Serial.println("[LoRa] ERROR: restart failed.");
  } else {
    Serial.println("[LoRa] Restart OK.");
  }
}

// -----------------------------------------------------------------------------
//  PACKET PARSING
// -----------------------------------------------------------------------------

String extractField(String& src, char sep) {
  int idx = src.indexOf(sep);
  if (idx < 0) {
    String field = src;
    src = "";
    return field;
  }
  String field = src.substring(0, idx);
  src = src.substring(idx + 1);
  return field;
}

bool parsePacket(const String& raw, GpsData& out) {
  String buf = raw;

  String coords    = extractField(buf, ';');
  out.date         = extractField(buf, ';');
  out.time         = extractField(buf, ';');
  out.altitude     = extractField(buf, ';');
  out.course       = extractField(buf, ';');
  out.speed        = buf;

  int commaIdx = coords.indexOf(',');
  if (commaIdx < 0) return false;
  out.lat = coords.substring(0, commaIdx);
  out.lng = coords.substring(commaIdx + 1);

  if (out.lat.length() == 0 || out.lng.length() == 0) return false;

  out.valid = true;
  return true;
}

// -----------------------------------------------------------------------------
//  MQTT
// -----------------------------------------------------------------------------

void maintainMqtt() {
  if (mqttClient.connected()) {
    mqttClient.loop();
    return;
  }
  unsigned long now = millis();
  if (now - lastMqttRetry < MQTT_RETRY_MS) return;
  lastMqttRetry = now;

  Serial.print("[MQTT] Connecting...");
#if defined(MQTT_USER) && defined(MQTT_PASS)
  bool ok = mqttClient.connect(MQTT_CLIENT_ID, MQTT_USER, MQTT_PASS);
#else
  bool ok = mqttClient.connect(MQTT_CLIENT_ID);
#endif
  if (ok) {
    Serial.println(" connected.");
  } else {
    Serial.println(" failed, state=" + String(mqttClient.state()) + ". Retry in " + String(MQTT_RETRY_MS / 1000) + "s.");
  }
}

void publishFix(const GpsData& fix) {
  if (!mqttClient.connected()) {
    Serial.println("[MQTT] Not connected — skipping publish.");
    return;
  }

  String topic = MQTT_TOPIC;
  String payload = String("{") +
    "\"lat\":"      + fix.lat      + ","   +
    "\"lng\":"      + fix.lng      + ","   +
    "\"date\":\""   + fix.date     + "\"," +
    "\"time\":\""   + fix.time     + "\"," +
    "\"altitude\":" + fix.altitude + ","   +
    "\"course\":"   + fix.course   + ","   +
    "\"speed\":"    + fix.speed    +
    "}";

  Serial.println("[MQTT] → " + topic + " : " + payload);
  mqttClient.publish(topic.c_str(), payload.c_str());
}

// -----------------------------------------------------------------------------
//  WEB SERVER
// -----------------------------------------------------------------------------

void setupWebServer() {
  webServer.on("/", HTTP_GET, [](AsyncWebServerRequest* request) {
    String mapsUrl = "http://maps.google.com/?q=" + lastFix.lat + "," + lastFix.lng;

    String html = R"rawlit(<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="refresh" content="10">
  <title>LoRa GPS Receiver</title>
  <style>
    body { font-family: sans-serif; padding: 1.5rem; background: #f4f4f4; }
    h1   { font-size: 1.2rem; color: #333; }
    .card { background: white; border-radius: 8px; padding: 1rem 1.5rem; max-width: 420px;
            box-shadow: 0 2px 6px rgba(0,0,0,.15); }
    .label { color: #888; font-size: .85rem; margin-top: .6rem; }
    .value { font-size: 1.05rem; font-weight: bold; color: #222; }
    a { display: inline-block; margin-top: 1rem; color: white; background: #1a73e8;
        padding: .5rem 1rem; border-radius: 6px; text-decoration: none; }
    a:hover { background: #1558b0; }
    .raw  { margin-top: 1rem; font-size: .8rem; color: #aaa; word-break: break-all; }
  </style>
</head>
<body>
  <div class="card">
    <h1>LoRa GPS Receiver</h1>)rawlit";

    if (lastFix.valid) {
      html += "<div class='label'>Coordinates</div><div class='value'>" + lastFix.lat + ", " + lastFix.lng + "</div>";
      html += "<div class='label'>Date / Time</div><div class='value'>" + lastFix.date + "   " + lastFix.time + "</div>";
      html += "<div class='label'>Altitude</div><div class='value'>" + lastFix.altitude + " m</div>";
      html += "<div class='label'>Course</div><div class='value'>" + lastFix.course + "°</div>";
      html += "<div class='label'>Speed</div><div class='value'>" + lastFix.speed + " km/h</div>";
      html += "<a href='" + mapsUrl + "' target='_blank'>Open in Google Maps</a>";
    } else {
      html += "<div class='value' style='color:#c00'>Waiting for GPS data...</div>";
    }

    html += "<div class='raw'>Last raw packet: " + lastRawPacket + "</div>";
    html += "</div></body></html>";

    request->send(200, "text/html", html);
  });

  webServer.begin();
  Serial.println("[Web] Server started.");
}

// -----------------------------------------------------------------------------
//  SETUP
// -----------------------------------------------------------------------------

void setup() {
  Serial.begin(115200);
  Serial.println("[RXLora] Starting...");

  // LoRa
  if (!initLoRa()) {
    Serial.println("[RXLora] ERROR: LoRa init failed. Check wiring.");
    while (1);
  }
  Serial.println("[RXLora] LoRa ready at " + String((long)LORA_FREQUENCY / 1000000) + " MHz");
  lastPacketMillis = millis();

  // WiFi utilizando constantes de secrets.h
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("[WiFi] Connecting");
  unsigned long wifiStart = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - wifiStart < 15000UL) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("[WiFi] Connected — IP: " + WiFi.localIP().toString());
  } else {
    Serial.println("[WiFi] Connection timeout. Continuing background reconnection...");
  }

  // MQTT utilizando constantes de secrets.h
  mqttClient.setServer(MQTT_SERVER, MQTT_PORT);
  maintainMqtt();

  // Web server
  setupWebServer();
}

// -----------------------------------------------------------------------------
//  LOOP
// -----------------------------------------------------------------------------

void loop() {
  maintainMqtt();

  int packetSize = LoRa.parsePacket();
  if (packetSize > 0) {
    String raw = "";
    while (LoRa.available()) {
      raw += (char)LoRa.read();
    }

    Serial.println("[LoRa] Received: " + raw);
    lastRawPacket    = raw;
    lastPacketMillis = millis();

    GpsData fix;
    if (parsePacket(raw, fix)) {
      lastFix = fix;
      publishFix(fix);
    } else {
      Serial.println("[LoRa] WARNING: malformed packet, ignored.");
    }

  } else {
    checkLoRaWatchdog();
  }
}