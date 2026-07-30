// =============================================================================
//  TXLora.ino  —  GPS + LoRa Transmitter (Edición Certificada para Misión)
// =============================================================================

#include <TinyGPS++.h>
#include <HardwareSerial.h>
#include <LoRa.h>
#include "gps_ublox.h"

// -----------------------------------------------------------------------
//  SERVIDOR WEB DE DEPURACIÓN (solo pruebas de banco, NUNCA en vuelo)
// -----------------------------------------------------------------------
// Pon esto a 0 antes de sellar la sonda para el lanzamiento: en vuelo no
// hay red WiFi a la que conectarse y mantener el radio WiFi activo solo
// añade consumo y ruido de RF cerca del LoRa sin ningún beneficio.
#define ENABLE_WIFI_DEBUG_SERVER 1

#if ENABLE_WIFI_DEBUG_SERVER
    #include <WiFi.h>
    #include <WebServer.h>
    #include "credentials.h"   // WIFI_SSID / WIFI_PASSWORD — no se sube a git
    #define WIFI_CONNECT_TIMEOUT_MS 10000UL
    WebServer webServer(80);
    bool wifiDebugActive = false;
#endif

#define GPS_RX_PIN      34
#define GPS_TX_PIN      12
#define GPS_BAUD        9600

#define LORA_SCK        5
#define LORA_MISO       19
#define LORA_MOSI       27
#define LORA_SS         18
#define LORA_RST        14
#define LORA_DIO0       26

// Frecuencia en la que transmitimos
#define LORA_FREQUENCY  868E6
// Frecuencia en que transmitimos (100s)
#define TX_INTERVAL     100000UL

// Tiempos máximos tolerables de inactividad por canal
#define NMEA_TIMEOUT_MS        6000UL   // 6s sin recibir cadenas de texto de la UART (fallo real de comunicación)
#define UBX_VERIFY_INTERVAL_MS 60000UL  // cada 60s, comprobamos activamente que el perfil Airborne sigue vigente

TinyGPSPlus gps;
HardwareSerial gpsSerial(1);

unsigned long lastTxMillis = 0;
unsigned long lastNmeaByteMillis = 0;
unsigned long lastUbxVerifyMillis = 0;

void ejecutarCicloConfiguracionGPS() {
    Serial.println("\n=============================================");
    Serial.println("[MISION] INICIANDO SECUENCIA DE CONTROL GPS...");
    Serial.println("=============================================");
    
    int intento = 0;
    bool operativo = false;

    while (!operativo && intento < 3) {
        intento++;
        Serial.printf("[MISION] Secuencia de calibración #%d...\n", intento);
        
        if (gps_configure_mission_profile()) {
            delay(200);
            if (gps_verify_airborne()) {
                Serial.println("[MISION] ¡ÉXITO! Modo Estratosférico Verificado y Bloqueado.");
                operativo = true;
            }
        }
        if (!operativo) delay(1500);
    }

    if (!operativo) {
        Serial.println("[ERROR CRÍTICO] Módulo GPS fuera de perfil dinámico aeronáutico.");
    }
    Serial.println("=============================================\n");
}

String pad2(int v) { return (v < 10 ? "0" : "") + String(v); }

String buildPacket() {
    if (!gps.location.isValid()) return "";
    String lat  = String(gps.location.lat(), 6);
    String lng  = String(gps.location.lng(), 6);
    String date = gps.date.isValid() ? pad2(gps.date.month()) + "/" + pad2(gps.date.day()) + "/" + String(gps.date.year()) : "00/00/0000";
    String time = gps.time.isValid() ? pad2(gps.time.hour()) + ":" + pad2(gps.time.minute()) + ":" + pad2(gps.time.second()) : "00:00:00";
    String alt  = gps.altitude.isValid() ? String(gps.altitude.meters(), 1) : "0";
    String crs  = gps.course.isValid() ? String(gps.course.deg(), 1) : "0";
    String spd  = gps.speed.isValid() ? String(gps.speed.kmph(), 1) : "0";

    return lat + "," + lng + ";" + date + ";" + time + ";" + alt + ";" + crs + ";" + spd;
}

#if ENABLE_WIFI_DEBUG_SERVER
void conectarWifiDebug() {
    Serial.println("[WiFi] Conectando a la red de casa para servidor de depuración...");
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < WIFI_CONNECT_TIMEOUT_MS) {
        delay(250);
        Serial.print(".");
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
        wifiDebugActive = true;
        Serial.print("[WiFi] Conectado. IP del panel de pruebas: http://");
        Serial.println(WiFi.localIP());
    } else {
        wifiDebugActive = false;
        Serial.println("[WiFi] No se pudo conectar (timeout). Continuando sin panel web.");
    }
}

