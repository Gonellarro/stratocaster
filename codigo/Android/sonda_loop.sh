#!/data/data/com.termux/files/usr/bin/bash

# ==============================================================================
# ORQUESTRADOR MULTI-FASE SIMPLIFICADO DE LA SONDA (STRATOCASTER)
# Fase 0: Pruebas y Espera en Rampa
# Fase 1: Vuelo en Directo (Streaming SRT)
# Fase 2: Bucle Autónomo de Transmisión Directa (Captura y GPS)
# ==============================================================================

# Cargar variables de entorno y credenciales privadas desde 'sonda.env' si existe
CONFIG_FILE="${SONDA_CONFIG_FILE:-$(dirname "$0")/sonda.env}"
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
fi

# Rutas públicas para ficheros que el operador necesita consultar o copiar.
PHOTO_DIR="${PHOTO_DIR:-$HOME/storage/pictures/Sonda}"
AUDIO_DIR="${AUDIO_DIR:-$HOME/storage/music/Sonda}"
TARGET_IMG="$PHOTO_DIR/foto.jpg"

# Estado interno: permanece privado en Termux, fuera del almacenamiento público.
STATE_DIR="$HOME/.sonda"
OFFLINE_LOG="$STATE_DIR/sonda_offline.log"
ARMED_FLAG="$STATE_DIR/sonda.armed"
LAUNCH_FLAG="$STATE_DIR/sonda.launch"
ABORT_FLAG="$STATE_DIR/sonda.abort"
VIDEO_FLAG="$STATE_DIR/sonda.video"
LANDING_FLAG="$STATE_DIR/sonda.landed"

# Único audio operativo por ahora: baliza de recuperación.
ALARM_AUDIO="${ALARM_AUDIO:-$AUDIO_DIR/alarma.mp3}"

# Definir valores predeterminados e identificador de dispositivo
if [ -z "$DEVICE_ID" ]; then
    DEVICE_ID="movil_sonda_1"
fi

# Canales MQTT dinámicos basados en la arquitectura multi-dispositivo
TOPIC_STATUS="sonda/mobile/$DEVICE_ID/status"
TOPIC_TELEMETRY="sonda/mobile/$DEVICE_ID/telemetry"
TOPIC_CAMERA="sonda/mobile/$DEVICE_ID/camera"
TOPIC_COMMAND="sonda/mobile/$DEVICE_ID/command"


# Asegurar la existencia de directorios de salida
mkdir -p "$PHOTO_DIR" "$AUDIO_DIR" "$STATE_DIR"

# Verificar dependencias críticas de Termux y herramientas
for cmd in termux-camera-photo termux-wake-lock termux-wake-unlock mosquitto_pub mosquitto_sub jq termux-battery-status termux-location termux-media-player; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "[❌ ERROR] Falta '$cmd'. Ejecuta primero ./install_sonda.sh en Termux."
        exit 1
    fi
done

# URL de VDO.ninja para transmisión de vídeo (facilidad de mantenimiento)
VDO_NINJA_URL="https://vdo.ninja/?push=sonda_stratocaster&webcam&facing=back&autostart&noaudio&videobitrate=1000&quality=2&nopreview&clean&forcelandscape"

# La posición se sigue leyendo para seguridad, pero la red se sondea con una
# cadencia moderada para no gastar batería cuando no hay cobertura.
CONNECTIVITY_CHECK_INTERVAL="${CONNECTIVITY_CHECK_INTERVAL:-15}"
OFFLINE_TELEMETRY_INTERVAL="${OFFLINE_TELEMETRY_INTERVAL:-60}"

# Función auxiliar para detener aplicaciones de vídeo en directo
stop_video_apps() {
    echo "[🔌 VIDEO] Deteniendo transmisión de vídeo en directo..."
    am force-stop flutter.vdo.ninja &>/dev/null
    am force-stop com.android.chrome &>/dev/null
    am force-stop com.wmspanel.larix_broadcaster &>/dev/null
}

stop_recovery_audio() {
    termux-media-player stop &>/dev/null || true
    pkill -f "sonda_recovery_alarm" &>/dev/null || true
}

start_recovery_audio() {
    [ -f "$ALARM_AUDIO" ] || return 1
    stop_recovery_audio
    (
        exec -a sonda_recovery_alarm bash -c 'while true; do termux-media-player play "$1" >/dev/null 2>&1; sleep 90; done' -- "$ALARM_AUDIO"
    ) &
}

