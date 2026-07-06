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

# CONFIGURACIÓN DE CONEXIÓN Y SERVIDORES (Valores por defecto)
IMAGE_SERVER_URL="https://sondafotos.martivich.es"
MQTT_HOST="sondafotos.martivich.es"
MQTT_PORT=1883
MQTT_USER=""
MQTT_PASS=""
MQTT_TOPIC="sonda/camera"

# Cargar variables de entorno y credenciales privadas desde 'sonda.env' si existe
CONFIG_FILE="$(dirname "$0")/sonda.env"
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
fi

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
            
            # 3. Publicar reporte en sonda/status
            STATUS_PAYLOAD=$(jq -n \
              --argjson lvl "$BAT_LVL" \
              --argjson tmp "$BAT_TEMP" \
              --argjson lat "$LAT" \
              --argjson lng "$LNG" \
              --argjson alt "$ALT" \
              --argjson acc "$ACC" \
              '{status: "diagnostico", level: $lvl, temp: $tmp, lat: $lat, lng: $lng, alt: $alt, accuracy: $acc}')
              
            mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "sonda/status" -m "$STATUS_PAYLOAD"
            ;;
            
        "init_gps")
            echo "[🛰️ GPS] Iniciando receptor GPS..."
            mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "sonda/status" -m '{"status": "gps_initializing"}'
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
                  
                mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "sonda/status" -m "$STATUS_PAYLOAD"
                timeout 5 termux-tts-speak "Señal de GPS fijada correctamente." 2>/dev/null
            else
                mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "sonda/status" -m '{"status": "gps_failed"}'
                timeout 5 termux-tts-speak "Error al fijar señal de GPS." 2>/dev/null
            fi
            ;;
            
        "test_audio")
            mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "sonda/status" -m '{"status": "audio_ok"}'
            timeout 5 termux-tts-speak "Sonda en línea y lista para la comprobación." 2>/dev/null
            ;;
            
        "test_video_on")
            echo "[📹 VIDEO] Test de vídeo: Iniciando streaming..."
            am start -a android.intent.action.VIEW -d "https://vdo.ninja/?push=sonda_stratocaster&facing=back&autostart&noaudio&videobitrate=1000&quality=2" &>/dev/null
            mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "sonda/status" -m '{"status": "video_streaming_on"}'
            ;;
            
        "test_video_off")
            echo "[📹 VIDEO] Test de vídeo: Deteniendo streaming..."
            am force-stop flutter.vdo.ninja &>/dev/null
            am force-stop com.android.chrome &>/dev/null
            am force-stop com.wmspanel.larix_broadcaster &>/dev/null
            mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "sonda/status" -m '{"status": "video_streaming_off"}'
            ;;
            
        "test_photo")
            echo "[📸 CÁMARA] Solicitud de test de foto..."
            mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "sonda/status" -m '{"status": "camera_testing"}'
            
            am force-stop com.android.chrome &>/dev/null
            am force-stop flutter.vdo.ninja &>/dev/null
            sleep 1
            
            termux-camera-photo -c 0 "$TARGET_IMG"
            
            if [ -f "$TARGET_IMG" ]; then
                TEXTO_DETECTADO="Captura de verificación de cámara (OK)"
                
                LOC_JSON=$(get_gps_location)
                LAT=$(echo "$LOC_JSON" | jq -r '.latitude // "null"')
                LNG=$(echo "$LOC_JSON" | jq -r '.longitude // "null"')
                ALT=$(echo "$LOC_JSON" | jq -r '.altitude // "null"')
                
                echo "[📸 CÁMARA] Subiendo foto de test a la web..."
                UPLOAD_RESP=$(curl -s -F "file=@$TARGET_IMG" -F "texto=$TEXTO_DETECTADO" "$IMAGE_SERVER_URL/upload")
                
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
                    
                    mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "$MQTT_TOPIC" -m "$PAYLOAD"
                    timeout 5 termux-tts-speak "Comprobación de cámara completada con éxito." 2>/dev/null
                else
                    echo "[❌ ERROR] Falló la subida de la foto de test: $UPLOAD_RESP"
                    mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "sonda/status" -m '{"status": "camera_error"}'
                fi
            else
                mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "sonda/status" -m '{"status": "camera_capture_failed"}'
            fi
            ;;
            
        "reboot")
            echo "[⚠️ SISTEMA] Reiniciando el dispositivo móvil..."
            timeout 5 termux-tts-speak "Reiniciando el sistema de la sonda." 2>/dev/null
            sleep 1
            su -c reboot 2>/dev/null || reboot
            ;;
            
        "arm")
            touch "$ARMED_FLAG"
            mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "sonda/status" -m '{"status": "armed"}'
            timeout 5 termux-tts-speak "Sonda Armada. Despegue inminente." 2>/dev/null
            ;;
    esac
}

# ==============================================================================
# FASE 0: ESPERA Y DIAGNÓSTICOS EN RAMPA
# ==============================================================================
echo "====================================================="
echo "  [FASE 0] Iniciando receptor de comandos pre-vuelo..."
echo "  Suscrito a sonda/comando. Esperando diagnóstico..."
echo "====================================================="

rm -f "$ARMED_FLAG"

