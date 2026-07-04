# Despliegue de Visión Artificial Local (Qwen3-VL) en Dispositivos Android mediante Termux

Este componente del proyecto describe la infraestructura, el proceso de compilación y la ejecución de Modelos de Lenguaje Multimodales (VLM) de forma 100% local en un smartphone embebido. El objetivo final es dotar a la sonda de capacidad de "percepción visual" autónoma para analizar el entorno sin dependencia de conectividad en la nube.

---

## 🛠️ Arquitectura y Componentes del Sistema

* **Hardware de Pruebas:** Xiaomi 14T (Procesador MediaTek Dimensity 8300 Ultra, 12 GB LPDDR5X RAM).
* **Entorno de Ejecución:** Termux (Emulador de terminal y entorno Linux aislado para Android).
* **Motor de Inferencia:** `llama.cpp` (Compilado de forma nativa en el dispositivo).
* **Modelo de Visión (VLM):** Qwen3-VL-2B-Instruct (Cuantización `Q4_K_M` para el LLM + Proyector Visual `F16`).

---

## 🚀 Guía de Despliegue Paso a Paso

### 1. Preparación del Entorno (SSH y Dependencias)
Para trabajar cómodamente desde el ordenador de desarrollo, se levanta un servidor SSH en el puerto alternativo de Termux (`8022`) y se instalan las herramientas de compilación esenciales.

```bash
# Actualizar repositorios e instalar paquetes críticos
pkg update && pkg upgrade -y
pkg install git cmake clang make pkg-config fftw python openssh termux-api -y

# Configurar credenciales y levantar el demonio SSH
passwd
sshd

```

> **Nota sobre redes:** Al cambiar de Wi-Fi o tras periodos de inactividad, Android puede pausar el proceso. Se recomienda ejecutar `termux-wake-lock` para asegurar el rendimiento sostenido de la CPU y evitar el modo suspensión.

Conectar desde el equipo de desarrollo local mediante:

```bash
ssh usuario_termux@IP_DEL_MOVIL -p 8022

```

---

### 2. Clonación y Compilación de `llama.cpp`

Para evitar baches matemáticos y desbordamientos de registros vectoriales (*Segmentation Fault - Exit code 139*) comunes al compilar software de IA experimental con versiones punteras de `clang` sobre procesadores ARM64 de última generación, se desactiva la optimización nativa agresiva en favor de una arquitectura estable.

```bash
# Clonar repositorio oficial
git clone [https://github.com/ggerganov/llama.cpp](https://github.com/ggerganov/llama.cpp)
cd llama.cpp
mkdir build && cd build

# Configurar CMake en modo de compatibilidad ARM64 estable
cmake .. -DGGML_NATIVE=OFF -DCMAKE_C_FLAGS="-O2" -DCMAKE_CXX_FLAGS="-O2"

# Compilar controlando los hilos (Evita saturar la memoria RAM y Swap de Android)
cmake --build . --config Release -j2

```

La compilación generará con éxito los binarios multimodales unificados dentro del directorio `~/llama.cpp/build/bin/`.

---

### 3. Descarga de la Suite Qwen3-VL-2B

Los modelos visuales requieren dos componentes acoplados: el archivo del modelo de lenguaje cuantitativo y su proyector de visión (encargado de traducir píxeles a vectores espaciales).

```bash
mkdir -p ~/llama.cpp/models/qwen && cd ~/llama.cpp/models/qwen

# Descargar Modelo Base GGUF (Q4_K_M)
curl -L "[https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/resolve/main/Qwen3VL-2B-Instruct-Q4_K_M.gguf](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/resolve/main/Qwen3VL-2B-Instruct-Q4_K_M.gguf)" \
  -o Qwen3VL-2B-Instruct-Q4_K_M.gguf --progress-bar -C -

# Descargar Visor/Proyector Multimedia (F16)
curl -L "[https://huggingfaAquí tienes un archivo `README.md` completo, estructurado y listo para usar como documentación de esta fase del proyecto. Está redactado con un enfoque técnico pero didáctico, ideal para registrar el proceso de despliegue de la IA local en el hardware de la sonda.
```

---