# Función auxiliar para publicar mensajes MQTT
publish_mqtt() {
    local topic="$1"
    local message="$2"
    local run_in_bg="${3:-false}"
    
    if [ "$run_in_bg" = "true" ]; then
        mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "$topic" -m "$message" &>/dev/null &
    else
        mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "$topic" -m "$message" &>/dev/null
    fi
}

# Acuse explícito de cada orden para que la consola no confunda un mensaje
# espontáneo con una prueba superada.
publish_ack() {
    local status="$1"
    local command_id="${2:-}"
    local payload
    payload=$(jq -n --arg status "$status" --arg command_id "$command_id" --arg device_id "$DEVICE_ID" \
      '{status: $status, command_id: $command_id, device_id: $device_id, timestamp: now}')
    publish_mqtt "$TOPIC_STATUS" "$payload"
}

# Asegurar que la CPU de Android no entre en reposo profundo
termux-wake-lock

# Definir ruta para el log de posicionamiento pasivo continuo
GPS_LOG="$STATE_DIR/gps_updates.json"
rm -f "$GPS_LOG"

# Iniciar la suscripción pasiva a actualizaciones de ubicación en segundo plano
termux-location -r updates > "$GPS_LOG" 2>/dev/null &
GPS_PID=$!

# Liberar recursos y matar el proceso de GPS/MQTT al salir del script
trap 'echo "[INFO] Liberando recursos, deteniendo GPS y receptor MQTT..."; kill -9 $GPS_PID $SUB_PID 2>/dev/null; pkill -9 -P $SUB_PID 2>/dev/null; stop_recovery_audio; rm -f "$ARMED_FLAG" "$LAUNCH_FLAG"; termux-wake-unlock' EXIT

# Función auxiliar para leer la mejor localización disponible al instante sin bloquear
get_gps_location() {
    local LOC_JSON=""
    # 1. Intentar leer la última posición reportada por el listener pasivo
    if [ -f "$GPS_LOG" ] && [ -s "$GPS_LOG" ]; then
        local TEMP_JSON
        TEMP_JSON=$(tail -n 1 "$GPS_LOG" 2>/dev/null)
        # Verificar que sea un objeto JSON completo válido
        if [[ "$TEMP_JSON" == \{*\} ]]; then
            LOC_JSON="$TEMP_JSON"
        fi
    fi
    # 2. Fallback a caché de red rápida
    if [ -z "$LOC_JSON" ] || [ "$LOC_JSON" = "{}" ]; then
        LOC_JSON=$(timeout 2 termux-location -p network -r last 2>/dev/null)
    fi
    # 3. Fallback a caché de GPS rápida
    if [ -z "$LOC_JSON" ] || [ "$LOC_JSON" = "{}" ]; then
        LOC_JSON=$(timeout 2 termux-location -p gps -r last 2>/dev/null)
    fi
    
    # Asegurar que al menos devolvemos un JSON vacío válido
    if [ -z "$LOC_JSON" ] || [ "$LOC_JSON" = "{}" ] || [[ "$LOC_JSON" != \{*\} ]]; then
        echo "{}"
    else
        echo "$LOC_JSON"
    fi
}

