#!/data/data/com.termux/files/usr/bin/bash

# ==============================================================================
# ORQUESTRADOR MULTI-FASE SIMPLIFICADO DE LA SONDA (STRATOCASTER)
# Fase 0: Pruebas y Espera en Rampa
# Fase 1: Vuelo en Directo (Streaming SRT)
# Fase 2: Bucle Autónomo de Transmisión Directa (Captura y GPS)
# ==============================================================================

# RUTAS DE CAPTURA Y TELEMETRÍA
TARGET_IMG="$HOME/imagenes/foto.jpg"
OFFLINE_LOG="$HOME/imagenes/sonda_offline.log"
ARMED_FLAG="$HOME/imagenes/sonda.armed"
ABORT_FLAG="$HOME/imagenes/sonda.abort"
VIDEO_FLAG="$HOME/imagenes/sonda.video"


# Cargar variables de entorno y credenciales privadas desde 'sonda.env' si existe
CONFIG_FILE="$(dirname "$0")/sonda.env"
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
fi

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
mkdir -p "$HOME/imagenes"

# Verificar dependencias críticas de Termux y herramientas
for cmd in termux-camera-photo termux-wake-lock termux-wake-unlock mosquitto_pub mosquitto_sub jq termux-battery-status termux-location termux-tts-speak; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "[❌ ERROR] El comando '$cmd' no está instalado en Termux."
        exit 1
    fi
done

# Tiempo de bucle de fotos en fase autónoma
TIEMPO=10

# Asegurar que la CPU de Android no entre en reposo profundo
termux-wake-lock

# Definir ruta para el log de posicionamiento pasivo continuo
GPS_LOG="$HOME/imagenes/gps_updates.json"
rm -f "$GPS_LOG"

# Iniciar la suscripción pasiva a actualizaciones de ubicación en segundo plano
termux-location -r updates > "$GPS_LOG" 2>/dev/null &
GPS_PID=$!

# Liberar recursos y matar el proceso de GPS al salir del script
trap 'echo "[INFO] Liberando recursos y deteniendo GPS pasivo..."; kill -9 $GPS_PID 2>/dev/null; rm -f "$ARMED_FLAG"; termux-wake-unlock' EXIT

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
    echo "[🤖 COMANDO] Recibido: $cmd"
    
    case "$cmd" in
        "get_status")
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
              
            mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "$TOPIC_STATUS" -m "$STATUS_PAYLOAD"
            ;;
            
        "init_gps")
            echo "[🛰️ GPS] Iniciando receptor GPS..."
            mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "$TOPIC_STATUS" -m '{"status": "gps_initializing"}'
            timeout 5 termux-tts-speak "Iniciando búsqueda de satélites GPS." 2>/dev/null
            
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
                  
                mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "$TOPIC_STATUS" -m "$STATUS_PAYLOAD"
                timeout 5 termux-tts-speak "Señal de GPS fijada correctamente." 2>/dev/null
            else
                mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "$TOPIC_STATUS" -m '{"status": "gps_failed"}'
                timeout 5 termux-tts-speak "Error al fijar señal de GPS." 2>/dev/null
            fi
            ;;
            
        "test_audio")
            mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "$TOPIC_STATUS" -m '{"status": "audio_ok"}'
            timeout 5 termux-tts-speak "Sonda en línea y lista para la comprobación." 2>/dev/null
            ;;
            
        "test_video_on")
            echo "[📹 VIDEO] Test de vídeo: Iniciando streaming..."
            touch "$VIDEO_FLAG"
            am start -a android.intent.action.VIEW -d "https://vdo.ninja/?push=sonda_stratocaster&webcam&facing=back&autostart&noaudio&videobitrate=1000&quality=2&nopreview&clean" &>/dev/null
            mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "$TOPIC_STATUS" -m '{"status": "video_streaming_on"}'
            ;;
            
        "test_video_off")
            echo "[📹 VIDEO] Test de vídeo: Deteniendo streaming..."
            rm -f "$VIDEO_FLAG"
            am force-stop flutter.vdo.ninja &>/dev/null
            am force-stop com.android.chrome &>/dev/null
            am force-stop com.wmspanel.larix_broadcaster &>/dev/null
            mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "$TOPIC_STATUS" -m '{"status": "video_streaming_off"}'
            ;;
            
        "test_photo")
            echo "[📸 CÁMARA] Solicitud de test de foto..."
            mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "$TOPIC_STATUS" -m '{"status": "camera_testing"}'
            
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
                am start -a android.intent.action.VIEW -d "https://vdo.ninja/?push=sonda_stratocaster&webcam&facing=back&autostart&noaudio&videobitrate=1000&quality=2&nopreview&clean&forcelandscape" &>/dev/null
            fi
            
            if [ -f "$TARGET_IMG" ]; then
                TEXTO_DETECTADO="Captura de verificación de cámara (OK)"
                
                LOC_JSON=$(get_gps_location)
                LAT=$(echo "$LOC_JSON" | jq -r '.latitude // "null"')
                LNG=$(echo "$LOC_JSON" | jq -r '.longitude // "null"')
                ALT=$(echo "$LOC_JSON" | jq -r '.altitude // "null"')
                
                echo "[📸 CÁMARA] Subiendo foto de test a la web..."
                UPLOAD_RESP=$(curl -s -F "file=@$TARGET_IMG" -F "texto=$TEXTO_DETECTADO" -F "device_id=$DEVICE_ID" "$IMAGE_SERVER_URL/upload")
                
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
                    
                    mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "$TOPIC_CAMERA" -m "$PAYLOAD"
                    timeout 5 termux-tts-speak "Comprobación de cámara completada con éxito." 2>/dev/null
                else
                    echo "[❌ ERROR] Falló la subida de la foto de test: $UPLOAD_RESP"
                    mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "$TOPIC_STATUS" -m '{"status": "camera_error"}'
                fi
            else
                mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "$TOPIC_STATUS" -m '{"status": "camera_capture_failed"}'
            fi
            ;;
            
        "reboot")
            echo "[⚠️ SISTEMA] Reiniciando el dispositivo móvil..."
            timeout 5 termux-tts-speak "Reiniciando el sistema de la sonda." 2>/dev/null
            sleep 1
            su -c reboot 2>/dev/null || reboot
            ;;
            
        "arm")
            # 1. Notificar armado por MQTT
            mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "$TOPIC_STATUS" -m '{"status": "armed"}'
            
            echo "[🛰️ NET] Sonda Armada. Esperando cuenta atrás..."
            timeout 5 termux-tts-speak "Sonda Armada. Lista para el lanzamiento." 2>/dev/null
            sleep 1
            
            # 2. Crear flag para salir del bucle de espera
            touch "$ARMED_FLAG"
            ;;
            
        "abort")
            echo "[🚨 ABORTAR] Recibida orden de abortar lanzamiento..."
            rm -f "$ARMED_FLAG"
            touch "$ABORT_FLAG"
            rm -f "$VIDEO_FLAG"
            
            # Detener vídeo
            am force-stop flutter.vdo.ninja &>/dev/null
            am force-stop com.android.chrome &>/dev/null
            am force-stop com.wmspanel.larix_broadcaster &>/dev/null
            
            timeout 5 termux-tts-speak "Lanzamiento abortado. Volviendo a modo de espera." 2>/dev/null
            sleep 1
            
            mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "$TOPIC_STATUS" -m '{"status": "aborted"}'
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
rm -f "$VIDEO_FLAG"