# Despliegue de Visión Artificial Local (Qwen3-VL) en Dispositivos Android mediante Termux

Este componente del proyecto describe la infraestructura, el proceso de compilación y la ejecución de Modelos de Lenguaje Multimodales (VLM) de forma 100% local en un smartphone embebido. El objetivo final es dotar a la sonda de capacidad de "percepción visual" autónoma para analizar el entorno sin dependencia de conectividad en la nube.

---

## 🛠️ Arquitectura y Componentes del Sistema

* **Hardware de Pruebas:** Xiaomi 15T (Procesador MediaTek Dimensity 8400 Ultra, 12 GB LPDDR5X RAM).
* **Entorno de Ejecución:** Termux (Emulador de terminal y entorno Linux aislado para Android).
* **Motor de Inferencia:** `llama.cpp` (Compilado de forma nativa en el dispositivo).
* **Modelo de Visión (VLM):** Qwen3-VL-2B-Instruct (Cuantización `Q4_K_M` para el LLM + Proyector Visual `F16`).

---

## 🚀 Guía de Despliegue Paso a Paso

### 1. Preparación del Entorno (SSH y Dependencias)
Para trabajar cómodamente desde el ordenador de desarrollo, se levanta un servidor SSH en el puerto alternativo de Termux (`8022`) y se instalan las herramientas de compilación esenciales.

```bash
# Actualizar repositorios e instalar paquetes críticos
pkg update && pkg upgrade -y
pkg install git cmake clang make pkg-config fftw python openssh termux-api -y

# Configurar credenciales y levantar el demonio SSH
passwd
sshd

```

> **Nota sobre redes:** Al cambiar de Wi-Fi o tras periodos de inactividad, Android puede pausar el proceso. Se recomienda ejecutar `termux-wake-lock` para asegurar el rendimiento sostenido de la CPU y evitar el modo suspensión.

Conectar desde el equipo de desarrollo local mediante:

```bash
ssh usuario_termux@IP_DEL_MOVIL -p 8022

```

---

### 2. Clonación y Compilación de `llama.cpp`

Para evitar baches matemáticos y desbordamientos de registros vectoriales (*Segmentation Fault - Exit code 139*) comunes al compilar software de IA experimental con versiones punteras de `clang` sobre procesadores ARM64 de última generación, se desactiva la optimización nativa agresiva en favor de una arquitectura estable.

```bash
# Clonar repositorio oficial
git clone [https://github.com/ggerganov/llama.cpp](https://github.com/ggerganov/llama.cpp)
cd llama.cpp
mkdir build && cd build

# Configurar CMake en modo de compatibilidad ARM64 estable
cmake .. -DGGML_NATIVE=OFF -DCMAKE_C_FLAGS="-O2" -DCMAKE_CXX_FLAGS="-O2"

# Compilar controlando los hilos (Evita saturar la memoria RAM y Swap de Android)
cmake --build . --config Release -j2

```

La compilación generará con éxito los binarios multimodales unificados dentro del directorio `~/llama.cpp/build/bin/`.

---

### 3. Descarga de la Suite Qwen3-VL-2B

Los modelos visuales requieren dos componentes acoplados: el archivo del modelo de lenguaje cuantitativo y su proyector de visión (encargado de traducir píxeles a vectores espaciales).

```bash
mkdir -p ~/llama.cpp/models/qwen && cd ~/llama.cpp/models/qwen

# Descargar Modelo Base GGUF (Q4_K_M)
curl -L "[https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/resolve/main/Qwen3VL-2B-Instruct-Q4_K_M.gguf](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/resolve/main/Qwen3VL-2B-Instruct-Q4_K_M.gguf)" \
  -o Qwen3VL-2B-Instruct-Q4_K_M.gguf --progress-bar -C -

# Descargar Visor/Proyector Multimedia (F16)
curl -L "[https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/resolve/main/mmproj-Qwen3VL-2B-Instruct-F16.gguf](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/resolve/main/mmproj-Qwen3VL-2B-Instruct-F16.gguf)" \
  -o mmproj-Qwen3VL-2B-Instruct-F16.gguf --progress-bar -C -

```

---

## 👁️ Ejecución de la Inferencia Visual

