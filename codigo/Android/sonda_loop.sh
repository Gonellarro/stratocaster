#!/data/data/com.termux/files/usr/bin/bash

# ==============================================================================
# ORQUESTRADOR DE CAPTURA E INFERENCIA LOCAL - RUTAS OPTIMIZADAS (CON CONEXIÓN)
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
for cmd in termux-camera-photo termux-wake-lock termux-wake-unlock magick mosquitto_pub jq; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "[❌ ERROR] El comando '$cmd' no está instalado en Termux."
        echo "Asegúrate de instalar 'mosquitto-clients', 'jq' y 'termux-api'."
        exit 1
    fi
done

if [ ! -x "$BIN_PATH" ]; then
    echo "[❌ ERROR] No se encontró el ejecutable en $BIN_PATH o no tiene permisos de ejecución."
    exit 1
fi

# Prompt corregido usando ANSI-C quoting para interpretar saltos de línea (\n)
PROMPT=$'<|im_start|>user\nDescribe en una sola frase corta qué se ve en esta imagen.<|im_end|>\n<|im_start|>assistant\n'

# Tiempo de bucle
TIEMPO=10

echo "====================================================="
echo "  Iniciando bucle de captura autónoma (Cada $TIEMPO s)..."
echo "  Destino de capturas: ~/imagenes/"
echo "  Servidor de fotos: $IMAGE_SERVER_URL"
echo "  Broker MQTT: $MQTT_HOST:$MQTT_PORT"
echo "====================================================="

# Asegurar que la CPU de Android no entre en reposo profundo
termux-wake-lock

# Liberar el wake lock automáticamente al salir del script (por interrupción o error)
trap 'echo "[INFO] Liberando wake lock de Termux..."; termux-wake-unlock' EXIT

