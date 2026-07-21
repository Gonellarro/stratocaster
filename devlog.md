# Devlog: Sonda IoT - Integración de Cámara y Telemetría en Grafana

**Fecha:** 2026-07-03  
**Sesión:** Integración de captura de imágenes, inferencia local de IA (Qwen3-VL) y geolocalización dual en el ecosistema TIG (Telegraf + InfluxDB + Grafana).

---

## 1. Resumen de la Arquitectura Diseñada
Se ha ampliado el ecosistema de telemetría GPS original para incorporar una cámara autónoma en un dispositivo Android remoto.
El flujo opera bajo las siguientes reglas:
* **Android (Termux):** Captura imágenes del sensor óptico, ejecuta inferencia local con `Qwen3-VL` (vía `llama.cpp`) para describirlas en una frase corta, geolocaliza la sonda usando el GPS del móvil y sube la foto + telemetría a través de internet (Wifi/3G/4G).
* **Servidor (Hospedaje de Fotos):** Un microservicio contenedorizado recibe la foto y la expone mediante HTTPS (detrás de Nginx Proxy Manager).
* **Ingesta:** El móvil publica los resultados (enlace de foto, texto de la IA y GPS) vía MQTT al broker Mosquitto. Telegraf ingesta esta información en InfluxDB v2.
* **Visualización:** Grafana unifica el mapa del Lora, el mapa del móvil, los históricos de altitud y una galería de fotos dinámicas con sincronización temporal interactiva.

---

## 2. Cambios Implementados en el Código