# ------------------------------------------------------------------------------
# DEFINICIÓN DE MANEJADOR DE COMANDOS (T-MINUS & DIAGNÓSTICOS)
# ------------------------------------------------------------------------------
handle_command() {
    local cmd="$1"
    local command_id="${2:-}"
    local audio_id="${3:-}"
    echo "[🤖 COMANDO] Recibido: $cmd"
    
    case "$cmd" in
        "get_status")
            publish_ack "status_received" "$command_id"
            # 1. Obtener estado de batería
            BAT_JSON=$(termux-battery-status 2>/dev/null)
            BAT_LVL=$(echo "$BAT_JSON" | jq -r '.percentage // 0')
            BAT_TEMP=$(echo "$BAT_JSON" | jq -r '.temperature // 0')
            
            # 2. Obtener GPS instantáneo
            LOC_JSON=$(get_gps_location)
            LAT=$(echo "$LOC_JSON" | jq -r '.latitude // "null"')
            LNG=$(echo "$LOC_JSON" | jq -r '.longitude // "null"')
            ALT=$(echo "$LOC_JSON" | jq -r '.altitude // "null"')
            ACC=$(echo "$LOC_JSON" | jq -r '.accuracy // "null"')
            
            # 3. Publicar reporte en topic de estado del dispositivo
            STATUS_PAYLOAD=$(jq -n \
              --argjson lvl "$BAT_LVL" \
              --argjson tmp "$BAT_TEMP" \
              --argjson lat "$LAT" \
              --argjson lng "$LNG" \
              --argjson alt "$ALT" \
              --argjson acc "$ACC" \
              '{status: "diagnostico", level: $lvl, temp: $tmp, lat: $lat, lng: $lng, alt: $alt, accuracy: $acc}')
              
            publish_mqtt "$TOPIC_STATUS" "$STATUS_PAYLOAD"
            ;;
            
        "init_gps")
            echo "[🛰️ GPS] Iniciando receptor GPS..."
            publish_ack "gps_test_started" "$command_id"
            publish_mqtt "$TOPIC_STATUS" '{"status": "gps_initializing"}'
            sleep 2
            LOC_JSON=$(get_gps_location)
            if [ -n "$LOC_JSON" ] && [ "$LOC_JSON" != "{}" ]; then
                LAT=$(echo "$LOC_JSON" | jq -r '.latitude // "null"')
                LNG=$(echo "$LOC_JSON" | jq -r '.longitude // "null"')
                ALT=$(echo "$LOC_JSON" | jq -r '.altitude // "null"')
                ACC=$(echo "$LOC_JSON" | jq -r '.accuracy // "null"')
                
                STATUS_PAYLOAD=$(jq -n \
                  --argjson lat "$LAT" \
                  --argjson lng "$LNG" \
                  --argjson alt "$ALT" \
                  --argjson acc "$ACC" \
                  '{status: "gps_ok", lat: $lat, lng: $lng, alt: $alt, accuracy: $acc}')
                  
                publish_mqtt "$TOPIC_STATUS" "$STATUS_PAYLOAD"
            else
                publish_mqtt "$TOPIC_STATUS" '{"status": "gps_failed"}'
            fi
            ;;
            
        "play_audio")
            case "$audio_id" in
                recovery_alarm) AUDIO_FILE="$ALARM_AUDIO" ;;
                *) publish_ack "audio_rejected_unknown" "$command_id"; return ;;
            esac
            if [ -s "$AUDIO_FILE" ]; then
                if start_recovery_audio; then
                    publish_ack "recovery_alarm_started" "$command_id"
                else
                    publish_ack "audio_playback_failed" "$command_id"
                fi
            else
                publish_ack "audio_rejected_missing_file" "$command_id"
            fi
            ;;

        "stop_audio")
            stop_recovery_audio
            publish_ack "audio_stopped" "$command_id"
            ;;
            
        "test_video_on")
            echo "[📹 VIDEO] Test de vídeo: Iniciando streaming..."
            touch "$VIDEO_FLAG"
            am start -a android.intent.action.VIEW -d "$VDO_NINJA_URL" &>/dev/null
            publish_mqtt "$TOPIC_STATUS" '{"status": "video_streaming_on"}'
            publish_ack "video_preview_started" "$command_id"
            ;;
            
        "test_video_off")
            echo "[📹 VIDEO] Test de vídeo: Deteniendo streaming..."
            rm -f "$VIDEO_FLAG" "$LANDING_FLAG"
            stop_recovery_audio
            stop_video_apps
            publish_mqtt "$TOPIC_STATUS" '{"status": "video_streaming_off"}'
            publish_ack "video_preview_stopped" "$command_id"
            ;;
            
        "test_photo")
            echo "[📸 CÁMARA] Solicitud de test de foto..."
            publish_mqtt "$TOPIC_STATUS" '{"status": "camera_testing"}'
            publish_ack "photo_test_started" "$command_id"
            
            RELAUNCH_VIDEO=0
            if [ -f "$VIDEO_FLAG" ]; then
                RELAUNCH_VIDEO=1
            fi
            
            am force-stop com.android.chrome &>/dev/null
            am force-stop flutter.vdo.ninja &>/dev/null
            # Borrar la foto anterior para no re-subir basura si falla la captura actual
            rm -f "$TARGET_IMG"
            # Esperar 2 segundos para dar tiempo a Android a liberar la cámara física
            sleep 2
            
            termux-camera-photo -c 0 "$TARGET_IMG"
            
            # Reanudar vídeo si estaba activo antes
            if [ "$RELAUNCH_VIDEO" -eq 1 ]; then
                echo "[📹 VIDEO] Reanudando transmisión de vídeo..."
                am start -a android.intent.action.VIEW -d "$VDO_NINJA_URL" &>/dev/null
            fi
            
            if [ -f "$TARGET_IMG" ]; then
                TEXTO_DETECTADO="Captura de verificación de cámara (OK)"
                
                LOC_JSON=$(get_gps_location)
                LAT=$(echo "$LOC_JSON" | jq -r '.latitude // "null"')
                LNG=$(echo "$LOC_JSON" | jq -r '.longitude // "null"')
                ALT=$(echo "$LOC_JSON" | jq -r '.altitude // "null"')
                
                echo "[📸 CÁMARA] Subiendo foto de test a la web..."
                UPLOAD_RESP=$(curl -s --connect-timeout 10 --max-time 30 -F "file=@$TARGET_IMG" -F "texto=$TEXTO_DETECTADO" -F "device_id=$DEVICE_ID" "$IMAGE_SERVER_URL/upload")
                
                if [ $? -eq 0 ] && [ -n "$UPLOAD_RESP" ] && [[ "$UPLOAD_RESP" != *"Error"* ]]; then
                    FILENAME="$UPLOAD_RESP"
                    URL_COMPLETA="$IMAGE_SERVER_URL/images/$FILENAME"
                    
                    PAYLOAD=$(jq -n \
                      --arg txt "$TEXTO_DETECTADO" \
                      --arg url "$URL_COMPLETA" \
                      --argjson lat "$LAT" \
                      --argjson lng "$LNG" \
                      --argjson alt "$ALT" \
                      '{texto: $txt, url_imagen: $url, lat: $lat, lng: $lng, alt: $alt}')
                    
                    publish_mqtt "$TOPIC_CAMERA" "$PAYLOAD"
                else
                    echo "[❌ ERROR] Falló la subida de la foto de test: $UPLOAD_RESP"
                    publish_mqtt "$TOPIC_STATUS" '{"status": "camera_error"}'
                fi
            else
                publish_mqtt "$TOPIC_STATUS" '{"status": "camera_capture_failed"}'
            fi
            ;;
            
        "reboot")
            echo "[⚠️ SISTEMA] Reiniciando el dispositivo móvil..."
            sleep 1
            su -c reboot 2>/dev/null || reboot
            ;;
            
        "arm")
            # ARMAR no inicia el vuelo: deja el dispositivo bloqueado y a la
            # espera de una orden LAUNCH independiente del servidor.
            rm -f "$LAUNCH_FLAG" "$ABORT_FLAG"
            touch "$ARMED_FLAG"
            publish_mqtt "$TOPIC_STATUS" '{"status": "armed"}'
            publish_ack "armed" "$command_id"
            echo "[🛰️ NET] Sonda Armada. Esperando orden de lanzamiento..."
            ;;

        "launch")
            if [ -f "$ARMED_FLAG" ]; then
                touch "$LAUNCH_FLAG"
                publish_mqtt "$TOPIC_STATUS" '{"status": "launched"}'
                publish_ack "launched" "$command_id"
                echo "[🚀 NET] Orden de lanzamiento aceptada."
            else
                publish_ack "launch_rejected_not_armed" "$command_id"
            fi
            ;;
            
        "abort")
            echo "[🚨 ABORTAR] Recibida orden de abortar lanzamiento..."
            rm -f "$ARMED_FLAG"
            rm -f "$LAUNCH_FLAG"
            touch "$ABORT_FLAG"
            rm -f "$VIDEO_FLAG"
            
            # Detener vídeo
            stop_video_apps
            
            sleep 1
            
            publish_mqtt "$TOPIC_STATUS" '{"status": "aborted"}'
            publish_ack "aborted" "$command_id"
            ;;
    esac
}

