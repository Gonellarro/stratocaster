#!/data/data/com.termux/files/usr/bin/bash

# ==============================================================================
# ORQUESTRADOR MULTI-FASE DE LA SONDA (STRATOCASTER)
# Fase 0: Pruebas y Espera en Rampa
# Fase 1: Vuelo en Directo (Streaming SRT)
# Fase 2: Inferencia Autónoma (Captura + Local IA)
# ==============================================================================

# Definición de rutas absolutas del entorno Termux
LLAMA_DIR="$HOME/llama.cpp"
BIN_PATH="$LLAMA_DIR/build/bin/llama-mtmd-cli"
MODEL_PATH="$LLAMA_DIR/models/qwen/Qwen3VL-2B-Instruct-Q4_K_M.gguf"
PROJ_PATH="$LLAMA_DIR/models/qwen/mmproj-Qwen3VL-2B-Instruct-F16.gguf"

# RUTAS DE CAPTURA Y TELEMETRÍA
TARGET_IMG="$HOME/imagenes/foto.jpg"
TARGET_IMG_LOW="$HOME/imagenes/foto_baja.jpg"  
RESULT_TXT="$HOME/imagenes/ultimo_resultado.txt"
LOG_TMP="$HOME/imagenes/llama_log.tmp"
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
for cmd in termux-camera-photo termux-wake-lock termux-wake-unlock magick mosquitto_pub mosquitto_sub jq termux-battery-status termux-location termux-tts-speak; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "[❌ ERROR] El comando '$cmd' no está instalado en Termux."
        echo "Asegúrate de instalar los paquetes 'mosquitto', 'jq', 'termux-api' y la app Termux:API en Android."
        exit 1
    fi
done

if [ ! -x "$BIN_PATH" ]; then
    echo "[❌ ERROR] No se encontró el ejecutable en $BIN_PATH o no tiene permisos de ejecución."
    exit 1
fi

# Prompt corregido usando ANSI-C quoting para interpretar saltos de línea (\n)
PROMPT=$'<|im_start|>user\nDescribe en una sola frase corta qué se ve en esta imagen.<|im_end|>\n<|im_start|>assistant\n'

# Tiempo de bucle de fotos en fase autónoma
TIEMPO=10

# Asegurar que la CPU de Android no entre en reposo profundo
termux-wake-lock