# Suscriptor MQTT de fondo
(
    mosquitto_sub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "$TOPIC_COMMAND" 2>/dev/null | while read -r line; do
        CMD=$(echo "$line" | jq -r '.cmd // empty')
        if [ -n "$CMD" ]; then
            handle_command "$CMD" </dev/null &
        fi
    done
) &
SUB_PID=$!

# Bucle de espera del armado (con telemetría periódica cada 10 segundos)
COUNTER=0
while [ ! -f "$ARMED_FLAG" ]; do
    if [ $((COUNTER % 10)) -eq 0 ]; then
        handle_command "get_status" &>/dev/null &
    fi
    sleep 1
    COUNTER=$((COUNTER + 1))
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
am start -a android.intent.action.VIEW -d "https://vdo.ninja/?push=sonda_stratocaster&webcam&facing=back&autostart&noaudio&videobitrate=1000&quality=2&nopreview&clean&forcelandscape" &>/dev/null
sleep 2

START_TIME=$(date +%s)
TIMEOUT_SAFETY=600

while true; do
    # Verificar si el operador ha enviado orden de abortar lanzamiento
    if [ -f "$ABORT_FLAG" ]; then
        echo "[🚨 ABORTAR] Flag de aborto detectado. Limpiando y reiniciando script..."
        rm -f "$ABORT_FLAG"
        rm -f "$VIDEO_FLAG"
        # Detener vídeo
        am force-stop flutter.vdo.ninja &>/dev/null
        am force-stop com.android.chrome &>/dev/null
        am force-stop com.wmspanel.larix_broadcaster &>/dev/null
        # Reiniciar script desde cero
        exec "$0" "$@"
    fi

    echo "[$(date +%T)] 📍 Midiendo altitud de vuelo..."
    
    LOC_JSON=$(get_gps_location)
    LAT=$(echo "$LOC_JSON" | jq -r '.latitude // "null"')
    LNG=$(echo "$LOC_JSON" | jq -r '.longitude // "null"')
    ALT=$(echo "$LOC_JSON" | jq -r '.altitude // "null"')
    ACC=$(echo "$LOC_JSON" | jq -r '.accuracy // "null"')
    
    # Enviar siempre el reporte de telemetría por MQTT (evita que el dashboard marque desconectado si no hay fix todavía)
    GPS_PAYLOAD=$(jq -n \
      --argjson lat "$LAT" \
      --argjson lng "$LNG" \
      --argjson alt "$ALT" \
      --argjson acc "$ACC" \
      '{lat: $lat, lng: $lng, altitude: $alt, accuracy: $acc}')
    mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "$TOPIC_TELEMETRY" -m "$GPS_PAYLOAD"
    echo "[📡 TELEMETRÍA] Enviada: Alt: $ALT m, Acc: $ACC m"
    
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