while true; do
    echo "[$(date +%T)] 📸 Capturando frame desde el sensor óptico..."
    
    # 1. Captura de foto desatendida usando la cámara trasera (ID 0)
    termux-camera-photo -c 0 "$TARGET_IMG"
    
    if [ ! -f "$TARGET_IMG" ]; then
        echo "[❌ ERROR] No se pudo generar la imagen en $TARGET_IMG. Reintentando en 5s..."
        sleep 5
        continue
    fi

    # 1.5. Redimensionar la imagen con fallback en caso de error
    if magick "$TARGET_IMG" -resize 640x480 "$TARGET_IMG_LOW" 2>/dev/null; then
        IMG_TO_PROCESS="$TARGET_IMG_LOW"
    else
        echo "[⚠️ ADVERTENCIA] Falló el redimensionado con ImageMagick. Procesando imagen original..."
        IMG_TO_PROCESS="$TARGET_IMG"
    fi

    echo "[$(date +%T)] 🧠 Procesando imagen con Qwen3-VL (Inferencia local)..."
    
    # 2. Ejecución del modelo redirigiendo los logs de telemetría (stderr)
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

    # Guardamos la cadena localmente
    echo "$TEXTO_DETECTADO" > "$RESULT_TXT"

    # 3. COMPROBAR CONEXIÓN WIFI (Para pruebas)
    # En Android 10+, 'ip route' lanza 'Permission denied' al intentar leer netlink sockets.
    # Usamos 'termux-wifi-connectioninfo' que accede a la API de Android de forma permitida.
    WIFI_ACTIVE=false
    if command -v termux-wifi-connectioninfo &> /dev/null; then
        WIFI_INFO=$(termux-wifi-connectioninfo 2>/dev/null)
        WIFI_IP=$(echo "$WIFI_INFO" | jq -r '.ip // empty')
        if [ -n "$WIFI_IP" ] && [ "$WIFI_IP" != "0.0.0.0" ]; then
            WIFI_ACTIVE=true
        fi
    fi

    if [ "$WIFI_ACTIVE" = true ]; then
        echo "[$(date +%T)] 📶 Conexión WIFI detectada activa (IP: $WIFI_IP)."
    else
        echo "[$(date +%T)] 📴 Sin conexión WIFI activa."
    fi

    # 4. GESTIÓN DE ENVÍO SEGÚN WIFI
    if [ "$WIFI_ACTIVE" = true ]; then
        # 4.1. [OPCIONAL] Intentar obtener coordenadas GPS del móvil
        LAT="null"
        LNG="null"
        ALT="null"
        
        if command -v termux-location &> /dev/null; then
            echo "[$(date +%T)] 📍 Obteniendo ubicación GPS del móvil..."
            # Intentar obtener la última ubicación conocida por GPS (timeout 5s)
            LOC_JSON=$(timeout 5 termux-location -p gps -r last 2>/dev/null)
            
            # Fallback a red si el GPS no responde (por estar bajo techo)
            if [ -z "$LOC_JSON" ] || [ "$LOC_JSON" = "{}" ]; then
                LOC_JSON=$(timeout 5 termux-location -p network -r last 2>/dev/null)
            fi
            
            if [ -n "$LOC_JSON" ] && [ "$LOC_JSON" != "{}" ]; then
                LAT=$(echo "$LOC_JSON" | jq -r '.latitude // "null"')
                LNG=$(echo "$LOC_JSON" | jq -r '.longitude // "null"')
                ALT=$(echo "$LOC_JSON" | jq -r '.altitude // "null"')
                echo "[📍 GPS] Geolocalización: Lat: $LAT, Lng: $LNG, Alt: $ALT"
            else
                echo "[⚠️ GPS] No se pudo obtener la geolocalización."
            fi
        fi

        # 4.2. Subir imagen al servidor HTTP (a través de Nginx Proxy Manager)
        echo "[$(date +%T)] 📤 Subiendo foto a $IMAGE_SERVER_URL/upload..."
        UPLOAD_RESP=$(curl -s -F "file=@$IMG_TO_PROCESS" -F "texto=$TEXTO_DETECTADO" "$IMAGE_SERVER_URL/upload")
        
        if [ $? -eq 0 ] && [ -n "$UPLOAD_RESP" ] && [[ "$UPLOAD_RESP" != *"Error"* ]]; then
            FILENAME="$UPLOAD_RESP"
            URL_COMPLETA="$IMAGE_SERVER_URL/images/$FILENAME"
            echo "[✅ OK] Subida con éxito: $URL_COMPLETA"
            
            # 4.3. Preparar el JSON para MQTT
            PAYLOAD=$(jq -n \
              --arg txt "$TEXTO_DETECTADO" \
              --arg url "$URL_COMPLETA" \
              --argjson lat "$LAT" \
              --argjson lng "$LNG" \
              --argjson alt "$ALT" \
              '{texto: $txt, url_imagen: $url, lat: $lat, lng: $lng, alt: $alt}')

            # 4.4. Publicar datos en el broker MQTT
            echo "[📡 MQTT] Publicando datos..."
            MQTT_CMD="mosquitto_pub -h $MQTT_HOST -p $MQTT_PORT -t $MQTT_TOPIC -m '$PAYLOAD'"
            if [ -n "$MQTT_USER" ]; then
                MQTT_CMD="$MQTT_CMD -u $MQTT_USER -P $MQTT_PASS"
            fi
            
            if eval "$MQTT_CMD"; then
                echo "[✅ OK] Publicado con éxito en el topic '$MQTT_TOPIC'."
            else
                echo "[❌ ERROR] Falló la publicación MQTT."
            fi
        else
            echo "[❌ ERROR] Falló la subida de la foto a la API: $UPLOAD_RESP"
        fi
    else
        # Modo Offline: Guardar información en log local del dispositivo
        echo "[$(date +%T)] Guardando registro offline en local..."
        echo "[$(date +%Y-%m-%d\ %H:%M:%S)] [OFFLINE] Texto IA: $TEXTO_DETECTADO" >> "$OFFLINE_LOG"
    fi

    echo "[$(date +%T)] Ciclo completado. Esperando $TIEMPO segundos..."
    echo "====================================================="
    
    sleep $TIEMPO
done