# Liberar el wake lock automáticamente al salir del script
trap 'echo "[INFO] Liberando wake lock de Termux..."; rm -f "$ARMED_FLAG"; termux-wake-unlock' EXIT

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
            
            # 2. Obtener GPS rápido (última posición conocida) para rampa
            LOC_JSON=$(timeout 3 termux-location -p network -r last 2>/dev/null)
            if [ -z "$LOC_JSON" ] || [ "$LOC_JSON" = "{}" ]; then
                LOC_JSON=$(timeout 3 termux-location -p gps -r last 2>/dev/null)
            fi
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
            # Forzar inicialización activa del GPS físico
            echo "[🛰️ GPS] Iniciando receptor GPS (búsqueda activa)..."
            termux-tts-speak "Iniciando búsqueda de satélites GPS." 2>/dev/null
            mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "sonda/status" -m '{"status": "gps_initializing"}'
            
            # Ejecutar búsqueda de satélites activa en segundo plano (puede tardar 10-15s)
            (
                LOC_JSON=$(timeout 20 termux-location -p gps 2>/dev/null)
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
                    termux-tts-speak "Señal de GPS fijada correctamente." 2>/dev/null
                else
                    mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "sonda/status" -m '{"status": "gps_failed"}'
                    termux-tts-speak "Error al fijar señal de GPS. Por favor, asegure visibilidad al cielo." 2>/dev/null
                fi
            ) &
            ;;
            
        "test_audio")
            # Test físico de audio
            termux-tts-speak "Sonda en línea y lista para la comprobación." 2>/dev/null
            mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "sonda/status" -m '{"status": "audio_ok"}'
            ;;
            
        "test_video_on")
            # Encender streaming (Soporte VDO.ninja, Chrome o Larix)
            echo "[📹 VIDEO] Test de vídeo: Iniciando streaming..."
            # Intentar lanzar app nativa VDO.ninja
            am start -n flutter.vdo.ninja/.MainActivity &>/dev/null
            mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "sonda/status" -m '{"status": "video_streaming_on"}'
            ;;
            
        "test_video_off")
            # Apagar todos los posibles codificadores de streaming para liberar la cámara
            echo "[📹 VIDEO] Test de vídeo: Deteniendo streaming..."
            am force-stop flutter.vdo.ninja &>/dev/null
            am force-stop com.android.chrome &>/dev/null
            am force-stop com.wmspanel.larix_broadcaster &>/dev/null
            mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "sonda/status" -m '{"status": "video_streaming_off"}'
            ;;
            
        "test_photo")
            # Captura de foto e inferencia IA bajo demanda (para pruebas pre-vuelo)
            echo "[📸 CÁMARA] Solicitud de test de foto e IA local recibida..."
            mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "sonda/status" -m '{"status": "camera_testing"}'
            
            termux-camera-photo -c 0 "$TARGET_IMG"
            
            if [ -f "$TARGET_IMG" ]; then
                # Redimensionar para optimizar
                if magick "$TARGET_IMG" -resize 640x480 "$TARGET_IMG_LOW" 2>/dev/null; then
                    IMG_TO_PROCESS="$TARGET_IMG_LOW"
                else
                    IMG_TO_PROCESS="$TARGET_IMG"
                fi
                
                echo "Procesando imagen: $IMG_TO_PROCESS"
                # Ejecutar inferencia de la IA (redirigiendo la entrada estándar para evitar cuelgues)
                TEXTO_DETECTADO=$("$BIN_PATH" \
                    -m "$MODEL_PATH" \
                    --mmproj "$PROJ_PATH" \
                    --image "$IMG_TO_PROCESS" \
                    -c 2048 \
                    -b 256 \
                    -t 4 \
                    --no-warmup \
                    -p "$PROMPT" 2> "$LOG_TMP" </dev/null)
                
                # Obtener GPS rápido
                LOC_JSON=$(timeout 5 termux-location -p gps -r last 2>/dev/null)
                if [ -z "$LOC_JSON" ] || [ "$LOC_JSON" = "{}" ]; then
                    LOC_JSON=$(timeout 5 termux-location -p network -r last 2>/dev/null)
                fi
                LAT=$(echo "$LOC_JSON" | jq -r '.latitude // "null"')
                LNG=$(echo "$LOC_JSON" | jq -r '.longitude // "null"')
                ALT=$(echo "$LOC_JSON" | jq -r '.altitude // "null"')
                
                # Subir foto original en alta resolución a la web
                echo "[📸 CÁMARA] Subiendo foto original a la web..."
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
                    termux-tts-speak "Comprobación de cámara y modelo de inteligencia artificial completada con éxito." 2>/dev/null
                else
                    echo "[❌ ERROR] Falló la subida de la foto original. Servidor respondió: $UPLOAD_RESP"
                    mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "sonda/status" -m '{"status": "camera_error"}'
                fi
            else
                mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "sonda/status" -m '{"status": "camera_capture_failed"}'
            fi
            ;;
            
        "reboot")
            echo "[⚠️ SISTEMA] Reiniciando dispositivo..."
            mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "sonda/status" -m '{"status": "rebooting"}'
            sleep 2
            reboot 2>/dev/null || exit 0
            ;;
            
        "arm")
            # ARMAR Y ENTRAR EN MODO VUELO
            echo "[🚀 SECUENCIA] ¡Comando de ARMADO recibido!"
            
            # NOTA: Usando VDO.ninja de forma manual, no reiniciamos la app al armar para no cortar la conexión iniciada a mano.
            # Simplemente dejamos que la transmisión siga activa.
            
            # Avisar al servidor central para arrancar la cuenta atrás visual
            curl -s -X POST "$IMAGE_SERVER_URL/control_lanzamiento/ok" &>/dev/null
            
            # Notificar estado armado por MQTT
            mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" -t "sonda/status" -m '{"status": "armed"}'
            
            # Escribir el flag físico en disco para notificar al proceso padre (evita subshell lock)
            touch "$ARMED_FLAG"
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
            # Redirigir entrada estándar y lanzar en segundo plano para evitar bloqueos
            handle_command "$CMD" </dev/null &
        fi
    done
) &
SUB_PID=$!

