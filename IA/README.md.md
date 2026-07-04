
# Despliegue de Visión Artificial Local (Qwen3-VL) en Dispositivos Android mediante Termux

Este componente del proyecto describe la infraestructura, el proceso de compilación, el aprovisionamiento de hardware óptimo y la ejecución de Modelos de Lenguaje Multimodales (VLM) de forma 100% local en un smartphone embebido. El objetivo final es dotar a la sonda de capacidad de "percepción visual" autónoma para analizar el entorno sin dependencia de conectividad en la nube.

---

## 🛠️ Arquitectura y Componentes del Sistema

* **Hardware de Pruebas:** Xiaomi (Procesador MediaTek Dimensity, 12 GB LPDDR5X RAM).
* **Entorno de Ejecución:** Termux (Emulador de terminal y entorno Linux aislado para Android, compilación de comunidad F-Droid).
* **Motor de Inferencia:** `llama.cpp` (Compilado de forma nativa en el dispositivo).
* **Modelo de Visión (VLM):** Qwen3-VL-2B-Instruct (Cuantización Q4_K_M para el LLM + Proyector Visual F16).

---

## 🚀 Guía de Despliegue Paso a Paso

### 1. Preparación del Entorno Base (Evasión de Restricciones del Sistema)
Las versiones de Termux distribuidas en plataformas comerciales como Google Play se encuentran obsoletas y bloqueadas debido a las políticas restrictivas de APIs modernas de Android, impidiendo el uso de binarios locales y periféricos. Para garantizar un acceso robusto al hardware de la sonda, el entorno debe desplegarse desde cero siguiendo estos pasos:

1. **Instalación de Binarios Firmados:** Instalar de forma exclusiva desde la plataforma **F-Droid** tanto el paquete de **Termux** (Emulador) como el complemento **Termux:API** (Puente de hardware). Es obligatorio que compartan la misma firma de origen.
2. **Evasión de Play Protect:** Durante la instalación, el sistema operativo interceptará el APK con una alerta de *"Aplicación no segura bloqueada"*. Para sortear este muro, se debe desplegar el menú contextual de **"Más detalles"** y seleccionar **"Instalar de todos modos"**.

Una vez dentro de la terminal nativa, se levanta el servidor SSH en el puerto alternativo (`8022`) para trabajar de forma remota:

```bash
# Saneamiento del árbol de repositorios e instalación de dependencias core
pkg update && pkg upgrade -y
pkg install git cmake clang make pkg-config fftw python openssh termux-api -y

# Configurar credenciales y levantar el demonio SSH
passwd
sshd
````

> 💡 **Nota sobre rendimiento y persistencia:** Al cambiar de interfaz de red o tras periodos prolongados de inactividad, las directivas de ahorro de energía de Android pausarán la ejecución del entorno. Ejecute imperativamente `termux-wake-lock` para forzar el rendimiento sostenido de la CPU y evadir el estado de suspensión.

Conexión remota desde la estación de desarrollo:

```bash
ssh usuario_termux@IP_DEL_MOVIL -p 8022
```

### 2. Vinculación de Almacenamiento y Control del Módulo de Cámara

Antes de proceder con la ingesta en el modelo de visión, se debe habilitar el hardware óptico para la captura desatendida de frames.

1. **Montaje de Unidades:** Ejecutar en terminal `termux-setup-storage` y otorgar permisos en el pop-up nativo de Android para enlazar la memoria compartida (`~/storage/shared/`).
    
2. **Asignación de Permisos de Hardware:** Dado que Android restringe el acceso a la cámara en segundo plano, se debe navegar manualmente en el SO a: _Ajustes > Aplicaciones > Administrar aplicaciones > Termux:API > Permisos_ y setear la **Cámara** en _"Permitir mientras la app está en uso"_.
    

#### Comando de Captura Autónoma:

Para capturar las imágenes que procesará el modelo Qwen sin depender de entornos gráficos o bucles colgados de intents de usuario, se dispara el sensor directamente hacia la ruta de almacenamiento asignada:

```bash
# Captura de frame mediante el sensor principal trasero (-c 0)
termux-camera-photo -c 0 ~/llama.cpp/models/qwen/foto_sonda.jpg

# Copia opcional al directorio público para telemetría visual o inspección externa
cp ~/llama.cpp/models/qwen/foto_sonda.jpg ~/storage/shared/Download/
```

### 3. Clonación y Compilación de llama.cpp

Para evitar baches matemáticos y desbordamientos de registros vectoriales (_Segmentation Fault - Exit code 139_) comunes al compilar software de IA experimental con versiones punteras de `clang` sobre procesadores ARM64 de última generación, se desactiva la optimización nativa agresiva en favor de una arquitectura estable.

```bash
# Clonar repositorio oficial
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp
mkdir build && cd build