# ==============================================================================
# FASE 0: ESPERA Y DIAGNÓSTICOS EN RAMPA
# ==============================================================================
echo "====================================================="
echo "  [FASE 0] Iniciando receptor de comandos pre-vuelo..."
echo "  Suscrito a $TOPIC_COMMAND. Esperando diagnóstico..."
echo "====================================================="

rm -f "$ARMED_FLAG"
rm -f "$LAUNCH_FLAG"
rm -f "$VIDEO_FLAG"
rm -f "$LANDING_FLAG"

# Suscriptor MQTT de fondo
(
    while true; do
        # mosquitto_sub termina cuando se corta la red; volver a lanzarlo
        # permite recibir comandos al recuperar la cobertura.
        mosquitto_sub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "$TOPIC_COMMAND" 2>/dev/null | while read -r line; do
            CMD=$(echo "$line" | jq -r '.cmd // empty')
            COMMAND_ID=$(echo "$line" | jq -r '.command_id // empty')
            AUDIO_ID=$(echo "$line" | jq -r '.audio_id // empty')
            if [ -n "$CMD" ]; then
                handle_command "$CMD" "$COMMAND_ID" "$AUDIO_ID" </dev/null &
            fi
        done
        sleep 2
    done
) &
SUB_PID=$!

# Bucle de espera del lanzamiento. El móvil no emite misión ni inicia vídeo
# por su cuenta: solo responde a órdenes explícitas del control.
while [ ! -f "$LAUNCH_FLAG" ]; do
    if [ -f "$ABORT_FLAG" ]; then
        rm -f "$ABORT_FLAG" "$ARMED_FLAG"
        exec "$0" "$@"
    fi
    sleep 1
