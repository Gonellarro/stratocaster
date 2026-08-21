#!/data/data/com.termux/files/usr/bin/bash

# Emisor de telemetría MQTT directo.
# No espera órdenes, no inicia vídeo, no captura fotos y no depende del dashboard.
# Si el GPS no tiene fix, publica igualmente el ciclo con coordenadas nulas.

set -u

CONFIG_FILE="${SONDA_CONFIG_FILE:-$(dirname "$0")/sonda.env}"
if [ -f "$CONFIG_FILE" ]; then
    # shellcheck disable=SC1090
    source "$CONFIG_FILE"
fi

DEVICE_ID="${DEVICE_ID:-movil_sonda_1}"
MQTT_HOST="${MQTT_HOST:-localhost}"
MQTT_PORT="${MQTT_PORT:-1883}"
MQTT_USER="${MQTT_USER:-}"
MQTT_PASS="${MQTT_PASS:-}"
TOPIC_TELEMETRY="sonda/mobile/$DEVICE_ID/telemetry"
INTERVAL="${TELEMETRY_INTERVAL:-5}"

for cmd in mosquitto_pub jq timeout termux-location termux-battery-status termux-wake-lock termux-wake-unlock; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "[ERROR] Falta '$cmd'. Ejecuta install_sonda.sh en Termux."
        exit 1
    fi
done

publish_telemetry() {
    local payload="$1"
    if [ -n "$MQTT_USER" ]; then
        timeout 8s mosquitto_pub \
            -h "$MQTT_HOST" -p "$MQTT_PORT" \
            -u "$MQTT_USER" -P "$MQTT_PASS" \
            -t "$TOPIC_TELEMETRY" -m "$payload" -q 1
    else
        timeout 8s mosquitto_pub \
            -h "$MQTT_HOST" -p "$MQTT_PORT" \
            -t "$TOPIC_TELEMETRY" -m "$payload" -q 1
    fi
}

cleanup() {
    echo "[INFO] Telemetría detenida."
    termux-wake-unlock >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

termux-wake-lock >/dev/null 2>&1 || true
echo "[INFO] Publicando telemetría en $TOPIC_TELEMETRY cada ${INTERVAL}s."
echo "[INFO] No se inicia vídeo, no se capturan fotos y no se espera GPS válido."

while true; do
    # -r last no espera una adquisición: devuelve el último dato disponible.
    # Si no existe un fix válido, el timeout evita bloquear el ciclo.
    location_json=$(timeout 5s termux-location -p gps -r last 2>/dev/null || true)
    lat=$(echo "$location_json" | jq -r '.latitude // "null"' 2>/dev/null || echo null)
    lng=$(echo "$location_json" | jq -r '.longitude // "null"' 2>/dev/null || echo null)
    alt=$(echo "$location_json" | jq -r '.altitude // "null"' 2>/dev/null || echo null)
    accuracy=$(echo "$location_json" | jq -r '.accuracy // "null"' 2>/dev/null || echo null)

    battery_json=$(timeout 5s termux-battery-status 2>/dev/null || true)
    level=$(echo "$battery_json" | jq -r '.percentage // 0' 2>/dev/null || echo 0)
    temp=$(echo "$battery_json" | jq -r '.temperature // 0' 2>/dev/null || echo 0)
    [[ "$level" =~ ^[0-9]+([.][0-9]+)?$ ]] || level=0
    [[ "$temp" =~ ^-?[0-9]+([.][0-9]+)?$ ]] || temp=0

    payload=$(jq -cn \
        --argjson lat "$lat" --argjson lng "$lng" \
        --argjson altitude "$alt" --argjson accuracy "$accuracy" \
        --argjson level "$level" --argjson temp "$temp" \
        '{lat:$lat, lng:$lng, altitude:$altitude, accuracy:$accuracy, level:$level, temp:$temp}')

    if publish_telemetry "$payload"; then
        echo "[$(date +%T)] Telemetría enviada: $payload"
    else
        echo "[$(date +%T)] No se pudo publicar MQTT; se reintentará."
    fi
    sleep "$INTERVAL"
done