// Misma información que se imprime por Serial, pero servida como HTML
void handleWebRoot() {
    unsigned long ahora = millis();

    String html = "<!DOCTYPE html><html><head><meta charset='utf-8'>";
    html += "<title>Sonda - Panel de pruebas</title>";
    html += "<meta name='viewport' content='width=device-width, initial-scale=1'>";
    html += "<style>body{font-family:monospace;background:#111;color:#0f0;padding:1.5em}";
    html += "h1{color:#fff}table{border-collapse:collapse}td{padding:4px 12px}";
    html += ".ok{color:#0f0}.fail{color:#f55}</style></head><body>";
    html += "<h1>Sonda &mdash; Panel de pruebas</h1>";
    html += "<p><small>Se autoactualiza cada 2s. Solo para pruebas en tierra.</small></p>";
    html += "<table>";
    html += "<tr><td>Satelites</td><td>" + String(gps.satellites.value()) + "</td></tr>";
    html += "<tr><td>HDOP</td><td>" + String(gps.hdop.hdop(), 1) + "</td></tr>";
    html += "<tr><td>Modo Airborne</td><td class='" + String(gps_is_airborne_active() ? "ok" : "fail") + "'>" +
            String(gps_is_airborne_active() ? "OK" : "FALLO") + "</td></tr>";
    html += "<tr><td>Fix valido</td><td>" + String(gps.location.isValid() ? "SI" : "NO") + "</td></tr>";
    if (gps.location.isValid()) {
        html += "<tr><td>Latitud</td><td>" + String(gps.location.lat(), 6) + "</td></tr>";
        html += "<tr><td>Longitud</td><td>" + String(gps.location.lng(), 6) + "</td></tr>";
        html += "<tr><td>Altitud (m)</td><td>" + (gps.altitude.isValid() ? String(gps.altitude.meters(), 1) : "N/D") + "</td></tr>";
        html += "<tr><td>Rumbo</td><td>" + (gps.course.isValid() ? String(gps.course.deg(), 1) : "N/D") + "</td></tr>";
        html += "<tr><td>Velocidad (km/h)</td><td>" + (gps.speed.isValid() ? String(gps.speed.kmph(), 1) : "N/D") + "</td></tr>";
    }
    html += "<tr><td>Fecha/Hora GPS</td><td>" + (gps.date.isValid() && gps.time.isValid() ?
             pad2(gps.date.month()) + "/" + pad2(gps.date.day()) + "/" + String(gps.date.year()) + " " +
             pad2(gps.time.hour()) + ":" + pad2(gps.time.minute()) + ":" + pad2(gps.time.second()) : "N/D") + "</td></tr>";
    html += "<tr><td>Ultimo NMEA hace</td><td>" + String((ahora - lastNmeaByteMillis) / 1000) + " s</td></tr>";
    html += "<tr><td>Ultimo UBX hace</td><td>" + String((ahora - gps_get_last_ubx_rx()) / 1000) + " s</td></tr>";
    html += "<tr><td>Ultimo TX LoRa hace</td><td>" + String((ahora - lastTxMillis) / 1000) + " s</td></tr>";
    html += "<tr><td>RSSI WiFi</td><td>" + String(WiFi.RSSI()) + " dBm</td></tr>";
    html += "</table>";
    html += "<script>setTimeout(()=>location.reload(),2000);</script>";
    html += "</body></html>";

    webServer.send(200, "text/html", html);
}

// Mismos datos en JSON, útil para scripts o Grafana durante las pruebas
void handleWebData() {
    unsigned long ahora = millis();
    String json = "{";
    json += "\"satelites\":" + String(gps.satellites.value()) + ",";
    json += "\"hdop\":" + String(gps.hdop.hdop(), 1) + ",";
    json += "\"airborne\":" + String(gps_is_airborne_active() ? "true" : "false") + ",";
    json += "\"fix_valido\":" + String(gps.location.isValid() ? "true" : "false") + ",";
    json += "\"lat\":" + String(gps.location.isValid() ? gps.location.lat() : 0, 6) + ",";
    json += "\"lng\":" + String(gps.location.isValid() ? gps.location.lng() : 0, 6) + ",";
    json += "\"alt_m\":" + String(gps.altitude.isValid() ? gps.altitude.meters() : 0, 1) + ",";
    json += "\"rumbo_deg\":" + String(gps.course.isValid() ? gps.course.deg() : 0, 1) + ",";
    json += "\"velocidad_kmh\":" + String(gps.speed.isValid() ? gps.speed.kmph() : 0, 1) + ",";
    json += "\"ultimo_nmea_s\":" + String((ahora - lastNmeaByteMillis) / 1000) + ",";
    json += "\"ultimo_ubx_s\":" + String((ahora - gps_get_last_ubx_rx()) / 1000) + ",";
    json += "\"ultimo_tx_s\":" + String((ahora - lastTxMillis) / 1000) + ",";
    json += "\"wifi_rssi_dbm\":" + String(WiFi.RSSI());
    json += "}";

    webServer.send(200, "application/json", json);
}
#endif

