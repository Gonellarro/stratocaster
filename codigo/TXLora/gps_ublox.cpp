#include "gps_ublox.h"

static HardwareSerial* _gpsSerial = nullptr;

// Buffer intermedio seguro para almacenar el payload antes de verificar checksum
#define UBX_BUFFER_SIZE 128
static uint8_t  _ubxPayloadBuffer[UBX_BUFFER_SIZE];

// Máquina de estados
static UbxState _parserState = SYNC1;
static uint8_t  _msgClass = 0;
static uint8_t  _msgId = 0;
static uint16_t _msgLen = 0;
static uint16_t _payloadIdx = 0;
static uint8_t  _calcA = 0, _calcB = 0;

// Variables de estado del GPS (Solo modificadas tras validar Checksum)
static bool     _airborneConfirmed = false;
static bool     _ackReceived = false;
static bool     _nakReceived = false;
static uint32_t _lastUbxRxMillis = 0;

void ubx_send_packet(uint8_t cls, uint8_t id, uint8_t* payload, uint16_t len) {
    uint8_t header[6] = {0xB5, 0x62, cls, id, (uint8_t)(len & 0xFF), (uint8_t)((len >> 8) & 0xFF)};
    uint8_t cka = 0, ckb = 0;
    for (int i = 2; i < 6; i++) { cka += header[i]; ckb += cka; }
    for (int i = 0; i < len; i++) { cka += payload[i]; ckb += cka; }
    _gpsSerial->write(header, 6);
    if (len > 0) _gpsSerial->write(payload, len);
    _gpsSerial->write(cka); _gpsSerial->write(ckb);
}

void gps_init(HardwareSerial& serial) {
    _gpsSerial = &serial;
}

// Procesamiento seguro de mensajes UBX (¡Solo tras validar Checksum!)
static void process_validated_ubx_message() {
    _lastUbxRxMillis = millis();

    // 1. Procesar UBX-ACK-ACK (Clase 0x05, ID 0x01)
    if (_msgClass == 0x05 && _msgId == 0x01) {
        uint8_t targetClass = _ubxPayloadBuffer[0];
        uint8_t targetId    = _ubxPayloadBuffer[1];
        if (targetClass == 0x06 && targetId == 0x24) {
            _ackReceived = true; // ACK específico a nuestro NAV5
        }
    }
    // 2. Procesar UBX-ACK-NAK (Clase 0x05, ID 0x00)
    else if (_msgClass == 0x05 && _msgId == 0x00) {
        uint8_t targetClass = _ubxPayloadBuffer[0];
        uint8_t targetId    = _ubxPayloadBuffer[1];
        if (targetClass == 0x06 && targetId == 0x24) {
            _nakReceived = true;
        }
    }
    // 3. Procesar respuesta a consulta (Poll) UBX-CFG-NAV5 (Clase 0x06, ID 0x24)
    else if (_msgClass == 0x06 && _msgId == 0x24 && _msgLen >= sizeof(UbxCfgNav5)) {
        UbxCfgNav5* cfg = (UbxCfgNav5*)_ubxPayloadBuffer;
        if (cfg->dynModel == 6) {
            _airborneConfirmed = true;
        }
    }
}

void gps_process_char(char c) {
    switch (_parserState) {
        case SYNC1: if ((uint8_t)c == 0xB5) _parserState = SYNC2; break;
        case SYNC2: if ((uint8_t)c == 0x62) _parserState = CLASS; else _parserState = SYNC1; break;
        case CLASS: _msgClass = c; _calcA = c; _calcB = _calcA; _parserState = ID; break;
        case ID:    _msgId = c; _calcA += c; _calcB += _calcA; _parserState = LENGTH_L; break;
        case LENGTH_L: _msgLen = c; _calcA += c; _calcB += _calcA; _parserState = LENGTH_H; break;
        case LENGTH_H: 
            _msgLen |= ((uint16_t)c << 8); _calcA += c; _calcB += _calcA; _payloadIdx = 0;
            if (_msgLen > UBX_BUFFER_SIZE) _parserState = SYNC1; // Previene desbordamientos por ruido
            else _parserState = (_msgLen == 0) ? CK_A : PAYLOAD;
            break;
        case PAYLOAD:
            _calcA += c; _calcB += _calcA;
            if (_payloadIdx < UBX_BUFFER_SIZE) {
                _ubxPayloadBuffer[_payloadIdx] = c; // Guardamos temporalmente sin interpretar
            }
            _payloadIdx++;
            if (_payloadIdx >= _msgLen) _parserState = CK_A;
            break;
        case CK_A:
            if (c == _calcA) _parserState = CK_B; else _parserState = SYNC1;
            break;
        case CK_B:
            if (c == _calcB) {
                process_validated_ubx_message(); // ¡Damos luz verde! El paquete es auténtico
            }
            _parserState = SYNC1;
            break;
    }
}

// Desactiva tramas NMEA ruidosas para descargar la UART
void disable_nmea_msg(uint8_t id) {
    UbxCfgMsg cmd = { 0xF0, id, 0x00 };
    ubx_send_packet(0x06, 0x01, (uint8_t*)&cmd, sizeof(cmd));
    delay(100);
}

bool gps_configure_mission_profile() {
    // A) Configurar tasa a 5 Hz (200 ms por muestra) 
    UbxCfgRate rateCmd = { 200, 1, 1 };
    Serial.println("[UBX] Configurando tasa de refresco a 5 Hz...");
    ubx_send_packet(0x06, 0x08, (uint8_t*)&rateCmd, sizeof(rateCmd));
    delay(200);

    // B) Filtrar sentencias NMEA irrelevantes
    Serial.println("[UBX] Filtrando sentencias NMEA secundarias (GLL, GSA, GSV, VTG)...");
    disable_nmea_msg(0x01); // GLL
    disable_nmea_msg(0x02); // GSA
    disable_nmea_msg(0x03); // GSV
    disable_nmea_msg(0x05); // VTG

    // C) Configurar Modelo Dinámico Airborne < 1G [cite: 109]
    UbxCfgNav5 navCmd;
    memset(&navCmd, 0, sizeof(navCmd));
    //navCmd.mask = 0xFFFF;
    navCmd.mask = 0x0001; 
    navCmd.dynModel = 6;   // 6 = Airborne < 1G    
    //navCmd.fixMode = 3;

    _ackReceived = false; _nakReceived = false;
    
    Serial.println("[UBX] Enviando comando crítico CFG-NAV5 (Airborne < 1G)...");
    ubx_send_packet(0x06, 0x24, (uint8_t*)&navCmd, sizeof(navCmd));

    unsigned long start = millis();
    while (millis() - start < 1500) {
        while (_gpsSerial->available() > 0) gps_process_char(_gpsSerial->read());
        if (_ackReceived) return true;
        if (_nakReceived) {
            Serial.println("[UBX] ¡ALERTA! El GPS devolvió un NAK explícito.");
            return false;
        }
    }
    return false;
}

bool gps_verify_airborne() {
    _airborneConfirmed = false;
    Serial.println("[UBX] Solicitando verificación física del registro (Poll CFG-NAV5)...");
    ubx_send_packet(0x06, 0x24, nullptr, 0);

    unsigned long start = millis();
    while (millis() - start < 1500) {
        while (_gpsSerial->available() > 0) gps_process_char(_gpsSerial->read());
        if (_airborneConfirmed) return true;
    }
    return false;
}

bool gps_is_airborne_active() { return _airborneConfirmed; }
uint32_t gps_get_last_ubx_rx() { return _lastUbxRxMillis; }