done

# Borrar flag de armado para estar listos para la secuencia
rm -f "$ARMED_FLAG"
rm -f "$ABORT_FLAG"

# ==============================================================================
# FASE 1: VUELO EN DIRECTO (STREAMING Y MONITOREO DE ALTITUD)
# ==============================================================================
echo "====================================================="
echo "  [FASE 1] ¡IGNICIÓN! Sonda en vuelo."
echo "  Transmitiendo vídeo en directo y telemetría de rampa..."
echo "====================================================="

# Arrancar el vídeo en directo de forma automática en el despegue (cámara trasera, autostart, sin audio y bitrate controlado)
touch "$VIDEO_FLAG"
am start -a android.intent.action.VIEW -d "$VDO_NINJA_URL" &>/dev/null
sleep 2

START_TIME=$(date +%s)
TIMEOUT_SAFETY=600
LAST_FLIGHT_HEARTBEAT_AT=0
LAST_CONNECTIVITY_CHECK_AT=0
LAST_OFFLINE_TELEMETRY_AT=0
COBERTURA=0

while true; do
    # Verificar si el operador ha enviado orden de abortar lanzamiento
    if [ -f "$ABORT_FLAG" ]; then
        echo "[🚨 ABORTAR] Flag de aborto detectado. Limpiando y reiniciando script..."
        rm -f "$ABORT_FLAG"
        rm -f "$VIDEO_FLAG"
        # Detener vídeo
        stop_video_apps
        # Reiniciar script desde cero
        exec "$0" "$@"
    fi

    echo "[$(date +%T)] 📍 Midiendo altitud de vuelo..."
    
    LOC_JSON=$(get_gps_location)
    LAT=$(echo "$LOC_JSON" | jq -r '.latitude // "null"')
    LNG=$(echo "$LOC_JSON" | jq -r '.longitude // "null"')
    ALT=$(echo "$LOC_JSON" | jq -r '.altitude // "null"')
    ACC=$(echo "$LOC_JSON" | jq -r '.accuracy // "null"')
    
    # Preparar telemetría aunque todavía no exista fix GPS.
    GPS_PAYLOAD=$(jq -n \
      --argjson lat "$LAT" \
      --argjson lng "$LNG" \
      --argjson alt "$ALT" \
      --argjson acc "$ACC" \
      '{lat: $lat, lng: $lng, altitude: $alt, accuracy: $acc}')
    NOW=$(date +%s)
    if [ $((NOW - LAST_CONNECTIVITY_CHECK_AT)) -ge "$CONNECTIVITY_CHECK_INTERVAL" ]; then
        if nc -z -w 2 "$MQTT_HOST" "$MQTT_PORT" &>/dev/null; then
            COBERTURA=1
        else
            COBERTURA=0
        fi
        LAST_CONNECTIVITY_CHECK_AT="$NOW"
    fi

    if [ "$COBERTURA" -eq 1 ]; then
        # Con red: telemetría normal cada ciclo (5 s) y heartbeat cada 15 s.
        publish_mqtt "$TOPIC_TELEMETRY" "$GPS_PAYLOAD"
        if [ $((NOW - LAST_FLIGHT_HEARTBEAT_AT)) -ge 15 ]; then
            publish_mqtt "$TOPIC_STATUS" "$(jq -n --arg device_id "$DEVICE_ID" '{status: "heartbeat", device_id: $device_id, timestamp: now}')"
            LAST_FLIGHT_HEARTBEAT_AT="$NOW"
        fi
        echo "[📡 TELEMETRÍA] Enviada: Alt: $ALT m, Acc: $ACC m"
    elif [ $((NOW - LAST_OFFLINE_TELEMETRY_AT)) -ge "$OFFLINE_TELEMETRY_INTERVAL" ]; then
        # Sin red: solo un intento ligero por minuto; nunca bloquea el bucle.
        publish_mqtt "$TOPIC_TELEMETRY" "$GPS_PAYLOAD" true
        LAST_OFFLINE_TELEMETRY_AT="$NOW"
        echo "[📡 TELEMETRÍA] Sin red: intento reducido (cada ${OFFLINE_TELEMETRY_INTERVAL}s)."
    else
        echo "[📡 TELEMETRÍA] Sin red: envío aplazado para ahorrar batería."
    fi
    
    ALT_INT=${ALT%.*}
    if [ -n "$ALT_INT" ] && [ "$ALT_INT" != "null" ]; then
        if [ "$ALT_INT" -gt 1000 ]; then
            echo "[🚀 CONTROL] ¡Cota de 1.000m superada! ($ALT_INT m). Entrando en Fase Autónoma..."
            break
        fi
    fi
    
    CURRENT_TIME=$(date +%s)
    ELAPSED=$((CURRENT_TIME - START_TIME))
    if [ $ELAPSED -gt $TIMEOUT_SAFETY ]; then
        echo "[⚠️ SEGURIDAD] Límite de tiempo de vídeo agotado ($TIMEOUT_SAFETY s). Entrando en Fase Autónoma..."
        break
    fi
    
    sleep 5
