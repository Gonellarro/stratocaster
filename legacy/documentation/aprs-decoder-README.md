# Decodificador APRS LoRa

Convierte los mensajes APRS de texto recibidos en:

`sonda/lora/aprs/telemetry/<indicativo>`

en telemetría JSON normalizada publicada en:

`sonda/lora/<indicativo>/telemetry`

Telegraf ya está suscrito a ese segundo patrón, por lo que la posición, altitud,
temperatura y presión quedan disponibles en InfluxDB y Grafana sin cambiar su
configuración.

Para arrancarlo dentro de `docker-TIG`:

```bash
docker compose up -d --build aprs-decoder
docker compose logs -f aprs-decoder
```