void setup() {
    Serial.begin(115200);
    Serial.println("[Sonda] Cargando vectores de telemetría...");

    gpsSerial.begin(GPS_BAUD, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);
    gps_init(gpsSerial);
    
    delay(2000); // Retardo físico indispensable de estabilización eléctrica
    ejecutarCicloConfiguracionGPS();

    SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_SS);
    LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
    if (!LoRa.begin(LORA_FREQUENCY)) {
        Serial.println("[RF] ERROR: No se detectó transceptor LoRa.");
        while (1);
    }
    Serial.println("[RF] Radio en línea y sintonizada.");

#if ENABLE_WIFI_DEBUG_SERVER
    conectarWifiDebug();
    if (wifiDebugActive) {
        webServer.on("/", handleWebRoot);
        webServer.on("/data", handleWebData);
        webServer.begin();
        Serial.println("[WiFi] Servidor de depuración activo.");
    }
#endif

    lastNmeaByteMillis = millis();
    lastUbxVerifyMillis = millis();
}

void loop() {
#if ENABLE_WIFI_DEBUG_SERVER
    if (wifiDebugActive) webServer.handleClient();
#endif

    // 1. Inyección de flujo de datos paralelo a ambos parsers
    while (gpsSerial.available() > 0) {
        char c = gpsSerial.read();
        lastNmeaByteMillis = millis();
        
        gps_process_char(c); // Alimentación del parser binario UBX
        gps.encode(c);       // Alimentación del decodificador de texto NMEA
    }

    // 2. Watchdog de Doble Canal Avanzado
    unsigned long instanteActual = millis();
    bool perdidaComunicacionTotal = (instanteActual - lastNmeaByteMillis > NMEA_TIMEOUT_MS);

    if (perdidaComunicacionTotal) {
        // Silencio total en la UART: fallo real de comunicación con el módulo.
        Serial.println("[WATCHDOG] Fallo detectado. Reactivando interfaz u-blox...");
        ejecutarCicloConfiguracionGPS();
        lastNmeaByteMillis = millis();
        lastUbxVerifyMillis = millis();
        gpsSerial.flush();
    } else if (instanteActual - lastUbxVerifyMillis >= UBX_VERIFY_INTERVAL_MS) {
        // Comunicación NMEA viva; comprobamos activamente (y de forma ligera)
        // que el perfil Airborne < 1G sigue aplicado, en vez de esperar a que
        // expire un timeout pasivo que nunca refleja el estado real.
        lastUbxVerifyMillis = instanteActual;
        Serial.println("[WATCHDOG] Verificación activa del perfil Airborne (poll)...");
        if (!gps_verify_airborne()) {
            Serial.println("[WATCHDOG] Perfil Airborne perdido. Reactivando interfaz u-blox...");
            ejecutarCicloConfiguracionGPS();
            lastUbxVerifyMillis = millis();
        }
    }

    // 3. Ventana cíclica de transmisión de datos por Radio
    if (instanteActual - lastTxMillis >= TX_INTERVAL) {
        lastTxMillis = instanteActual;

        // Monitor en consola local
        Serial.printf("[Vuelo] Satélites: %d | HDOP: %.1f | Modo Airborne: %s | Freq: 5Hz\n", 
                      gps.satellites.value(), gps.hdop.hdop(), gps_is_airborne_active() ? "OK" : "FALLO");

        if (gps.location.isValid()) {
            String packet = buildPacket();
            if (packet.length() > 0) {
                Serial.println("[LoRa TX] → " + packet);
                LoRa.beginPacket();
                LoRa.print(packet);
                LoRa.endPacket();
            }
        } else {
            Serial.println("[Telemetría] Buscando FIX de satélites...");
        }
    }
}