Para procesar una imagen, utilizamos el binario unificado para multi-fusión de tareas de `llama.cpp` (`llama-mtmd-cli`). Es imperativo estructurar el prompt con la plantilla de chat oficial de Qwen (`<|im_start|>`) para asegurar respuestas directas sin bucles sintácticos.

```bash
cd ~/llama.cpp/build

./bin/llama-mtmd-cli \
  -m ../models/qwen/Qwen3VL-2B-Instruct-Q4_K_M.gguf \
  --mmproj ../models/qwen/mmproj-Qwen3VL-2B-Instruct-F16.gguf \
  --image /ruta/a/tu/imagen.jpg \
  -p "<|im_start|>user\nDescribe en una sola frase corta qué se ve en esta imagen.<|im_end|>\n<|im_start|>assistant\n"

```

---

## 📊 Consideraciones Técnicas y Telemetría

Durante las pruebas de estrés en el hardware con 12 GB de RAM, se han observado las siguientes métricas de comportamiento del sistema:

* **Gestión Dinámica de Memoria (`-fit`):** Aunque el mapa conceptual inicial del proyector visual estima un techo teórico alto de memoria virtual, el flag de auto-ajuste de `llama.cpp` empaqueta con éxito los pesos dentro de la memoria física disponible, garantizando estabilidad sin provocar el cierre forzado de la app por parte del *Out-Of-Memory (OOM) Killer* de Android.
* **Aviso de Tokens de Imagen:** El motor sugiere configuraciones altas (`--image-min-tokens 1024`) para análisis milimétricos de coordenadas de objetos (*grounding*). No obstante, para tareas descriptivas globales, la configuración estándar es óptima y reduce el tiempo de cómputo por imagen.

---

## 🧹 Mantenimiento y Limpieza del Espacio

Para revertir los cambios o liberar almacenamiento en el dispositivo de pruebas una vez validada la hipótesis, se pueden emplear los siguientes comandos de limpieza selectiva:

* **Eliminar únicamente los modelos (Libera ~2.5 GB):**
```bash
rm -rf ~/llama.cpp/models/qwen/*

```


* **Eliminar todo el entorno del motor compilado:**
```bash
rm -rf ~/llama.cpp

```


* **Restaurar el terminal por completo:** Borrar los datos de almacenamiento de la aplicación *Termux* desde el menú de *Ajustes > Aplicaciones* de Android.

```

***

Te deja las bases perfectas por si metes este desarrollo en un repositorio de GitHub, Notion o la memoria técnica de tu sistema de gestión. ¿Añadimos un apartado con el esquema de conexiones físicas o prefieres guardarlo así por ahora?

```ce.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/resolve/main/mmproj-Qwen3VL-2B-Instruct-F16.gguf](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/resolve/main/mmproj-Qwen3VL-2B-Instruct-F16.gguf)" \
  -o mmproj-Qwen3VL-2B-Instruct-F16.gguf --progress-bar -C -

```

---

## 👁️ Ejecución de la Inferencia Visual

Para procesar una imagen, utilizamos el binario unificado para multi-fusión de tareas de `llama.cpp` (`llama-mtmd-cli`). Es imperativo estructurar el prompt con la plantilla de chat oficial de Qwen (`<|im_start|>`) para asegurar respuestas directas sin bucles sintácticos.

```bash
cd ~/llama.cpp/build

./bin/llama-mtmd-cli \
  -m ../models/qwen/Qwen3VL-2B-Instruct-Q4_K_M.gguf \
  --mmproj ../models/qwen/mmproj-Qwen3VL-2B-Instruct-F16.gguf \
  --image /ruta/a/tu/imagen.jpg \
  -p "<|im_start|>user\nDescribe en una sola frase corta qué se ve en esta imagen.<|im_end|>\n<|im_start|>assistant\n"

