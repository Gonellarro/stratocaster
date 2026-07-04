// =============================================================================
//  TXLora.ino  —  GPS + LoRa Transmitter
//  Reads GPS data and transmits a formatted packet over LoRa every TX_INTERVAL ms.
// =============================================================================

#include <TinyGPS++.h>
#include <HardwareSerial.h>
#include <LoRa.h>

// -----------------------------------------------------------------------------
//  CONFIGURATION  —  edit only this section
// -----------------------------------------------------------------------------

// GPS serial port
#define GPS_RX_PIN      34
#define GPS_TX_PIN      12
#define GPS_BAUD        9600

// LoRa pins (TTGO / LilyGO T-Beam typical wiring)
#define LORA_SCK        5
#define LORA_MISO       19
#define LORA_MOSI       27
#define LORA_SS         18
#define LORA_RST        14
#define LORA_DIO0       26

// LoRa frequency: 868E6 for Europe, 915E6 for Americas
#define LORA_FREQUENCY  868E6

// Transmission interval in milliseconds
#define TX_INTERVAL     10000UL

// -----------------------------------------------------------------------------
//  GLOBALS
// -----------------------------------------------------------------------------

TinyGPSPlus gps;
HardwareSerial gpsSerial(1);   // UART1 — avoids SoftwareSerial overhead on ESP32

unsigned long lastTxMillis = 0;

// -----------------------------------------------------------------------------
//  HELPERS
// -----------------------------------------------------------------------------

// Returns a zero-padded two-digit string
String pad2(int v) {
  return (v < 10 ? "0" : "") + String(v);
}

// Builds the packet string from the current GPS fix.
// Format: lat,lng;MM/DD/YYYY;HH:MM:SS;altitude;course;speed_kmph
// Returns empty string if location is not valid.
String buildPacket() {
  if (!gps.location.isValid()) return "";

  String lat  = String(gps.location.lat(), 6);
  String lng  = String(gps.location.lng(), 6);

  String date = gps.date.isValid()
    ? pad2(gps.date.month()) + "/" + pad2(gps.date.day()) + "/" + String(gps.date.year())
    : "00/00/0000";

  String time = gps.time.isValid()
    ? pad2(gps.time.hour()) + ":" + pad2(gps.time.minute()) + ":" + pad2(gps.time.second())
    : "00:00:00";

  String alt  = gps.altitude.isValid() ? String(gps.altitude.meters(), 1) : "0";
  String crs  = gps.course.isValid()   ? String(gps.course.deg(),      1) : "0";
  String spd  = gps.speed.isValid()    ? String(gps.speed.kmph(),      1) : "0";

  return lat + "," + lng + ";" +
         date + ";" +
         time + ";" +
         alt + ";" +
         crs + ";" +
         spd;
}

// Transmits packet over LoRa and prints it to Serial.
void transmitPacket(const String& packet) {
  Serial.println("[TX] " + packet);
  LoRa.beginPacket();
  LoRa.print(packet);
  LoRa.endPacket();
}

// -----------------------------------------------------------------------------
//  SETUP
// -----------------------------------------------------------------------------

void setup() {
  Serial.begin(115200);
  Serial.println("[TXLora] Starting...");

  // GPS on UART1
  gpsSerial.begin(GPS_BAUD, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);

  // LoRa
  SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_SS);
  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
  if (!LoRa.begin(LORA_FREQUENCY)) {
    Serial.println("[TXLora] ERROR: LoRa init failed. Check wiring.");
    while (1);
  }
  Serial.println("[TXLora] LoRa ready at " + String((long)LORA_FREQUENCY / 1000000) + " MHz");
}

// -----------------------------------------------------------------------------
//  LOOP
// -----------------------------------------------------------------------------

void loop() {
  // Feed GPS parser — only act when a complete NMEA sentence is decoded
  while (gpsSerial.available() > 0) {
    gps.encode(gpsSerial.read());
  }

  // --- DIAGNÓSTICO: muestra cada 5s cuántos caracteres GPS han llegado
  static unsigned long lastDiag = 0;
  if (millis() - lastDiag >= 5000) {
    lastDiag = millis();
    Serial.println("[GPS] Chars processed: " + String(gps.charsProcessed()) +
                   " | Sentences with fix: " + String(gps.sentencesWithFix()) +
                   " | Failed checksum: " + String(gps.failedChecksum()));
  }
  // --- FIN DIAGNÓSTICO

  // Warn if no GPS module detected after 5 s
  if (millis() > 5000 && gps.charsProcessed() < 10) {
    Serial.println("[TXLora] WARNING: No GPS data — check wiring.");
  }

  // Transmit on interval
  unsigned long now = millis();
  if (now - lastTxMillis >= TX_INTERVAL) {
    lastTxMillis = now;

    String packet = buildPacket();
    if (packet.length() > 0) {
      transmitPacket(packet);
    } else {
      Serial.println("[TXLora] No valid GPS fix — skipping transmission.");
    }
  }
}