# Configurar CMake en modo de compatibilidad ARM64 estable
cmake .. -DGGML_NATIVE=OFF -DCMAKE_C_FLAGS="-O2" -DCMAKE_CXX_FLAGS="-O2"

# Compilar controlando los hilos (Evita saturar la memoria RAM y Swap de Android)
cmake --build . --config Release -j2
```

La compilación generará con éxito los binarios multimodales unificados dentro del directorio `~/llama.cpp/build/bin/`.

### 4. Descarga de la Suite Qwen3-VL-2B

Los modelos visuales requieren dos componentes acoplados: el archivo del modelo de lenguaje cuantitativo y su proyector de visión (encargado de traducir píxeles a vectores espaciales).


```bash
mkdir -p ~/llama.cpp/models/qwen && cd ~/llama.cpp/models/qwen

# Descargar Modelo Base GGUF (Q4_K_M)
cd ~/llama.cpp/models/qwen && curl -L "https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/resolve/main/Qwen3VL-2B-Instruct-Q4_K_M.gguf" -o Qwen3VL-2B-Instruct-Q4_K_M.gguf --progress-bar -C -

# Descargar Visor/Proyector Multimedia (F16)
curl -L "https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/resolve/main/mmproj-Qwen3VL-2B-Instruct-F16.gguf" -o mmproj-Qwen3VL-2B-Instruct-F16.gguf --progress-bar -C -
```

### 👁️ 5. Optimización del Flujo Multimodal y Restricciones de Imagen (Cuello de Botella del Proyector)

Durante el despliegue práctico en procesadores MediaTek Dimensity (como el Xiaomi 14T), el binario experimental `llama-mtmd-cli` presenta una restricción crítica respecto al tamaño y resolución de los archivos de entrada generados por `termux-camera-photo`.

* **El Problema:** Las imágenes nativas de la cámara (12 MP o superior) fuerzan al proyector visual (`mmproj`) a trocear la imagen en cientos de mosaicos (*tiles*) de $440 \times 440$ píxeles. Esto genera una matriz de atención masiva que satura el bus de la CPU, provocando un bloqueo en bucle infinito (*deadlock*) antes de que el motor llegue siquiera a mapear los archivos en memoria.
* **La Solución:** Redimensionar la imagen de manera desatendida mediante la suite moderna de `ImageMagick` a una resolución ligera ($640 \times 480$) antes de la inferencia. Esto colapsa el uso de RAM a unos estables **1435 MiB** y reduce el tiempo de cómputo a escasos segundos.

#### Dependencias Adicionales de Procesado Visual

```bash
# Instalación del core moderno de ImageMagick para Termux
pkg install imagemagick -y

```

---

### 🤖 6. Orquestación Automatizada: El Script de Control de la Sonda (`sonda_loop.sh`)

Para garantizar la autonomía de la sonda sin interacción humana, se encapsula el comportamiento en un bucle síncrono.

Asimismo, para evitar que la sustitución de comandos de Bash bloquee el script indefinidamente esperando un carácter de fin de transmisión inexistente por parte del CLI, **se implementa un pipeline basado en archivos temporales (`.tmp`)**, garantizando que el hilo principal lea el resultado de la inferencia de forma asíncrona y segura mediante `tail`.

Cree el script de automatización en la raíz del entorno:

```bash
nano ~/sonda_loop.sh

```

Inserte el siguiente código corregido y optimizado con bridas de control de CPU y limitación de hilos:

```bash
#!/data/data/com.termux/files/usr/bin/bash

# ==============================================================================
# ORQUESTRADOR DE CAPTURA E INFERENCIA LOCAL - RUTAS OPTIMIZADAS
# ==============================================================================

# Definición de rutas absolutas del entorno Termux
LLAMA_DIR="$HOME/llama.cpp"
BIN_PATH="$LLAMA_DIR/build/bin/llama-mtmd-cli"
MODEL_PATH="$LLAMA_DIR/models/qwen/Qwen3VL-2B-Instruct-Q4_K_M.gguf"
PROJ_PATH="$LLAMA_DIR/models/qwen/mmproj-Qwen3VL-2B-Instruct-F16.gguf"

# Rutas de almacenamiento intermedio e imágenes
TARGET_IMG="$HOME/imagenes/foto_sonda.jpg"
TARGET_IMG_LOW="$HOME/imagenes/foto_sonda_baja.jpg"
RESULT_TMP="$HOME/imagenes/output_ia.tmp"
LOG_TMP="$LLAMA_DIR/build/llama_log.tmp"

# Plantilla de chat estricta Qwen (Cierre de comillas dobles mandatorio)
PROMPT="<|im_start|>user\nDescribe en una sola frase corta qué se ve en esta imagen.<|im_end|>\n<|im_start|>assistant\n"