```

---

Aquí tienes un archivo `README.md` completo, estructurado y listo para usar como documentación de esta fase del proyecto. Está redactado con un enfoque técnico pero didáctico, ideal para registrar el proceso de despliegue de la IA local en el hardware de la sonda.

---

# Despliegue de Visión Artificial Local (Qwen3-VL) en Dispositivos Android mediante Termux

Este componente del proyecto describe la infraestructura, el proceso de compilación y la ejecución de Modelos de Lenguaje Multimodales (VLM) de forma 100% local en un smartphone embebido. El objetivo final es dotar a la sonda de capacidad de "percepción visual" autónoma para analizar el entorno sin dependencia de conectividad en la nube.

---

## 🛠️ Arquitectura y Componentes del Sistema

* **Hardware de Pruebas:** Xiaomi 15T (Procesador MediaTek Dimensity 8400 Ultra, 12 GB LPDDR5X RAM).
* **Entorno de Ejecución:** Termux (Emulador de terminal y entorno Linux aislado para Android).
* **Motor de Inferencia:** `llama.cpp` (Compilado de forma nativa en el dispositivo).
* **Modelo de Visión (VLM):** Qwen3-VL-2B-Instruct (Cuantización `Q4_K_M` para el LLM + Proyector Visual `F16`).

---

## 🚀 Guía de Despliegue Paso a Paso

### 1. Preparación del Entorno (SSH y Dependencias)
Para trabajar cómodamente desde el ordenador de desarrollo, se levanta un servidor SSH en el puerto alternativo de Termux (`8022`) y se instalan las herramientas de compilación esenciales.

```bash
# Actualizar repositorios e instalar paquetes críticos
pkg update && pkg upgrade -y
pkg install git cmake clang make pkg-config fftw python openssh termux-api -y

# Configurar credenciales y levantar el demonio SSH
passwd
sshd

```

> **Nota sobre redes:** Al cambiar de Wi-Fi o tras periodos de inactividad, Android puede pausar el proceso. Se recomienda ejecutar `termux-wake-lock` para asegurar el rendimiento sostenido de la CPU y evitar el modo suspensión.

Conectar desde el equipo de desarrollo local mediante:

```bash
ssh usuario_termux@IP_DEL_MOVIL -p 8022