# Suscriptor MQTT de fondo
(
    mosquitto_sub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "sonda/comando" 2>/dev/null | while read -r line; do
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

# Matar el receptor de comandos de fondo para bloquear control remoto durante el vuelo
kill -9 "$SUB_PID" 2>/dev/null
pkill -9 -P "$SUB_PID" 2>/dev/null
rm -f "$ARMED_FLAG"

# ==============================================================================
# FASE 1: VUELO EN DIRECTO (STREAMING Y MONITOREO DE ALTITUD)
# ==============================================================================
echo "====================================================="
echo "  [FASE 1] ¡IGNICIÓN! Sonda en vuelo."
echo "  Transmitiendo vídeo en directo y telemetría de rampa..."
echo "====================================================="

# Arrancar el vídeo en directo de forma automática en el despegue (cámara trasera, autostart, sin audio y bitrate controlado)
am start -a android.intent.action.VIEW -d "https://vdo.ninja/?push=sonda_stratocaster&facing=back&autostart&noaudio&videobitrate=1000&quality=2" &>/dev/null

sleep 10

START_TIME=$(date +%s)
TIMEOUT_SAFETY=600

while true; do
    echo "[$(date +%T)] 📍 Midiendo altitud de vuelo..."
    
    LOC_JSON=$(get_gps_location)
    LAT=$(echo "$LOC_JSON" | jq -r '.latitude // "null"')
    LNG=$(echo "$LOC_JSON" | jq -r '.longitude // "null"')
    ALT=$(echo "$LOC_JSON" | jq -r '.altitude // "null"')
    ACC=$(echo "$LOC_JSON" | jq -r '.accuracy // "null"')
    
    if [ "$LAT" != "null" ]; then
        GPS_PAYLOAD=$(jq -n \
          --argjson lat "$LAT" \
          --argjson lng "$LNG" \
          --argjson alt "$ALT" \
          --argjson acc "$ACC" \
          '{lat: $lat, lng: $lng, altitude: $alt, accuracy: $acc}')
        mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "gps/data" -m "$GPS_PAYLOAD"
        echo "[📡 TELEMETRÍA] Enviada: Alt: $ALT m, Acc: $ACC m"
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
echo "[🔌 VIDEO] Deteniendo transmisión de vídeo en directo..."
am force-stop flutter.vdo.ninja &>/dev/null
am force-stop com.android.chrome &>/dev/null
am force-stop com.wmspanel.larix_broadcaster &>/dev/null
sleep 2

# ==============================================================================
# FASE 2: CAPTURA DE IMÁGENES AUTÓNOMA Y TELEMETRÍA (SIN IA LOCAL)
# ==============================================================================
echo "====================================================="
echo "  [FASE 2] Iniciando bucle de captura autónoma ligera..."
echo "  Destino de capturas locales: ~/imagenes/"
echo "  Subida de fotos e información cada $TIEMPO s"
echo "====================================================="

while true; do
    echo "[$(date +%T)] 📸 Capturando frame desde el sensor óptico..."
    
    termux-camera-photo -c 0 "$TARGET_IMG"
    
    if [ ! -f "$TARGET_IMG" ]; then
        echo "[❌ ERROR] No se pudo generar la imagen. Reintentando en 5s..."
        sleep 5
        continue
    fi

    # Definir texto descriptivo genérico (IA eliminada del móvil)
    TEXTO_DETECTADO="Captura en tiempo real - Sonda Stratocaster"

    # Geolocalizar
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

    # Subir foto original a la web
    echo "[$(date +%T)] 📤 Subiendo foto original..."
    UPLOAD_RESP=$(curl -s -F "file=@$TARGET_IMG" -F "texto=$TEXTO_DETECTADO" "$IMAGE_SERVER_URL/upload")
    
    if [ $? -eq 0 ] && [ -n "$UPLOAD_RESP" ] && [[ "$UPLOAD_RESP" != *"Error"* ]]; then
        FILENAME="$UPLOAD_RESP"
        URL_COMPLETA="$IMAGE_SERVER_URL/images/$FILENAME"
        echo "[✅ OK] Subida exitosa: $URL_COMPLETA"
        
        # Publicar JSON MQTT en sonda/camera
        PAYLOAD=$(jq -n \
          --arg txt "$TEXTO_DETECTADO" \
          --arg url "$URL_COMPLETA" \
          --argjson lat "$LAT" \
          --argjson lng "$LNG" \
          --argjson alt "$ALT" \
          '{texto: $txt, url_imagen: $url, lat: $lat, lng: $lng, alt: $alt}')

        mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "$MQTT_TOPIC" -m "$PAYLOAD"
        echo "[✅ OK] Telemetría y foto publicadas por MQTT."
    else
        echo "[❌ ERROR] Falló la subida de foto: $UPLOAD_RESP"
        # Guardar en log local offline
        echo "[$(date +%Y-%m-%d\ %H:%M:%S)] [OFFLINE] Lat: $LAT, Lng: $LNG, Alt: $ALT" >> "$OFFLINE_LOG"
    fi

    echo "[$(date +%T)] Ciclo completado. Esperando $TIEMPO segundos..."
    echo "====================================================="
    
    sleep $TIEMPO
done