### 📱 Script Sonda Móvil (`codigo/Android/`)
* **[sonda_loop.sh](file:///home/marti/Documentos/Personal/Sonda/codigo/Android/sonda_loop.sh):**
  * **Wake Lock seguro:** Implementado un control `trap` para liberar automáticamente el bloqueo de CPU de Android (`termux-wake-unlock`) al cerrar el script (evitando el drenaje involuntario de batería).
  * **Manejo de permisos en Android 10+:** Reemplazado el comando `ip route` (restringido en móviles modernos) por el comando oficial de la API de Termux `termux-wifi-connectioninfo` para detectar el estado del Wifi de forma limpia y recuperar la IP asignada.
  * **Ubicación temporal:** Corregida la redirección del log de compilación de `/tmp/` (restringida en Termux) a una carpeta de usuario escribible (`$HOME/imagenes/llama_log.tmp`).
  * **Geolocalización Móvil:** Integrada la adquisición de coordenadas (Latitud, Longitud, Altitud) usando `termux-location` con timeouts y fallbacks seguros a localización por red móvil si el GPS carece de cobertura bajo techo.
  * **Subida y MQTT:** Añadida subida mediante `curl` multipart al servidor de imágenes y publicación JSON en MQTT.
* **[sonda.env.example](file:///home/marti/Documentos/Personal/Sonda/codigo/Android/sonda.env.example):**
  * Creado un archivo plantilla para desacoplar las variables sensibles (contraseña de Mosquitto, dominio del servidor) y cargarlas mediante variables de entorno dinámicas en el shell sin comprometer la seguridad en Git.

### 🐳 Infraestructura Servidor (`docker-TIG/`)
* **Servidor de Imágenes (`docker-broadcast/image-store/`):**
  * Creado un microservicio ligero en Python usando **Flask** (`app.py` y `Dockerfile`).
  * Genera un UUID único para cada foto subida para prevenir colisiones de nombres.
  * Almacena las fotos en un volumen físico persistente `./images` expuesto en el puerto `5000` (diseñado para rutarse de forma segura mediante HTTPS en Nginx Proxy Manager).
  * **Miniweb de Galería (`/fotos`):** Creada una interfaz web integrada en el puerto `5000/fotos`. Genera una vista de galería en modo oscuro fluido y moderno (fuente Google Outfit, bordes difuminados, sombras de neón). Incluye un visor a pantalla completa (*lightbox*) para ampliar las imágenes con su descripción al hacer clic sobre ellas.
  * **Asociación de metadatos:** Guarda un archivo `.json` de metadatos al lado de cada foto para registrar la descripción de la IA y la marca de tiempo de subida en tiempo real.
* **[docker-compose.yml](file:///home/marti/Documentos/Personal/Sonda/docker-TIG/docker-compose.yml):**
  * Integrado el nuevo servicio `image-store` en la pila de contenedores.
* **[telegraf.conf](file:///home/marti/Documentos/Personal/Sonda/docker-TIG/telegraf/telegraf.conf):**
  * Añadida la entrada `INPUT 3` para suscribir a Telegraf al nuevo topic MQTT `sonda/camera`.
  * Configurados los campos de string `texto` y `url_imagen` para que InfluxDB los almacene de forma nativa sin errores de tipado.

### 📊 Cuadro de Mando (`Sonda LORA-*.json`)
Se actualizó el dashboard de Grafana con las siguientes mejoras:
* **Mapa de Posición (`Geomap` nativo):**
  * Reemplazado el plugin clásico de trackmap por el panel nativo **Geomap** de Grafana.
  * Creadas 3 capas de datos enrutadas mediante `RefId`:
    1. **Ruta ESP32 Lora (Línea Roja):** Trayecto histórico del Lora.
    2. **Puntos Lora (Marcadores Rojos):** Nodos del Lora.
    3. **Fotos Móvil (Marcadores Cian):** Puntos donde el móvil reportó y geolocalizó fotos.
  * Configurada la opción de centrado automático (`allData: true`).
  * Las consultas del mapa ahora respetan la variable de parada de tiempo del dashboard (`stop: v.timeRangeStop`).
* **Tabla de Galería de Fotos:**
  * Creada una tabla interactiva que oculta las coordenadas y muestra únicamente la hora, el texto descriptivo de la IA (ancho `600px`) y la imagen.
  * El alto de la celda de la tabla se ha establecido como numérico (`150px`) y el ancho de la columna en `350px` para renderizar las imágenes grandes y claras en el propio dashboard.
  * **Sincronización por Enlace Temporal (Data Links):**
    * **Enlace de Foto:** Un clic en la celda de la imagen abre la foto original a resolución completa en otra pestaña.
    * **Enlace de Tiempo:** Al hacer clic en el timestamp de una foto en la tabla, el dashboard entero (incluido el mapa y las gráficas) se enfoca y se "rebobina" a ese segundo exacto de tiempo, facilitando la auditoría de telemetría histórica.

---

## 3. Guía de Despliegue Técnico (Siguiente Sesión)
Cuando decidas migrar los cambios al servidor principal, el checklist ordenado es:
1. Transferir las carpetas `docker-TIG/` y `docker-broadcast/` al servidor (o hacer `git pull` en la carpeta raíz del proyecto).
2. Copiar el archivo `telegraf.conf` actualizado al servidor (`docker-TIG/telegraf/telegraf.conf`) y reiniciar Telegraf (`docker compose restart telegraf`).
3. Levantar la pila de telemetría: `cd docker-TIG && docker compose up -d --build`.
4. Levantar la pila de retransmisión: `cd docker-broadcast && docker compose up -d --build`.
5. En **Nginx Proxy Manager**, añadir el Proxy Host para redirigir tu subdominio `sondafotos.martivich.es` al contenedor `image-store` en el puerto `5000` con SSL forzado.
   * **Tip para la Miniweb:** El panel de control estará en `/control` y la galería en `/fotos` (ej: `https://sondafotos.martivich.es/control`).
6. En el teléfono móvil, crear el archivo `sonda.env` a partir del de ejemplo y rellenar las contraseñas.
7. Importar el archivo JSON final en Grafana.

---

**Fecha:** 2026-07-05 / 2026-07-06  
**Sesión:** Implementación del HUD de OBS estilo SpaceX, soporte de WebSockets en Mosquitto, y optimización de la consola de control pre-vuelo en tierra.

## 1. Habilitación de WebSockets en Mosquitto (Puerto 9001)
* **Objetivo:** Permitir que los navegadores web (como OBS Browser Source o la propia consola de control) se conecten directamente al broker MQTT en tiempo real.
* **Configuración:**
  * Modificado `mosquitto.conf` para habilitar el puerto `9001` con el protocolo `websockets` y autenticación requerida.
  * Creado el archivo encriptado `password_file` para el usuario `admin` y aplicados permisos seguros `644` en el servidor para que el Docker de Mosquitto lo pueda leer.
  * Añadida la autenticación MQTT al cliente JavaScript en la web de control (`app.py`) y en el HUD de OBS (`telemetria.html`).

## 2. Rediseño del HUD de OBS estilo SpaceX (`codigo/HUD/telemetria.html`)
* **Diseño:** Recreado el icónico panel de telemetría inferior de la retransmisión de SpaceX (Starship):
  * Dos gauges de 270 grados en las esquinas inferiores para **Velocidad (KM/H)**, **Altitud (M / KM)**, **Temperatura (°C)** y **Presión Atmosférica (hPa)**.
  * **Cálculos Dinámicos:**
    * **Presión:** Calculada mediante la fórmula barométrica estándar internacional según la altitud de la sonda.
    * **Recorrido:** Cálculo de la distancia en línea recta desde la rampa mediante la fórmula Haversine.
    * **Dirección (Rumbo):** Rumbo en grados (`0°-359°`) y rosa de vientos (`N`, `NE`, `SW`...) calculado vectorialmente en base a su desviación de las coordenadas iniciales.
  * **Arco de Trayectoria Central:** Un perfil parabólico SVG con hitos de vuelo (`DESPEGUE`, `1.000m`, `APOGEO`, `DESCENSO`, `RECUPERACIÓN`) donde un marcador cian se desplaza dinámicamente según la altura reportada por la sonda.
  * **Reloj de Misión:** T-minus para la cuenta atrás (rojo neón) y cronómetro ascendente (`T+`) dinámico tras el despegue.
  * **Caja de IA Flotante:** Caja inferior translúcida que muestra la descripción que la IA local de la sonda va dictando.

## 3. Automatizaciones y Tests Pre-vuelo en la Consola (`app.py`)
* **Consola de Control (`/control`):**
  * Añadido el botón de **`🛰️ Inicializar GPS`** y de **`📸 Test Foto/IA`**.
  * Incorporada la validación completa en el checklist (se requiere confirmar GPS, batería, altavoz TTS, stream de vídeo y test de IA/Cámara para que el botón de Armar se active).
  * Soporte de reinicio completo (Abortar) para limpiar todos los estados en un solo clic.

## 4. Corrección de Bug y Optimización del Script del Móvil (`sonda_loop.sh`)
* **Telemetría Automática:** Añadido un bucle en la fase 0 para enviar telemetría (batería, GPS) automáticamente al broker cada 10 segundos mientras la sonda esté en tierra esperando el armado.
* **Comando `init_gps`:** Comando bajo demanda que fuerza una búsqueda de satélites activa sin caché (`termux-location -p gps` de 20s en segundo plano), guiando al operador por voz TTS y actualizando el estado de búsqueda en la web.
* **Comando `test_photo`:** Captura una foto, hace inferencia local en baja resolución para evitar Out Of Memory (OOM) del móvil, pero sube la imagen original en alta resolución a la web por `curl`.
* **Solución al Cuelgue del Script (Stdin Hijacking):** Corregido un sutil bug de pipes de Bash donde `llama-mtmd-cli` se quedaba congelado. Se solucionó redireccionando la entrada estándar a `/dev/null` (`</dev/null`) tanto en las llamadas a la IA como al receptor de comandos de fondo.
---

**Fecha:** 2026-07-06  
**Sesión:** Secuenciador asíncrono pre-vuelo, reintentos con animación de puntos suspensivos en checklist y robustez de GPS en interiores.

## 1. Asincronismo Completo en el Móvil (`sonda_loop.sh`)
* **Ejecución Asíncrona (`&`):** Lanzados los comandos internos del receptor MQTT en segundo plano (`handle_command "$CMD" </dev/null &`). Esto evita que procesos lentos (como hablar por TTS o procesar fotos con la IA local) bloqueen la lectura de la tubería MQTT de Termux.

## 2. Robustez de Geolocalización y Fallback GPS
* **Fallback a Red Celular/WiFi:** Modificado el comando `init_gps` del móvil para que intente primero una búsqueda de satélites física (`gps` durante 15s) y, si falla (como en interiores), intente por red (`network` durante 8s). Esto asegura que el test de posicionamiento funcione tanto bajo techo como en campo abierto.
* **Control Web de Satélites:** Habilitada la recepción de los estados `gps_ok` y `gps_failed` en el cliente JavaScript de `/control`, permitiendo actualizar las coordenadas y marcar el GPS como verificado de inmediato.

## 3. Secuenciador Visual de Autotest
* **Animación de Puntos Suspendidos:** Implementada una animación CSS de máquina de escribir de tres puntos horizontales (`...`) en la casilla de verificación mientras se está realizando una prueba.
* **Reintentos Dinámicos:** Asignados números de reintentos configurables por paso para evitar esperas interminables en pruebas lentas (ej: 1 intento para GPS o LoRa, 3 para la IP del móvil, 2 para TTS).
* **Nivel de Batería Tricolor:** Clasificación de batería en tres niveles de color en el checklist: Verde (Ok, >=75%), Naranja (Warn, 50-74%) y Rojo (Ko, <50%).
* **Prevención de Conflictos de Cámara:** Añadido un `am force-stop` a Chrome/VDO.ninja al inicio de `test_photo` en el móvil, garantizando que el hardware de la cámara quede libre para el disparo del test de foto/IA.
* **Reordenación y Simplificación de Checklist:** Reordenado el listado HTML para coincidir exactamente con el orden secuencial del script de pruebas. Eliminado el paso de test de vídeo automático para evitar congelamientos en caliente.
* **Bypass de LoRa y Meshtastic:** Se configuraron ambos enlaces para que carguen en verde (`ok`/`Omitido`) directamente al iniciar o resetear, evitando esperas pasivas y permitiendo al operador centrarse en el móvil y la cámara.
* **Animación de Spinner de Neón:** Reemplazada la animación de los puntos suspensivos por un mini spinner circular de neón cian que gira fluidamente en el interior del checkbox mientras la prueba está en progreso.

## 4. Refactorización y Separación del Frontend (HTML/CSS/JS)
* **Arquitectura limpia:** Separados los enormes templates inline de Python/Flask a sus carpetas correspondientes:
  - `templates/control.html` y `templates/fotos.html`
  - `static/css/control.css` y `static/css/fotos.css`
  - `static/js/control.js` y `static/js/fotos.js`
* **Limpieza de app.py:** Reducido `app.py` de más de 1900 líneas a solo 160 líneas de pura lógica de Flask, mejorando drásticamente el mantenimiento.
* **Actualización de Dockerfile:** Modificado para copiar toda la estructura del directorio (`COPY . .`) y no solo el script python, garantizando que el contenedor tenga acceso a las vistas estáticas.

## 5. Optimización del GPS, Control de Timeouts y Simplificación de Inferencia
* **Suscripción Pasiva del GPS:** Implementada una escucha pasiva (`termux-location -r updates`) en segundo plano que escribe las coordenadas de forma continua en `gps_updates.json`. Las consultas posteriores leen el archivo de forma instantánea (`tail -n 1`), eliminando por completo los bloqueos de 15 segundos causados por el encendido y apagado reiterado del chip del GPS.
* **Control de Timeouts en Voz (TTS):** Envuelta la ejecución de `termux-tts-speak` con `timeout 5` para evitar que el script se bloquee indefinidamente y se acumulen procesos zombis en Termux si el motor de síntesis de voz de Android se congela.
* **Eliminación de IA Local (llama.cpp) en el Móvil:** Retirada la carga del modelo de IA `Qwen-VL` y el comando `llama-mtmd-cli` del script `sonda_loop.sh`. Al delegar el procesamiento pesado fuera del teléfono, el uso de memoria RAM del script ha bajado de más de 2.5 GB a unos pocos megabytes, solucionando de raíz las terminaciones forzadas del sistema operativo (`Signal 9`).
* **Habilitación de Cuenta Atrás:** Modificada la validación `isReady` de la consola de control para omitir los checks puenteados de LoRa y vídeo, permitiendo que el botón "Iniciar cuenta atrás" se active correctamente en cuanto los componentes del móvil pasen a color verde.
* **Auto-centrado del Mapa:** Añadido un detector en el cliente web que centra y desplaza el mapa automáticamente (`setView`) en la posición de la sonda en cuanto se recibe el primer paquete geográfico válido.

## 6. Rediseño Estético y Layout Premium de la Consola
* **Esquema de Colores Premium:** Adoptada la paleta de colores azul/navy oscuro (`#080b11` y `#0f1322`) con bordes en azul oscuro (`#1a2035`) y acentos en azul cielo y verde, según la imagen de referencia.
* **Cabecera de Estado Persistente:** Añadido un header superior de ancho completo que unifica el título del proyecto y los indicadores dinámicos (Píldora de estado general, código de misión activa, temporizador y contador de satélites).
* **Compresión del Checklist:** Se disminuyeron los márgenes, rellenos y el tamaño de fuente en la lista de comprobaciones para evitar desplazamientos verticales en pantallas medianas.
* **Tarjeta de Telemetría Multipropósito (Mini-Cards):** Se eliminó la antigua tabla comparativa y se reemplazó por 6 tarjetas horizontales independientes. Añadida una barra de nivel de batería dinámica interactiva.
* **Compatibilidad de Lógica JS:** Mapeados todos los selectores de telemetría históricos en un bloque oculto del HTML, manteniendo compatibilidad total de actualización sin alterar el script cliente.
* **Estructura Lateral Menú:** Ampliado el menú de la barra izquierda con los accesos directos simulados solicitados (Misión, Telemetría, Mapa, Cámara, Meshtastic, Registros, y Configuración).
* **Corrección de Warning Falso:** Excluido el enlace de LoRa (puenteado) en el cálculo global del estado general del header, solucionando el falso aviso cuando el móvil está conectado correctamente.

## 7. Próximos Pasos: Arquitectura de Streaming Multi-Cámara y VDO.ninja
* **Automatización de VDO.ninja en el Despegue:** Configurada la activación automática del streaming al pasar a la Fase 1 (Ignición) mediante intents de Chrome.
* **Optimización de Parámetros de Cámara:** Implementados parámetros de URL (`&webcam`, `&facing=back`, `&autostart`, `&noaudio`, `&videobitrate=1000`, `&quality=2`, `&nopreview` y `&clean`) para forzar la cámara trasera, omitir los diálogos de selección de pantalla y la sala de preparación previa.
* **Planificación Multi-Cámara para Twitch:** Diseñada la estructura para integrar múltiples cámaras (Sonda, Tierra, Dron) usando VDO.ninja como fuentes del navegador en OBS Studio.
* **Migración y Autohospedaje (N100):** Planificada la sustitución de MediaMTX por una instancia dockerizada de VDO.ninja (servidor web + servidor WSS de señalización) en el servidor N100 para dar soporte P2P cifrado local e independiente.

## 8. Redefinición de Secuencia de Despegue, Redes del Móvil y Proxies Seguros (07/07/2026)
* **Secuencia de 3 Botones:** Redefinido el panel "Misión preparada" en el Dashboard para secuenciar el despegue en tres pasos lógicos: *Listo para el despegue*, *Iniciar cuenta atrás* y *Abortar lanzamiento*.
* **Control de Redes en el Móvil:** Implementado el apagado automático de Wi-Fi en el móvil al armar la sonda (forzando la conexión a datos móviles 4G/5G) y la reactivación automática de Wi-Fi al abortar la secuencia para facilitar pruebas sucesivas en rampa.
* **Congelación de Controles pre-vuelo:** Actualizada la lógica de validación de controles para congelar el estado de los botones una vez iniciada la misión (estado diferente de `espera`). Esto evita que los botones se deshabiliten cuando el móvil pierde temporalmente la conexión durante la transición de Wi-Fi a datos 4G.
* **CORS en el Servidor Flask:** Habilitadas cabeceras CORS globales (`Access-Control-Allow-Origin: *`) en el backend Flask para evitar que el navegador interno de OBS Studio bloquee las peticiones de telemetría provenientes de un origen local (`file://`).
* **WebSockets Seguros mediante subruta `/mqtt`:** Adaptado el HUD y el Dashboard para enrutar el tráfico WebSockets de Mosquitto a través de la ruta segura `/mqtt` en el puerto de internet estándar (443) con certificados SSL firmados (Let's Encrypt), evitando el bloqueo de contenido mixto de los navegadores.
* **Estado Actual (Pendiente):** Nginx Proxy Manager responde con `502 Bad Gateway` al intentar enrutar la localización `/mqtt` al puerto `9001` de Mosquitto en el N100, a pesar de que el cortafuegos UFW del servidor está desactivado y el puerto responde localmente. Queda pendiente investigar la causa de este enrutamiento interno de red.

## 9. Modularización, Volúmenes en Desarrollo y Vuelo Autónomo Inteligente (08/07/2026)
* **Modularización del Dashboard:** Dividido el monolito de `control.js` en 7 submódulos especializados (`state.js`, `ui.js`, `map.js`, `telemetry.js`, `checklist.js`, `launch.js` y `main.js`) en la carpeta `static/js/`, mejorando el mantenimiento y la escalabilidad.
* **Enlace del Menú Lateral:** Conectados los botones de *Cámara* y *Dashboard* en el menú lateral para permitir una navegación fluida entre la consola de control y la galería de capturas.
* **Volúmenes en Caliente (Docker):** Configurado un montaje de volumen de tipo *bind mount* (`./image-store:/app`) en el `docker-compose.yml` para evitar tener que reconstruir la imagen de Docker en cada actualización de archivos de estilo o de interfaz.
* **Control de Giro CSS:** Corregido el giro de la cámara de vuelo a `-90deg` y adaptado con `scale(2)` y `object-fit: cover` para visualizarla en horizontal de forma nítida y a pantalla completa.
* **Reconexión Automática de Vídeo (Fases 0/1):** Implementado un control de estado (`VIDEO_FLAG`) en el móvil para reanudar de forma automática la transmisión de VDO.ninja tras pausarla momentáneamente para tomar fotos en rampa y ascenso.
* **Bucle de Vuelo Inteligente (Fase 2):** Rediseñado el bucle autónomo para optimizar batería y recursos en la estratosfera:
  * Chequeo de cobertura continuo cada 5 segundos (vía `nc` a puerto de MQTT).
  * Apagado automático de Chrome y del streaming al perder cobertura, y encendido automático en el descenso al recuperar señal.
  * Envío de telemetría de alta velocidad (cada 5s) si hay señal.
  * Disparo de fotos de alta resolución (cada 60s) con guardado local en el móvil con marcas de tiempo (`sonda_TIMESTAMP.jpg`).
---

## 10. Robustecimiento de TX/RX LoRa, Subruteo NPM y Aprovisionamiento TIG (20/07/2026)

### 🛰️ Emisor LoRa (`codigo/TXLora/`)
* **Perfil Estratosférico `Airborne < 1G` (`gps_ublox`):**
  * Diseñada la estructura empaquetada `UbxCfgNav5` de **36 bytes exactos** alineada con la especificación oficial de u-blox NEO-6.
  * Aplicada la máscara `0x0001` para actualizar exclusivamente `dynModel = 6` (Airborne < 1G, que permite medir hasta 50 km de altitud) sin alterar otros parámetros del módulo.
  * Optimizado el flujo de la UART a 9600 baudios filtrando tramas NMEA secundarias (`GLL`, `GSA`, `GSV`, `VTG`) y elevando la tasa de refresco a 5Hz.
* **Watchdog de Doble Canal:**
  * **Canal NMEA:** Detección de silencio en la UART (>6s) para re-ejecutar el ciclo de calibración ante fallos de conexión.
  * **Canal Airborne:** Muestra periódica (*poll* cada 60s) para confirmar activamente que el módulo u-blox conserva el perfil *Airborne* y no se ha reiniciado al modo *Pedestrian* de fábrica debido a bajadas puntuales de tensión (*brownout*).
* **Panel de Pruebas Web:** Servidor web integrado en `TXLora.ino` aislado mediante la directiva `#define ENABLE_WIFI_DEBUG_SERVER 1` para pruebas en banco de tierra (panel HTML de auto-refresco y endpoint `/data` en JSON).

### 📡 Receptor LoRa (`codigo/RXLora/`)
* **Compatibilidad de Protocolo:** Confirmado el parseo 1:1 de la trama delimitada (`lat,lng;date;time;altitude;course;speed`).
* **Conexión WiFi No Bloqueante:** Modificada la inicialización en `setup()` para incluir un timeout de 15 segundos y activar la auto-reconexión en segundo plano (`WiFi.setAutoReconnect(true)`). Esto garantiza que el receptor siga recibiendo y procesando paquetes LoRa locales aunque la red WiFi no esté disponible al encenderlo.
* **Actualización de Credenciales:** Actualizado `secrets.h` para dirigir las publicaciones MQTT a `stratocaster.martivich.es` en el puerto `1883`.

### 🌐 Infraestructura Web, Proxy y Aprovisionamiento TIG (`docker-TIG/`)
* **Unificación de Dominio (`stratocaster.martivich.es`):**
  * Configurado Nginx Proxy Manager (NPM) para dar servicio a toda la infraestructura bajo un solo dominio:
    * `/` → Dashboard Flask (`:5000`)
    * `/grafana/` → Cuadro de mando de Grafana (`:3000`)
    * `/mqtt` → Mosquitto WebSockets (`:9001`) con cabeceras `Upgrade` y `proxy_read_timeout 86400s`.
  * Adaptado `docker-compose.yml` de `docker-TIG` con las variables de entorno `GF_SERVER_ROOT_URL`, `GF_SERVER_SERVE_FROM_SUB_PATH=true` y `GF_SECURITY_ALLOW_EMBEDDING=true`.
* **Aprovisionamiento Automático de Grafana:**
  * **Corrección de UIDs:** Corregidos los UIDs de datasources hardcodeados (`afngbg7x6dq80a` → `influxdb_ds`) en el JSON exportado del cuadro de mando (`Sonda LORA`).
  * **Configuración automática:** Creadas las carpetas de aprovisionamiento `docker-TIG/grafana/provisioning/datasources/influxdb.yml` y `docker-TIG/grafana/provisioning/dashboards/` para que Grafana arranque en el servidor con el datasource InfluxDB y el dashboard **Sonda LORA** pre-cargados automáticamente.
  * **Ajuste en `.gitignore`:** Actualizada la exclusión de `.gitignore` (`docker-TIG/grafana/*` y `!docker-TIG/grafana/provisioning/`) para que Git rastree la configuración de aprovisionamiento manteniendo aislada la persistencia.
* **Despliegue y Resolución de Permisos en Servidor (`ubntsrv04TIG`):**
  * Regenerados certificados SSL para Mosquitto (`openssl`).
  * Corregida la propiedad del directorio SQLite de Grafana (`sudo chown -R 472:472 docker-TIG/grafana` / `chmod -R 777`).
  * Desplegada y verificada la pila en el servidor en producción.

---

**Fecha:** 2026-07-21  
**Sesión:** Sincronización del tiempo de misión, priorización de telemetría LoRa, detección dinámica de enlaces en rampa y rediseño de alertas del HUD de OBS.

## 1. Sincronización Temporal del Lanzamiento
* **Cronómetro Unificado (`app.py`):** Corregido el desfase de tiempo de misión entre el Dashboard y el HUD de OBS. Ahora, el tiempo de misión (`timestamp_mision`) se mantiene a cero en el estado `armando` (Listo para el despegue) y se inicializa de forma sincronizada en el momento exacto en que el operador inicia la cuenta atrás de 10 segundos (`action = ok`).

## 2. Redundancia Aeroespacial y Failover de Telemetría (LoRa Prioritario)
* **HUD de OBS (`telemetria.html`):**
  * Modificada la lógica de ingesta de datos para dar **prioridad absoluta a la radio LoRa (868MHz)** para la altitud, velocidad, rumbo y curva de trayectoria. El GPS del móvil actúa como respaldo inicial en rampa, pero una vez que LoRa transmite su primer paquete, el HUD se alimenta 100% de la radio debido a su mayor precisión configurada para cotas estratosféricas (`dynModel = 6` en el u-blox).
  * Implementado un parseo seguro anti-NaN unificando el campo de altitud (`alt` y `altitude`) y barriendo valores indeterminados a `0` para que no rompan las fórmulas barométricas teóricas de presión.
* **Dashboard de Control (`telemetry.js`):**
  * Sincronizado el volcado dinámico: si el teléfono móvil pierde la cobertura 4G en pleno ascenso, los paneles principales de posición (Lat/Lng), altitud, velocidad y rumbo pasan a actualizarse inmediatamente usando los datos de radio LoRa para que el operador no pierda la visibilidad del vuelo.

## 3. Detección Dinámica de Enlaces y Watchdogs Inteligentes
* **Checklist en Rampa (`control.html`, `ui.js`, `state.js`, `checklist.js`):**
  * Cambiado el check de LoRa para que no esté forzado en verde como "Omitido". Ahora inicia en rojo (`Sin Enlace`).
  * En cuanto se recibe la primera publicación de `RXLora` en MQTT (`gps/data` sin la marca de precisión de Android), el checklist cambia dinámicamente a verde (`En Línea (868MHz)`).
  * Ajustado el Watchdog del receptor LoRa a **120 segundos (2 minutos)** para soportar la cadencia espaciada de transmisión por radio sin que la luz del enlace parpadee falsamente a rojo.
  * Ajustado el Watchdog del teléfono a **35 segundos en vuelo** para dar margen al cambio de Wi-Fi a datos móviles 4G sin marcar falsas pérdidas de cobertura.
  * Añadidos registros en la consola de eventos al perder y recuperar la conexión móvil.

## 4. Rediseño del HUD (Evitar Solapamientos y Alertas Independientes)
* **Ajuste de Caja de IA (`telemetria.html`):** Eliminada la caja flotante de descripción de IA del HUD de OBS para limpiar la visual de la emisión en Twitch (estos mensajes se siguen visualizando únicamente en la web de control).
* **Indicadores Flotantes Independientes (`telemetria.html`):**
  * Creada una nueva caja con estilo *glassmorphism* flotando a `top: -55px` (sobre el velocímetro) para evitar solapamientos.
  * Muestra dos luces de estado desacopladas:
    1. **Vídeo Móvil 4G:** Alterna entre `VÍDEO ONLINE MÓVIL 4G` (verde) y `VÍDEO OFFLINE MÓVIL 4G` (rojo si el script suspende Chrome por falta de cobertura).
    2. **Telemetría:** Alterna entre `TELEMETRÍA MÓVIL (4G)`, `TELEMETRÍA LORA (868MHz)` y `TELEMETRÍA OFFLINE` según la actividad de los canales.
* **Sonda Móvil (`sonda_loop.sh`):** Corregida la periodicidad de telemetría en Fase 1 (Ignición) para enviar paquetes de presencia a Mosquitto de forma ininterrumpida cada 5 segundos y evitar que el Dashboard o el HUD lo declaren fuera de línea.