done

# Detener retransmisión de vídeo
stop_video_apps
sleep 2

# ==============================================================================
# FASE 2: CAPTURA DE IMÁGENES AUTÓNOMA Y TELEMETRÍA (INTELIGENTE)
# ==============================================================================
echo "====================================================="
echo "  [FASE 2] Iniciando bucle de captura autónoma inteligente..."
echo "  Destino de capturas locales: $PHOTO_DIR"
echo "  Telemetría cada 5s | Fotos cada 60s (si hay cobertura)"
echo "====================================================="

VIDEO_RUNNING=0
CICLO=0
PHOTO_INTERVAL=60  # Intervalo de fotos en segundos
PHOTO_CYCLES=$((PHOTO_INTERVAL / 5))
if [ "$PHOTO_CYCLES" -lt 1 ]; then PHOTO_CYCLES=1; fi

# Detección local de aterrizaje: requiere descenso previo, velocidad baja y
# altitud estable durante varios minutos. Funciona aunque no haya cobertura.
MAX_ALTITUDE=0
DESCENT_DETECTED=0
LAST_ALTITUDE=""
LOW_MOTION_CYCLES=0
LANDING_STABLE_CYCLES=36
LAST_LANDING_STATUS_AT=0
LAST_HEARTBEAT_AT=0