# Bucle de espera del armado (con telemetría periódica cada 10 segundos)
COUNTER=0
while [ ! -f "$ARMED_FLAG" ]; do
    if [ $((COUNTER % 10)) -eq 0 ]; then
        # Solicitar actualización de sensores de forma no bloqueante
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

# Espera inicial de 10s mientras el directo se estabiliza (durante la cuenta atrás de tierra)
sleep 10

START_TIME=$(date +%s)
TIMEOUT_SAFETY=600 # 10 minutos de transmisión límite antes de pasar a fotos autónomas por seguridad

while true; do
    echo "[$(date +%T)] 📍 Midiendo altitud de vuelo..."
    
    # Adquisición de GPS en segundo plano
    LOC_JSON=$(timeout 4 termux-location -p gps -r last 2>/dev/null)
    if [ -z "$LOC_JSON" ] || [ "$LOC_JSON" = "{}" ]; then
        LOC_JSON=$(timeout 4 termux-location -p network -r last 2>/dev/null)
    fi
    
    LAT=$(echo "$LOC_JSON" | jq -r '.latitude // "null"')
    LNG=$(echo "$LOC_JSON" | jq -r '.longitude // "null"')
    ALT=$(echo "$LOC_JSON" | jq -r '.altitude // "null"')
    ACC=$(echo "$LOC_JSON" | jq -r '.accuracy // "null"')
    
    # Publicar telemetría en tiempo real en gps/data
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
    
    # Comprobar límite de altitud para cortar el vídeo (1000 metros)
    ALT_INT=${ALT%.*} # Convertir a entero
    if [ -n "$ALT_INT" ] && [ "$ALT_INT" != "null" ]; then
        if [ "$ALT_INT" -gt 1000 ]; then
            echo "[🚀 CONTROL] ¡Cota de 1.000m superada! ($ALT_INT m). Entrando en Fase Autónoma..."
            break
        fi
    fi
    
    # Comprobar timeout de seguridad
    CURRENT_TIME=$(date +%s)
    ELAPSED=$((CURRENT_TIME - START_TIME))
    if [ $ELAPSED -gt $TIMEOUT_SAFETY ]; then
        echo "[⚠️ SEGURIDAD] Límite de tiempo de vídeo agotado ($TIMEOUT_SAFETY s). Entrando en Fase Autónoma..."
        break
    fi
    
    sleep 5
done

# Detener retransmisión de vídeo (Soporta VDO.ninja, Chrome y Larix)
echo "[🔌 VIDEO] Deteniendo transmisión de vídeo en directo..."
am force-stop flutter.vdo.ninja &>/dev/null
am force-stop com.android.chrome &>/dev/null
am force-stop com.wmspanel.larix_broadcaster &>/dev/null
sleep 2

# ==============================================================================
# FASE 2: INFERENCIA AUTÓNOMA Y CAPTURA DE IMÁGENES
# ==============================================================================
echo "====================================================="
echo "  [FASE 2] Iniciando bucle de captura autónoma..."
echo "  Destino de capturas locales: ~/imagenes/"
echo "  Inferencia local IA con Qwen3-VL activa (Cada $TIEMPO s)"
echo "====================================================="

# Detectar Wifi en las rutas de red (para pruebas locales)
WIFI_ACTIVE=false
if command -v termux-wifi-connectioninfo &> /dev/null; then
    WIFI_INFO=$(termux-wifi-connectioninfo 2>/dev/null)
    WIFI_IP=$(echo "$WIFI_INFO" | jq -r '.ip // empty')
    if [ -n "$WIFI_IP" ] && [ "$WIFI_IP" != "0.0.0.0" ]; then
        WIFI_ACTIVE=true
    fi
