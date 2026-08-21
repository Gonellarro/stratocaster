#!/data/data/com.termux/files/usr/bin/bash

# ==============================================================================
# ORQUESTRADOR MULTI-FASE SIMPLIFICADO DE LA SONDA (STRATOCASTER)
# Fase 0: Pruebas y Espera en Rampa
# Fase 1: Vuelo en Directo (vídeo y telemetría MQTT)
# La recuperación queda reservada a una orden explícita del control.
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
RECOVERY_FLAG="$STATE_DIR/sonda.recovery"

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
for cmd in termux-camera-photo termux-wake-lock termux-wake-unlock mosquitto_pub mosquitto_sub jq timeout termux-battery-status termux-location termux-media-player; do
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
RECOVERY_DATA_INTERVAL="${RECOVERY_DATA_INTERVAL:-60}"

# Una posición GPS se considera válida para vuelo cuando procede del receptor
# GNSS, no está obsoleta y su radio de precisión es razonable. No se acepta la
# ubicación de red porque puede desplazar la sonda cientos de metros.
GPS_MAX_ACCURACY_METERS="${GPS_MAX_ACCURACY_METERS:-75}"
GPS_MAX_AGE_MS="${GPS_MAX_AGE_MS:-120000}"
# Un receptor GNSS puede necesitar decenas de segundos para recuperar un fix,
# especialmente tras arrancar o después de estar bajo techo.
GPS_FIX_TIMEOUT_SECONDS="${GPS_FIX_TIMEOUT_SECONDS:-45}"

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

# Prueba extremo a extremo: conexión, autenticación, publicación y ACK del
# broker. No se usa nc porque puede dar falsos negativos al cambiar de red.
mqtt_connection_available() {
    local heartbeat_payload
    heartbeat_payload=$(jq -nc --arg device_id "$DEVICE_ID" \
        '{status:"heartbeat", device_id:$device_id, timestamp:now}')
    timeout 5s mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" \
        -u "$MQTT_USER" -P "$MQTT_PASS" \
        -t "$TOPIC_STATUS" -m "$heartbeat_payload" -q 1 &>/dev/null
}