while true; do
    if [ -f "$ABORT_FLAG" ]; then
        rm -f "$ABORT_FLAG" "$LANDING_FLAG"
        stop_recovery_audio
        stop_video_apps
        exec "$0" "$@"
    fi
    # 1. Comprobar conectividad periódicamente, no en cada ciclo de GPS.
    NOW=$(date +%s)
    if [ $((NOW - LAST_CONNECTIVITY_CHECK_AT)) -ge "$CONNECTIVITY_CHECK_INTERVAL" ]; then
        if nc -z -w 2 "$MQTT_HOST" "$MQTT_PORT" &>/dev/null; then
            COBERTURA=1
        else
            COBERTURA=0
        fi
        LAST_CONNECTIVITY_CHECK_AT="$NOW"
    fi

    # Geolocalizar (leído en cada ciclo de 5s)
    LAT="null"
    LNG="null"
    ALT="null"
    ACC="null"
    LOC_JSON=$(get_gps_location)
    if [ -n "$LOC_JSON" ] && [ "$LOC_JSON" != "{}" ]; then
        LAT=$(echo "$LOC_JSON" | jq -r '.latitude // "null"')
        LNG=$(echo "$LOC_JSON" | jq -r '.longitude // "null"')
        ALT=$(echo "$LOC_JSON" | jq -r '.altitude // "null"')
        ACC=$(echo "$LOC_JSON" | jq -r '.accuracy // "null"')
    fi

    ALT_NUM=$(awk "BEGIN { if (\"$ALT\" == \"null\") print 0; else print $ALT + 0 }")
    PREVIOUS_MAX_ALTITUDE="$MAX_ALTITUDE"
    if awk "BEGIN { exit !($ALT_NUM > $MAX_ALTITUDE) }"; then
        MAX_ALTITUDE="$ALT_NUM"
    fi
    if awk "BEGIN { exit !($PREVIOUS_MAX_ALTITUDE > 1000 && $ALT_NUM < ($PREVIOUS_MAX_ALTITUDE - 50)) }"; then
        DESCENT_DETECTED=1
    fi
    SPEED_NUM=$(echo "$LOC_JSON" | jq -r '.speed // 999' 2>/dev/null)
    if [ "$SPEED_NUM" = "null" ] || ! [[ "$SPEED_NUM" =~ ^[0-9]+([.][0-9]+)?$ ]]; then SPEED_NUM=999; fi
    if [ -z "$LAST_ALTITUDE" ]; then
        ALT_STEP=999
    else
        ALT_STEP=$(awk "BEGIN { d=$ALT_NUM-$LAST_ALTITUDE; if (d<0) d=-d; print d }")
    fi
    LAST_ALTITUDE="$ALT_NUM"
    if awk "BEGIN { exit !($DESCENT_DETECTED == 1 && $ALT_STEP < 15 && $SPEED_NUM < 3) }"; then
        LOW_MOTION_CYCLES=$((LOW_MOTION_CYCLES + 1))
    else
        LOW_MOTION_CYCLES=0
    fi
    if [ "$LOW_MOTION_CYCLES" -ge "$LANDING_STABLE_CYCLES" ] && [ ! -f "$LANDING_FLAG" ]; then
        touch "$LANDING_FLAG"
        publish_mqtt "$TOPIC_STATUS" "$(jq -n --argjson alt "$ALT_NUM" '{status: "landed", alt: $alt, alarm: "starting"}')"
        if start_recovery_audio; then
            publish_ack "recovery_alarm_started"
        else
            publish_ack "recovery_alarm_missing_audio"
        fi
    fi

    # 2. Gestión dinámica de conectividad en vuelo
    if [ "$COBERTURA" -eq 1 ]; then
        # Heartbeat explícito: permite al servidor distinguir presencia móvil
        # de la telemetría y detectar la recuperación de la comunicación.
        NOW=$(date +%s)
        if [ $((NOW - LAST_HEARTBEAT_AT)) -ge 15 ]; then
            publish_mqtt "$TOPIC_STATUS" "$(jq -n --arg device_id "$DEVICE_ID" '{status: "heartbeat", device_id: $device_id, timestamp: now}')"
            LAST_HEARTBEAT_AT="$NOW"
        fi
        # Si aterrizó sin cobertura, repetir periódicamente el evento hasta
        # que la consola pueda pasar a recuperación.
        if [ -f "$LANDING_FLAG" ]; then
            NOW=$(date +%s)
            if [ $((NOW - LAST_LANDING_STATUS_AT)) -ge 60 ]; then
                publish_mqtt "$TOPIC_STATUS" "$(jq -n --argjson alt "$ALT_NUM" '{status: "landed", alt: $alt, alarm: "active"}')" true
                LAST_LANDING_STATUS_AT="$NOW"
            fi
        fi
        # Con cobertura: Si el vídeo estaba apagado, lo encendemos para el directo
        if [ "$VIDEO_RUNNING" -eq 0 ]; then
            echo "[🛰️ NET] Conexión recuperada. Reanudando vídeo en directo..."
            am start -a android.intent.action.VIEW -d "$VDO_NINJA_URL" &>/dev/null
            VIDEO_RUNNING=1
            publish_mqtt "$TOPIC_STATUS" '{"status": "video_streaming_on", "reason": "connection_recovered"}'
            sleep 2
        fi

        # Enviar telemetría continua de alta velocidad (cada 5s)
        BAT_STATUS=$(termux-battery-status)
        BAT_LEVEL=$(echo "$BAT_STATUS" | jq -r '.percentage // 100')
        BAT_TEMP=$(echo "$BAT_STATUS" | jq -r '.temperature // 25')

        PAYLOAD=$(jq -n \
          --argjson level "$BAT_LEVEL" \
          --argjson temp "$BAT_TEMP" \
          --argjson lat "$LAT" \
          --argjson lng "$LNG" \
          --argjson alt "$ALT" \
          --argjson accuracy "$ACC" \
          '{"status": "diagnostico", "level": $level, "temp": $temp, "lat": $lat, "lng": $lng, "alt": $alt, "accuracy": $accuracy}')

        publish_mqtt "$TOPIC_STATUS" "$PAYLOAD" true
        echo "[🛰️ NET] [$(date +%T)] Telemetría enviada por MQTT."
    else
        # Sin cobertura: Si el directo de Chrome está corriendo, lo matamos para salvar batería
        # Forzar un heartbeat inmediato en cuanto vuelva la conexión.
        LAST_HEARTBEAT_AT=0
        if [ "$VIDEO_RUNNING" -eq 1 ]; then
            echo "[🛰️ NET] Conexión perdida. Apagando vídeo para conservar batería..."
            stop_video_apps
            VIDEO_RUNNING=0
        fi
    fi

    # 3. Captura y registro de fotos en alta resolución (cada 60 segundos)
    if [ $((CICLO % PHOTO_CYCLES)) -eq 0 ]; then
        echo "[$(date +%T)] 📸 Capturando frame autónomo de alta resolución..."

        # Si la cámara física está ocupada por el directo, pausar Chrome 2s
        if [ "$VIDEO_RUNNING" -eq 1 ]; then
            am force-stop com.android.chrome &>/dev/null
            am force-stop flutter.vdo.ninja &>/dev/null
            sleep 2
        fi

        rm -f "$TARGET_IMG"
        termux-camera-photo -c 0 "$TARGET_IMG"

        # Reanudar directo tras el disparo si debe seguir activo
        if [ "$VIDEO_RUNNING" -eq 1 ]; then
            am start -a android.intent.action.VIEW -d "$VDO_NINJA_URL" &>/dev/null
        fi

        if [ -f "$TARGET_IMG" ]; then
            # Guardar copia física con timestamp en el almacenamiento local del teléfono
            TIMESTAMP=$(date +%Y%m%d_%H%M%S)
            LOCAL_COPY="$PHOTO_DIR/sonda_$TIMESTAMP.jpg"
            cp "$TARGET_IMG" "$LOCAL_COPY"

            TEXTO_DETECTADO="Captura autónoma - Altitud: $ALT m"

            if [ "$COBERTURA" -eq 1 ]; then
                echo "[$(date +%T)] 📤 Subiendo foto original al servidor..."
                UPLOAD_RESP=$(curl -s --connect-timeout 10 --max-time 30 -F "file=@$TARGET_IMG" -F "texto=$TEXTO_DETECTADO" -F "device_id=$DEVICE_ID" "$IMAGE_SERVER_URL/upload")

                if [ $? -eq 0 ] && [ -n "$UPLOAD_RESP" ] && [[ "$UPLOAD_RESP" != *"Error"* ]]; then
                    FILENAME="$UPLOAD_RESP"
                    URL_COMPLETA="$IMAGE_SERVER_URL/images/$FILENAME"
                    echo "[✅ OK] Subida exitosa: $URL_COMPLETA"

                    PAYLOAD=$(jq -n \
                      --arg txt "$TEXTO_DETECTADO" \
                      --arg url "$URL_COMPLETA" \
                      --argjson lat "$LAT" \
                      --argjson lng "$LNG" \
                      --argjson alt "$ALT" \
                      '{texto: $txt, url_imagen: $url, lat: $lat, lng: $lng, alt: $alt}')

                    publish_mqtt "$TOPIC_CAMERA" "$PAYLOAD"
                else
                    echo "[❌ ERROR] Falló la subida de foto: $UPLOAD_RESP"
                    echo "[$(date +%Y-%m-%d\ %H:%M:%S)] [OFFLINE_ERR] Lat: $LAT, Lng: $LNG, Alt: $ALT, Archivo: sonda_$TIMESTAMP.jpg" >> "$OFFLINE_LOG"
                fi
            else
                echo "[🛰️ NET] Sin cobertura. Guardada localmente: sonda_$TIMESTAMP.jpg"
                echo "[$(date +%Y-%m-%d\ %H:%M:%S)] [OFFLINE_SAVE] Lat: $LAT, Lng: $LNG, Alt: $ALT, Archivo: sonda_$TIMESTAMP.jpg" >> "$OFFLINE_LOG"
            fi
        fi
    fi

    sleep 5
    CICLO=$((CICLO + 1))
done