# Detener el receptor de comandos MQTT de fondo para bloquear control remoto durante el vuelo autónomo
kill -9 "$SUB_PID" 2>/dev/null
pkill -9 -P "$SUB_PID" 2>/dev/null

# Detener retransmisión de vídeo
echo "[🔌 VIDEO] Deteniendo transmisión de vídeo en directo..."
am force-stop flutter.vdo.ninja &>/dev/null
am force-stop com.android.chrome &>/dev/null
am force-stop com.wmspanel.larix_broadcaster &>/dev/null
sleep 2

# ==============================================================================
# FASE 2: CAPTURA DE IMÁGENES AUTÓNOMA Y TELEMETRÍA (INTELIGENTE)
# ==============================================================================
echo "====================================================="
echo "  [FASE 2] Iniciando bucle de captura autónoma inteligente..."
echo "  Destino de capturas locales: ~/imagenes/"
echo "  Telemetría cada 5s | Fotos cada 60s (si hay cobertura)"
echo "====================================================="

VIDEO_RUNNING=0
CICLO=0
PHOTO_INTERVAL=60  # Intervalo de fotos en segundos
PHOTO_CYCLES=$((PHOTO_INTERVAL / 5))
if [ "$PHOTO_CYCLES" -lt 1 ]; then PHOTO_CYCLES=1; fi

while true; do
    # 1. Comprobar si hay cobertura de red real contra el Broker MQTT
    if nc -z -w 2 "$MQTT_HOST" "$MQTT_PORT" &>/dev/null; then
        COBERTURA=1
    else
        COBERTURA=0
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

    # 2. Gestión dinámica de conectividad en vuelo
    if [ "$COBERTURA" -eq 1 ]; then
        # Con cobertura: Si el vídeo estaba apagado, lo encendemos para el directo
        if [ "$VIDEO_RUNNING" -eq 0 ]; then
            echo "[🛰️ NET] Conexión recuperada. Reanudando vídeo en directo..."
            am start -a android.intent.action.VIEW -d "https://vdo.ninja/?push=sonda_stratocaster&webcam&facing=back&autostart&noaudio&videobitrate=1000&quality=2&nopreview&clean&forcelandscape" &>/dev/null
            VIDEO_RUNNING=1
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

        mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "$TOPIC_STATUS" -m "$PAYLOAD" &>/dev/null &
        echo "[🛰️ NET] [$(date +%T)] Telemetría enviada por MQTT."
    else
        # Sin cobertura: Si el directo de Chrome está corriendo, lo matamos para salvar batería
        if [ "$VIDEO_RUNNING" -eq 1 ]; then
            echo "[🛰️ NET] Conexión perdida. Apagando vídeo para conservar batería..."
            am force-stop flutter.vdo.ninja &>/dev/null
            am force-stop com.android.chrome &>/dev/null
            am force-stop com.wmspanel.larix_broadcaster &>/dev/null
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
            am start -a android.intent.action.VIEW -d "https://vdo.ninja/?push=sonda_stratocaster&webcam&facing=back&autostart&noaudio&videobitrate=1000&quality=2&nopreview&clean&forcelandscape" &>/dev/null
        fi

        if [ -f "$TARGET_IMG" ]; then
            # Guardar copia física con timestamp en el almacenamiento local del teléfono
            TIMESTAMP=$(date +%Y%m%d_%H%M%S)
            LOCAL_COPY="$HOME/imagenes/sonda_$TIMESTAMP.jpg"
            cp "$TARGET_IMG" "$LOCAL_COPY"

            TEXTO_DETECTADO="Captura autónoma - Altitud: $ALT m"

            if [ "$COBERTURA" -eq 1 ]; then
                echo "[$(date +%T)] 📤 Subiendo foto original al servidor..."
                UPLOAD_RESP=$(curl -s -F "file=@$TARGET_IMG" -F "texto=$TEXTO_DETECTADO" -F "device_id=$DEVICE_ID" "$IMAGE_SERVER_URL/upload")

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

                    mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "$TOPIC_CAMERA" -m "$PAYLOAD"
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