fi

while true; do
    echo "[$(date +%T)] 📸 Capturando frame desde el sensor óptico..."
    
    # 1. Captura de foto usando la cámara trasera
    termux-camera-photo -c 0 "$TARGET_IMG"
    
    if [ ! -f "$TARGET_IMG" ]; then
        echo "[❌ ERROR] No se pudo generar la imagen en $TARGET_IMG. Reintentando en 5s..."
        sleep 5
        continue
    fi

    # 1.5. Redimensionar para optimizar procesamiento
    if magick "$TARGET_IMG" -resize 640x480 "$TARGET_IMG_LOW" 2>/dev/null; then
        IMG_TO_PROCESS="$TARGET_IMG_LOW"
    else
        echo "[⚠️ ADVERTENCIA] Falló el redimensionado. Procesando original..."
        IMG_TO_PROCESS="$TARGET_IMG"
    fi

    echo "[$(date +%T)] 🧠 Procesando imagen con Qwen3-VL (Inferencia local)..."
    
    # 2. Ejecución de la IA redirigiendo stderr
    TEXTO_DETECTADO=$("$BIN_PATH" \
        -m "$MODEL_PATH" \
        --mmproj "$PROJ_PATH" \
        --image "$IMG_TO_PROCESS" \
        -c 2048 \
        -b 256 \
        -t 4 \
        --no-warmup \
        -p "$PROMPT" 2> "$LOG_TMP")

    echo "-----------------------------------------------------"
    echo "📝 TEXTO EXTRAÍDO POR LA IA:"
    echo "$TEXTO_DETECTADO"
    echo "-----------------------------------------------------"

    echo "$TEXTO_DETECTADO" > "$RESULT_TXT"

    # Redetectar Wifi en cada ciclo
    if command -v termux-wifi-connectioninfo &> /dev/null; then
        WIFI_INFO=$(termux-wifi-connectioninfo 2>/dev/null)
        WIFI_IP=$(echo "$WIFI_INFO" | jq -r '.ip // empty')
        if [ -n "$WIFI_IP" ] && [ "$WIFI_IP" != "0.0.0.0" ]; then
            WIFI_ACTIVE=true
        else
            WIFI_ACTIVE=false
        fi
    fi

    # Envío de datos
    if [ "$WIFI_ACTIVE" = true ]; then
        LAT="null"
        LNG="null"
        ALT="null"
        
        # Geolocalizar
        if command -v termux-location &> /dev/null; then
            LOC_JSON=$(timeout 5 termux-location -p gps -r last 2>/dev/null)
            if [ -z "$LOC_JSON" ] || [ "$LOC_JSON" = "{}" ]; then
                LOC_JSON=$(timeout 5 termux-location -p network -r last 2>/dev/null)
            fi
            
            if [ -n "$LOC_JSON" ] && [ "$LOC_JSON" != "{}" ]; then
                LAT=$(echo "$LOC_JSON" | jq -r '.latitude // "null"')
                LNG=$(echo "$LOC_JSON" | jq -r '.longitude // "null"')
                ALT=$(echo "$LOC_JSON" | jq -r '.altitude // "null"')
            fi
        fi

        # Subir foto original en alta resolución a la web
        echo "[$(date +%T)] 📤 Subiendo foto original y descripción a la web..."
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
            echo "[✅ OK] Datos de telemetría publicados por MQTT."
        else
            echo "[❌ ERROR] Falló la subida de foto al servidor web: $UPLOAD_RESP"
        fi
    else
        # Modo sin conexión Wifi
        echo "[$(date +%T)] Guardando registro offline en local..."
        echo "[$(date +%Y-%m-%d\ %H:%M:%S)] [OFFLINE] Texto IA: $TEXTO_DETECTADO" >> "$OFFLINE_LOG"
    fi

    echo "[$(date +%T)] Ciclo completado. Esperando $TIEMPO segundos..."
    echo "====================================================="
    
    sleep $TIEMPO
done