echo "====================================================="
echo "  Iniciando bucle de captura autónoma (Cada 30s)..."
echo "  Destino de capturas: ~/imagenes/"
echo "====================================================="

# Asegurar que la CPU de Android no entre en reposo profundo (Mantiene wakelock)
termux-wake-lock

while true; do
    echo "[$(date +%T)] 📸 Capturando frame desde el sensor óptico..."
    
    # 1. Captura de foto desatendida usando la cámara trasera (ID 0)
    termux-camera-photo -c 0 "$TARGET_IMG"
    
    if [ ! -f "$TARGET_IMG" ]; then
        echo "[❌ ERROR] No se pudo generar la imagen en $TARGET_IMG. Reintentando en 5s..."
        sleep 5
        continue
    fi

    # 2. Redimensionamiento preventivo: Evita el colapso del proyector en CPU
    # Es obligatorio definir explícitamente el archivo de salida final ($TARGET_IMG_LOW)
    magick "$TARGET_IMG" -resize 640x480 "$TARGET_IMG_LOW"

    echo "[$(date +%T)] 🧠 Procesando imagen con Qwen3-VL (Inferencia local)..."

    # 3. Inferencia acotada en hilos y contexto
    # -t 4: Limita la computación a 4 núcleos estables (Evita saturar el programador de Android)
    # -c 2048: Reduce la matriz de contexto para optimizar el consumo de RAM
    # --no-warmup: Omite la fase de pre-cálculo matricial acelerando el arranque
    "$BIN_PATH" \
        -m "$MODEL_PATH" \
        --mmproj "$PROJ_PATH" \
        --image "$TARGET_IMG_LOW" \
        -c 2048 \
        -b 256 \
        -t 4 \
        --no-warmup \
        -p "$PROMPT" \
        > "$RESULT_TMP" 2> "$LOG_TMP"

    # 4. Extracción segura del flujo de texto omitiendo metadatos del binario
    TEXTO_DETECTADO=$(tail -n 1 "$RESULT_TMP")

    # Interfaz de salida por consola
    echo "-----------------------------------------------------"
    echo "📝 TEXTO EXTRAÍDO POR LA IA:"
    echo "$TEXTO_DETECTADO"
    echo "-----------------------------------------------------"

    echo "[$(date +%T)] Ciclo completado. Esperando 30 segundos..."
    echo "====================================================="
    sleep 30
done

```

Asigne permisos de ejecución al orquestador antes de lanzarlo:

```bash
chmod +x ~/sonda_loop.sh
./sonda_loop.sh

```

---

### 📊 Consideraciones Técnicas y Telemetría

Durante las pruebas de estrés en el hardware con 12 GB de RAM, se han observado las siguientes métricas de comportamiento del sistema:

* **Gestión Dinámica de Memoria (-fit y contexto acotado):** Mientras que una ejecución sin parámetros intenta reservar por defecto un espacio de contexto masivo inasumible para la arquitectura móvil (colapsando la ejecución con consumos virtuales desproporcionados), la fijación manual a `-c 2048` mantiene el proceso acotado en **1.4 GB fijos de memoria física**. Esto garantiza una estabilidad absoluta a largo plazo frente al *Out-Of-Memory (OOM) Killer* de Android.
* **Fijación de Afinidad de Hilos (`-t 4`):** El procesador MediaTek Dimensity gestiona arquitecturas de núcleos heterogéneos (*Big.LITTLE*). Si no se limita el comando, `llama.cpp` intenta paralelizar las operaciones en los 8 núcleos lógicos del dispositivo simultáneamente (marcando picos ineficientes de hasta 780% de CPU en `top`). Fijar el parámetro en `-t 4` estabiliza el uso del procesador en un **400% constante**, delegando la tarea en los núcleos de alto rendimiento de forma lineal sin saturar el bus de memoria ni generar estrangulamiento térmico (*thermal throttling*).

---

### 🧹 Mantenimiento y Limpieza del Espacio

Para liberar el almacenamiento en el dispositivo de pruebas una vez validadas las hipótesis de laboratorio, se emplean los siguientes comandos de limpieza selectiva:

* **Eliminar imágenes temporales y logs generados por el bucle:** `rm -f ~/imagenes/* && rm -f ~/llama.cpp/build/*.tmp`
* **Eliminar únicamente los modelos VLM (Libera ~2.5 GB):** `rm -rf ~/llama.cpp/models/qwen/*`
* **Eliminar todo el entorno del motor compilado:** `rm -rf ~/llama.cpp`
* **Restaurar el terminal por completo:** Borrar los datos de almacenamiento de la aplicación Termux desde el menú nativo de *Ajustes > Aplicaciones > Termux > Almacenamiento > Borrar datos*.