```

---

### 2. Clonación y Compilación de `llama.cpp`

Para evitar baches matemáticos y desbordamientos de registros vectoriales (*Segmentation Fault - Exit code 139*) comunes al compilar software de IA experimental con versiones punteras de `clang` sobre procesadores ARM64 de última generación, se desactiva la optimización nativa agresiva en favor de una arquitectura estable.

```bash
# Clonar repositorio oficial
git clone [https://github.com/ggerganov/llama.cpp](https://github.com/ggerganov/llama.cpp)
cd llama.cpp
mkdir build && cd build

# Configurar CMake en modo de compatibilidad ARM64 estable
cmake .. -DGGML_NATIVE=OFF -DCMAKE_C_FLAGS="-O2" -DCMAKE_CXX_FLAGS="-O2"

# Compilar controlando los hilos (Evita saturar la memoria RAM y Swap de Android)
cmake --build . --config Release -j2

```

La compilación generará con éxito los binarios multimodales unificados dentro del directorio `~/llama.cpp/build/bin/`.

---

### 3. Descarga de la Suite Qwen3-VL-2B

Los modelos visuales requieren dos componentes acoplados: el archivo del modelo de lenguaje cuantitativo y su proyector de visión (encargado de traducir píxeles a vectores espaciales).

```bash
mkdir -p ~/llama.cpp/models/qwen && cd ~/llama.cpp/models/qwen

# Descargar Modelo Base GGUF (Q4_K_M)
curl -L "[https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/resolve/main/Qwen3VL-2B-Instruct-Q4_K_M.gguf](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/resolve/main/Qwen3VL-2B-Instruct-Q4_K_M.gguf)" \
  -o Qwen3VL-2B-Instruct-Q4_K_M.gguf --progress-bar -C -

# Descargar Visor/Proyector Multimedia (F16)
curl -L "[https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/resolve/main/mmproj-Qwen3VL-2B-Instruct-F16.gguf](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/resolve/main/mmproj-Qwen3VL-2B-Instruct-F16.gguf)" \
  -o mmproj-Qwen3VL-2B-Instruct-F16.gguf --progress-bar -C -

```

---

## 👁️ Ejecución de la Inferencia Visual

Para procesar una imagen, utilizamos el binario unificado para multi-fusión de tareas de `llama.cpp` (`llama-mtmd-cli`). Es imperativo estructurar el prompt con la plantilla de chat oficial de Qwen (`<|im_start|>`) para asegurar respuestas directas sin bucles sintácticos.

```bash
cd ~/llama.cpp/build

./bin/llama-mtmd-cli \
  -m ../models/qwen/Qwen3VL-2B-Instruct-Q4_K_M.gguf \
  --mmproj ../models/qwen/mmproj-Qwen3VL-2B-Instruct-F16.gguf \
  --image /ruta/a/tu/imagen.jpg \
  -p "<|im_start|>user\nDescribe en una sola frase corta qué se ve en esta imagen.<|im_end|>\n<|im_start|>assistant\n"

```

---

## 📊 Consideraciones Técnicas y Telemetría

Durante las pruebas de estrés en el hardware con 12 GB de RAM, se han observado las siguientes métricas de comportamiento del sistema:

* **Gestión Dinámica de Memoria (`-fit`):** Aunque el mapa conceptual inicial del proyector visual estima un techo teórico alto de memoria virtual, el flag de auto-ajuste de `llama.cpp` empaqueta con éxito los pesos dentro de la memoria física disponible, garantizando estabilidad sin provocar el cierre forzado de la app por parte del *Out-Of-Memory (OOM) Killer* de Android.
* **Aviso de Tokens de Imagen:** El motor sugiere configuraciones altas (`--image-min-tokens 1024`) para análisis milimétricos de coordenadas de objetos (*grounding*). No obstante, para tareas descriptivas globales, la configuración estándar es óptima y reduce el tiempo de cómputo por imagen.

---

## 🧹 Mantenimiento y Limpieza del Espacio

Para revertir los cambios o liberar almacenamiento en el dispositivo de pruebas una vez validada la hipótesis, se pueden emplear los siguientes comandos de limpieza selectiva:

* **Eliminar únicamente los modelos (Libera ~2.5 GB):**
```bash
rm -rf ~/llama.cpp/models/qwen/*

```


* **Eliminar todo el entorno del motor compilado:**
```bash
rm -rf ~/llama.cpp

```


* **Restaurar el terminal por completo:** Borrar los datos de almacenamiento de la aplicación *Termux* desde el menú de *Ajustes > Aplicaciones* de Android.

```

***

Te deja las bases perfectas por si metes este desarrollo en un repositorio de GitHub, Notion o la memoria técnica de tu sistema de gestión. ¿Añadimos un apartado con el esquema de conexiones físicas o prefieres guardarlo así por ahora?

```## 📊 Consideraciones Técnicas y Telemetría

Durante las pruebas de estrés en el hardware con 12 GB de RAM, se han observado las siguientes métricas de comportamiento del sistema:

* **Gestión Dinámica de Memoria (`-fit`):** Aunque el mapa conceptual inicial del proyector visual estima un techo teórico alto de memoria virtual, el flag de auto-ajuste de `llama.cpp` empaqueta con éxito los pesos dentro de la memoria física disponible, garantizando estabilidad sin provocar el cierre forzado de la app por parte del *Out-Of-Memory (OOM) Killer* de Android.
* **Aviso de Tokens de Imagen:** El motor sugiere configuraciones altas (`--image-min-tokens 1024`) para análisis milimétricos de coordenadas de objetos (*grounding*). No obstante, para tareas descriptivas globales, la configuración estándar es óptima y reduce el tiempo de cómputo por imagen.

---

## 🧹 Mantenimiento y Limpieza del Espacio

Para revertir los cambios o liberar almacenamiento en el dispositivo de pruebas una vez validada la hipótesis, se pueden emplear los siguientes comandos de limpieza selectiva:

* **Eliminar únicamente los modelos (Libera ~2.5 GB):**
```bash
rm -rf ~/llama.cpp/models/qwen/*

```


* **Eliminar todo el entorno del motor compilado:**
```bash
rm -rf ~/llama.cpp

```


* **Restaurar el terminal por completo:** Borrar los datos de almacenamiento de la aplicación *Termux* desde el menú de *Ajustes > Aplicaciones* de Android.
* 