enter_recovery_mode() {
    touch "$LANDING_FLAG" "$RECOVERY_FLAG"
    rm -f "$VIDEO_FLAG"
    stop_video_apps
    if start_recovery_audio; then
        publish_mqtt "$TOPIC_STATUS" '{"status":"landed","alarm":"starting","source":"command"}' true
        publish_ack "recovery_alarm_started"
    else
        publish_ack "recovery_alarm_missing_audio"
    fi
    echo "[FASE 4] Recuperación activa: vídeo detenido y baliza encendida."

    local last_recovery_status=0
    local last_recovery_probe=0
    local recovery_online=0
    while true; do
        if [ -f "$ABORT_FLAG" ]; then
            echo "[FASE 4] Orden de aborto recibida. Volviendo a espera."
            rm -f "$ABORT_FLAG" "$RECOVERY_FLAG" "$LANDING_FLAG"
            stop_recovery_audio
            exec "$0" "$@"
        fi

        local now
        now=$(date +%s)
        if [ $((now - last_recovery_probe)) -ge "$CONNECTIVITY_CHECK_INTERVAL" ]; then
            if mqtt_connection_available; then
                recovery_online=1
            else
                recovery_online=0
            fi
            last_recovery_probe="$now"
        fi

        # La Fase 4 trabaja siempre a baja frecuencia: posición y foto cada
        # minuto. Sin red se conservan localmente y se reintentan al volver.
        if [ $((now - last_recovery_status)) -ge "$RECOVERY_DATA_INTERVAL" ]; then
            local loc_json lat lng alt acc battery_json battery_level battery_temp payload
            loc_json=$(get_gps_location)
            lat=$(echo "$loc_json" | jq -r '.latitude // "null"')
            lng=$(echo "$loc_json" | jq -r '.longitude // "null"')
            alt=$(echo "$loc_json" | jq -r '.altitude // "null"')
            acc=$(echo "$loc_json" | jq -r '.accuracy // "null"')
            battery_json=$(termux-battery-status 2>/dev/null)
            battery_level=$(echo "$battery_json" | jq -r '.percentage // 0')
            battery_temp=$(echo "$battery_json" | jq -r '.temperature // 0')
            payload=$(jq -n \
                --argjson lat "$lat" --argjson lng "$lng" \
                --argjson alt "$alt" --argjson accuracy "$acc" \
                --argjson level "$battery_level" --argjson temp "$battery_temp" \
                '{status:"recovery_telemetry", lat:$lat, lng:$lng, altitude:$alt, accuracy:$accuracy, level:$level, temp:$temp}')

            if [ "$recovery_online" -eq 1 ]; then
                publish_mqtt "$TOPIC_TELEMETRY" "$payload"
                publish_mqtt "$TOPIC_STATUS" "$(jq -n --argjson lat "$lat" --argjson lng "$lng" --argjson alt "$alt" '{status:"landed", alarm:"active", source:"recovery", lat:$lat, lng:$lng, alt:$alt}')"
                echo "[FASE 4] Posición enviada. Capturando foto de recuperación..."
            else
                echo "[FASE 4] Sin red: posición y foto guardadas localmente."
                echo "[$(date +%Y-%m-%d\ %H:%M:%S)] [RECOVERY_OFFLINE] Lat: $lat, Lng: $lng, Alt: $alt" >> "$OFFLINE_LOG"
            fi

            capture_recovery_photo "$lat" "$lng" "$alt" "$recovery_online"
            last_recovery_status="$now"
        fi
        sleep 5
    done
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

# Iniciar el receptor GNSS explícitamente: sin -p gps Android puede entregar
# una posición de red/fusionada de cientos de metros de error. termux-location
# imprime JSON multilínea; jq lo compacta a una línea por fix para poder leer
# siempre el último objeto completo con tail -n 1.
termux-location -p gps -r updates 2>/dev/null | jq -c --unbuffered . > "$GPS_LOG" &
GPS_PID=$!

# Liberar recursos y matar el proceso de GPS/MQTT al salir del script
trap 'echo "[INFO] Liberando recursos, deteniendo GPS y receptor MQTT..."; kill -9 $GPS_PID $SUB_PID 2>/dev/null; pkill -9 -P $SUB_PID 2>/dev/null; stop_recovery_audio; rm -f "$ARMED_FLAG" "$LAUNCH_FLAG"; termux-wake-unlock' EXIT

# Determina si el JSON contiene un fix GNSS reciente y suficientemente preciso.
is_usable_gps_fix() {
    local location_json="$1"
    echo "$location_json" | jq -e \
        --argjson max_accuracy "$GPS_MAX_ACCURACY_METERS" \
        --argjson max_age "$GPS_MAX_AGE_MS" \
        '(.provider == "gps") and
         (.latitude != null) and (.longitude != null) and
         (.accuracy != null) and (.accuracy <= $max_accuracy) and
         ((.elapsedMs == null) or (.elapsedMs <= $max_age))' >/dev/null 2>&1
}

# Función auxiliar para leer la mejor localización disponible al instante sin bloquear.
# Solo se acepta GPS GNSS reciente: una posición de red de 200 m puede situar
# la sonda a cientos de metros y es peor que conservar la última posición buena.
get_gps_location() {
    local LOC_JSON=""
    local TEMP_JSON=""
    # 1. Intentar leer la última posición reportada por el listener pasivo
    if [ -f "$GPS_LOG" ] && [ -s "$GPS_LOG" ]; then
        TEMP_JSON=$(tail -n 1 "$GPS_LOG" 2>/dev/null)
        if [[ "$TEMP_JSON" == \{*\} ]] && is_usable_gps_fix "$TEMP_JSON"; then
            LOC_JSON="$TEMP_JSON"
        fi
    fi
    # 2. Fallback a caché GPS. Aún es preferible a cualquier estimación de red.
    if [ -z "$LOC_JSON" ] || [ "$LOC_JSON" = "{}" ]; then
        TEMP_JSON=$(timeout 5 termux-location -p gps -r last 2>/dev/null)
        if is_usable_gps_fix "$TEMP_JSON"; then
            LOC_JSON="$TEMP_JSON"
        fi
    fi
    # Sin un fix GNSS válido devolvemos vacío. Los consumidores no moverán el
    # marcador y mantendrán la última coordenada GPS conocida.
    if [ -z "$LOC_JSON" ] || [ "$LOC_JSON" = "{}" ] || [[ "$LOC_JSON" != \{*\} ]]; then
        echo "{}"
    else
        echo "$LOC_JSON"
    fi
}

# Espera de forma acotada a un fix GNSS válido. No acepta posiciones de red:
# es preferible informar de que aún no hay fix antes que publicar una posición
# desplazada cientos de metros.
wait_for_gps_fix() {
    local deadline now location_json
    deadline=$(( $(date +%s) + GPS_FIX_TIMEOUT_SECONDS ))
    while true; do
        location_json=$(get_gps_location)
        if [ "$location_json" != "{}" ]; then
            echo "$location_json"
            return 0
        fi
        now=$(date +%s)
        if [ "$now" -ge "$deadline" ]; then
            echo "{}"
            return 1
        fi
        sleep 2
    done
}

# Captura de Fase 4. Siempre conserva una copia local; solo intenta subirla
# cuando el sondeo MQTT ya ha confirmado que la red está disponible.
capture_recovery_photo() {
    local lat="$1"
    local lng="$2"
    local alt="$3"
    local online="$4"
    local timestamp local_copy description upload_response filename image_url camera_payload

    rm -f "$TARGET_IMG"
    if ! timeout 20s termux-camera-photo -c 0 "$TARGET_IMG"; then
        echo "[FASE 4] No se pudo capturar la foto de recuperación."
        return 1
    fi
    if [ ! -s "$TARGET_IMG" ]; then
        echo "[FASE 4] La cámara no generó una foto de recuperación."
        return 1
    fi

    timestamp=$(date +%Y%m%d_%H%M%S)
    local_copy="$PHOTO_DIR/recuperacion_$timestamp.jpg"
    cp "$TARGET_IMG" "$local_copy"
    description="Captura de recuperación - Altitud: $alt m"

    if [ "$online" -ne 1 ]; then
        echo "[FASE 4] Foto guardada localmente: $(basename "$local_copy")"
        return 0
    fi

    upload_response=$(curl -s --connect-timeout 10 --max-time 30 \
        -F "file=@$TARGET_IMG" -F "texto=$description" -F "device_id=$DEVICE_ID" \
        "$IMAGE_SERVER_URL/upload")
    if [ $? -ne 0 ] || [ -z "$upload_response" ] || [[ "$upload_response" == *"Error"* ]]; then
        echo "[FASE 4] No se pudo subir la foto; queda guardada localmente."
        echo "[$(date +%Y-%m-%d\ %H:%M:%S)] [RECOVERY_UPLOAD_ERR] Lat: $lat, Lng: $lng, Alt: $alt, Archivo: $(basename "$local_copy")" >> "$OFFLINE_LOG"
        return 1
    fi

    filename="$upload_response"
    image_url="$IMAGE_SERVER_URL/images/$filename"
    camera_payload=$(jq -n \
        --arg txt "$description" --arg url "$image_url" \
        --argjson lat "$lat" --argjson lng "$lng" --argjson alt "$alt" \
        '{texto:$txt, url_imagen:$url, lat:$lat, lng:$lng, alt:$alt, status:"recovery_photo"}')
    publish_mqtt "$TOPIC_CAMERA" "$camera_payload"
    echo "[FASE 4] Foto de recuperación enviada: $image_url"
}

# ------------------------------------------------------------------------------
# DEFINICIÓN DE MANEJADOR DE COMANDOS (T-MINUS & DIAGNÓSTICOS)
# ------------------------------------------------------------------------------
handle_command() {
    local cmd="$1"
    local command_id="${2:-}"
    local audio_id="${3:-}"
    local expires_at="${4:-}"
    local expires_seconds

    # Los comandos de misión no se retienen en MQTT: una orden atrasada no
    # debe ejecutarse al recuperar cobertura. Si en el futuro se cambia la
    # entrega, esta comprobación mantiene la misma garantía de seguridad.
    if [[ "$expires_at" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
        expires_seconds="${expires_at%%.*}"
        if [ "$(date +%s)" -gt "$expires_seconds" ]; then
            echo "[🤖 COMANDO] Ignorado por caducidad: $cmd"
            publish_ack "command_expired" "$command_id"
            return
        fi
    fi

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
            publish_mqtt "$TOPIC_STATUS" "$(jq -n --argjson timeout "$GPS_FIX_TIMEOUT_SECONDS" '{status:"gps_initializing", timeout_seconds:$timeout}')"
            LOC_JSON=$(wait_for_gps_fix)
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

        "recovery")
            echo "[RECUPERACIÓN] Orden recibida: entrando en fase de tierra..."
            touch "$RECOVERY_FLAG"
            rm -f "$VIDEO_FLAG"
            stop_video_apps
            publish_ack "recovery_requested" "$command_id"
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
rm -f "$RECOVERY_FLAG"

# Suscriptor MQTT de fondo
(
    while true; do
        # mosquitto_sub termina cuando se corta la red; volver a lanzarlo
        # permite recibir comandos al recuperar la cobertura.
        echo "[MQTT] Escuchando órdenes en $TOPIC_COMMAND..."
        mosquitto_sub \
            -h "$MQTT_HOST" -p "$MQTT_PORT" \
            -u "$MQTT_USER" -P "$MQTT_PASS" \
            -i "sonda-${DEVICE_ID}-commands" -k 20 \
            -t "$TOPIC_COMMAND" | while read -r line; do
            CMD=$(echo "$line" | jq -r '.cmd // empty')
            COMMAND_ID=$(echo "$line" | jq -r '.command_id // empty')
            AUDIO_ID=$(echo "$line" | jq -r '.audio_id // empty')
            EXPIRES_AT=$(echo "$line" | jq -r '.expires_at // empty')
            if [ -n "$CMD" ]; then
                handle_command "$CMD" "$COMMAND_ID" "$AUDIO_ID" "$EXPIRES_AT" </dev/null &
            fi
        done
        echo "[MQTT] Suscripción perdida; reintentando en 2 segundos..."
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
# FASE 1: VUELO EN DIRECTO (VÍDEO Y TELEMETRÍA MQTT)
# ==============================================================================
echo "====================================================="
echo "  [FASE 1] ¡IGNICIÓN! Sonda en vuelo."
echo "  Transmitiendo vídeo en directo y telemetría continua..."
echo "====================================================="

# Arrancar el vídeo en directo de forma automática en el despegue (cámara trasera, autostart, sin audio y bitrate controlado)
touch "$VIDEO_FLAG"
am start -a android.intent.action.VIEW -d "$VDO_NINJA_URL" &>/dev/null
sleep 2

LAST_CONNECTIVITY_CHECK_AT=0
LAST_OFFLINE_TELEMETRY_AT=0
COBERTURA=-1

while true; do
    if [ -f "$RECOVERY_FLAG" ]; then
        enter_recovery_mode
    fi
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

    NOW=$(date +%s)
    if [ $((NOW - LAST_CONNECTIVITY_CHECK_AT)) -ge "$CONNECTIVITY_CHECK_INTERVAL" ]; then
        if mqtt_connection_available; then
            if [ "$COBERTURA" -ne 1 ]; then
                echo "[🛰️ NET] MQTT confirmado. Activando perfil normal."
            fi
            COBERTURA=1
        else
            if [ "$COBERTURA" -ne 0 ]; then
                echo "[🛰️ NET] MQTT no disponible. Activando perfil de bajo consumo."
            fi
            COBERTURA=0
        fi
        LAST_CONNECTIVITY_CHECK_AT="$NOW"
    fi

    # Sin cobertura no se despierta el GPS cada 5 s: se mantiene el sondeo de
    # red cada 15 s, pero la medición y el intento MQTT se reducen a 60 s.
    if [ "$COBERTURA" -eq 0 ] && [ $((NOW - LAST_OFFLINE_TELEMETRY_AT)) -lt "$OFFLINE_TELEMETRY_INTERVAL" ]; then
        sleep 5
        continue
    fi

    echo "[$(date +%T)] 📍 Midiendo altitud de vuelo..."

    LOC_JSON=$(get_gps_location)
    LAT=$(echo "$LOC_JSON" | jq -r '.latitude // "null"')
    LNG=$(echo "$LOC_JSON" | jq -r '.longitude // "null"')
    ALT=$(echo "$LOC_JSON" | jq -r '.altitude // "null"')
    ACC=$(echo "$LOC_JSON" | jq -r '.accuracy // "null"')

    # Preparar telemetría aunque todavía no exista fix GPS. La batería y la
    # temperatura viajan en el mismo topic para que Grafana tenga una fuente
    # de telemetría de vuelo única (sin depender del topic de diagnóstico).
    BAT_STATUS=$(termux-battery-status 2>/dev/null || true)
    BAT_LEVEL=$(echo "$BAT_STATUS" | jq -r '.percentage // 0' 2>/dev/null || echo 0)
    BAT_TEMP=$(echo "$BAT_STATUS" | jq -r '.temperature // 0' 2>/dev/null || echo 0)
    [[ "$BAT_LEVEL" =~ ^[0-9]+([.][0-9]+)?$ ]] || BAT_LEVEL=0
    [[ "$BAT_TEMP" =~ ^-?[0-9]+([.][0-9]+)?$ ]] || BAT_TEMP=0

    GPS_PAYLOAD=$(jq -n \
      --argjson lat "$LAT" \
      --argjson lng "$LNG" \
      --argjson alt "$ALT" \
      --argjson acc "$ACC" \
      --argjson level "$BAT_LEVEL" \
      --argjson temp "$BAT_TEMP" \
      '{lat: $lat, lng: $lng, altitude: $alt, accuracy: $acc, level: $level, temp: $temp}')

    if [ "$COBERTURA" -eq 1 ]; then
        # Con red: telemetría normal cada ciclo (5 s). El sondeo MQTT de los
        # 15 s ya publica el heartbeat confirmado con QoS 1.
        publish_mqtt "$TOPIC_TELEMETRY" "$GPS_PAYLOAD"
        echo "[📡 TELEMETRÍA] Enviada: Alt: $ALT m, Acc: $ACC m"
    else
        # Sin red: solo un intento ligero por minuto; nunca bloquea el bucle.
        publish_mqtt "$TOPIC_TELEMETRY" "$GPS_PAYLOAD" true
        LAST_OFFLINE_TELEMETRY_AT="$NOW"
        echo "[📡 TELEMETRÍA] Sin red: intento reducido (cada ${OFFLINE_TELEMETRY_INTERVAL}s)."
    fi

    sleep 5
done
