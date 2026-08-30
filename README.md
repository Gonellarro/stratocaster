# Stratocaster · Telemetría de sonda

Sistema de telemetría para una sonda meteorológica. Recoge datos de un móvil
Android y de enlaces LoRa, los almacena en InfluxDB y los muestra en Grafana.

El proyecto ya no incluye consola web de control, vídeo ni captura de fotos.
La operación actual es exclusivamente de telemetría MQTT.

## Arquitectura activa

```text
Móvil Android ──MQTT──┐
                       ├── Mosquitto ── Telegraf ── InfluxDB ── Grafana
LoRa RX ───────MQTT───┤
LoRa APRS ── MQTT ── decodificador APRS ──────────────────────┘
```

El móvil ejecuta `codigo/Android/sonda_telemetria.sh` y publica en:

```text
sonda/mobile/<DEVICE_ID>/telemetry
```

Los receptores LoRa publican telemetría JSON normalizada en:

```text
sonda/lora/<DEVICE_ID>/telemetry
```

El decodificador APRS convierte las tramas recibidas en
`sonda/lora/aprs/telemetry/<INDICATIVO>` al mismo formato normalizado de LoRa.

## Contenido del repositorio

```text
codigo/
  Android/sonda_telemetria.sh   Emisor Android/Termux
  Android/sonda.env.example     Plantilla de configuración privada
  RXLora/                       Firmware del receptor LoRa con MQTT
  TXLora/                       Firmware del transmisor LoRa
docker-TIG/                     Mosquitto, Telegraf, InfluxDB, Grafana y APRS
```

## Despliegue del servidor

En `docker-TIG`, crea `.env` a partir de `.env.example` y rellena las
credenciales de InfluxDB, Grafana y MQTT. Crea también el usuario MQTT:

```bash
cd docker-TIG
docker run --rm -v "$PWD/mosquitto/config:/mosquitto/config" \
  eclipse-mosquitto:2.1.2-alpine \
  mosquitto_passwd -b /mosquitto/config/password_file admin TU_CLAVE_MQTT

sudo chown 1883:1883 mosquitto/config/password_file
sudo chmod 600 mosquitto/config/password_file
docker compose up -d --build
```

Servicios expuestos:

- MQTT: puerto `1883`, con usuario y contraseña.
- InfluxDB: puerto `8086`.
- Grafana: puerto `3000`.

El dashboard `Sonda LORA` se provisiona automáticamente desde
`docker-TIG/grafana/provisioning/`.

## Preparación del móvil Android

En Termux instala Termux:API y concede permisos de ubicación. Después:

```bash
pkg install mosquitto jq coreutils termux-api
termux-setup-storage
```

Copia `codigo/Android/sonda.env.example` como `sonda.env` junto al script y
rellena `MQTT_HOST`, `MQTT_USER`, `MQTT_PASS`, `DEVICE_ID` y, opcionalmente,
`TELEMETRY_INTERVAL`.

```bash
chmod +x sonda_telemetria.sh
./sonda_telemetria.sh
```

El emisor mantiene un receptor GNSS activo y publica latitud, longitud,
altitud, precisión, batería y temperatura. Se detiene con `Ctrl+C`.

## Verificación rápida

Desde un equipo con acceso al broker:

```bash
mosquitto_sub -h stratocaster.martivich.es -p 1883 \
  -u admin -P 'TU_CLAVE_MQTT' -t 'sonda/#' -v
```

## Seguridad actual

MQTT usa autenticación, pero el puerto 1883 no cifra el tráfico. No publiques
credenciales ni archivos `.env` en Git. Antes de un uso expuesto a Internet,
conviene migrar a MQTT con TLS y usuarios con permisos limitados por topic.
