#ifndef GPS_UBLOX_H
#define GPS_UBLOX_H

#include <Arduino.h>

// Estructura oficial UBX-CFG-NAV5 (Modo Dinámico)
// IMPORTANTE: el payload de CFG-NAV5 en el protocolo UBX (NEO-6 incluido) es
// de 36 bytes FIJOS. Si el struct no ocupa exactamente 36 bytes, el receptor
// detecta longitud incorrecta para class/id 0x06/0x24 y responde con NAK.
struct __attribute__((__packed__)) UbxCfgNav5 {
    uint16_t mask;             
    uint8_t  dynModel;         // 6 = Airborne < 1G
    uint8_t  fixMode;          
    int32_t  fixedAlt;         
    uint32_t fixedAltVar;      
    int8_t   minElev;          
    uint8_t  drLimit;          
    uint16_t pDop;             
    uint16_t tDop;             
    uint16_t pAcc;             
    uint16_t tAcc;             
    uint8_t  staticHoldThresh; 
    uint8_t  dgpsTimeOut;      
    uint32_t reserved2;        // 4 bytes (antes estaba mal como 1+1 bytes)
    uint32_t reserved3;        // 4 bytes (antes estaba mal como 2 bytes)
    uint32_t reserved4;        // 4 bytes
};
// sizeof(UbxCfgNav5) == 36 bytes, coincide con lo que espera el NEO-6.

// Estructura oficial UBX-CFG-RATE (Frecuencia de actualización)
struct __attribute__((__packed__)) UbxCfgRate {
    uint16_t measRate;         // Tiempo entre mediciones en ms (200ms = 5Hz)
    uint16_t navRate;          // Ciclos de navegación (Siempre 1)
    uint16_t timeRef;          // Referencia de tiempo (1 = GPS)
};

// Estructura oficial UBX-CFG-MSG (Desactivar/Activar sentencias NMEA)
struct __attribute__((__packed__)) UbxCfgMsg {
    uint8_t msgClass;          // Clase del mensaje (0xF0 para NMEA estándar)
    uint8_t msgId;             // ID del mensaje NMEA (GLL, GSV, etc.)
    uint8_t rate;              // Tasa (0 = Desactivado, 1 = Activado por ciclo)
};

enum UbxState { SYNC1, SYNC2, CLASS, ID, LENGTH_L, LENGTH_H, PAYLOAD, CK_A, CK_B };

// API del Driver Aeroespacial Unificado
void gps_init(HardwareSerial& serial);
void gps_process_char(char c);
bool gps_configure_mission_profile();
bool gps_verify_airborne();          // <-- Corregido: Ahora expuesto correctamente para TXLora.ino
bool gps_is_airborne_active();       // <-- Corregido: Expuesta para que coincida con el loop() del .ino
uint32_t gps_get_last_ubx_rx();

#endif