// =============================================================================
//  secrets.h — Archivo de credenciales privadas e ignorado en Git
// =============================================================================

#ifndef SECRETS_H
#define SECRETS_H

// Configuración de red WiFi local
#define WIFI_SSID       "NovaWifi"
#define WIFI_PASSWORD   "Marti07Emma21Maria30"

// Configuración de acceso al Bróker MQTT
#define MQTT_SERVER     "sonda.martivich.es"
#define MQTT_PORT       1883
#define MQTT_CLIENT_ID  "LoRaReceiver"

// Credenciales robustas cambiadas tras auditoría de intrusiones
#define MQTT_USER       "admin"
#define MQTT_PASS       "AWLCxdfGxwohHF2qpScJLK9AbRAFxD"

#endif // SECRETS_H