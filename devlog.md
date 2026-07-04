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

### 🐳 Infraestructura Servidor (`docker/`)
* **Servidor de Imágenes (`docker/image-store/`):**
  * Creado un microservicio ligero en Python usando **Flask** (`app.py` y `Dockerfile`).
  * Genera un UUID único para cada foto subida para prevenir colisiones de nombres.
  * Almacena las fotos en un volumen físico persistente `./images` expuesto en el puerto `5000` (diseñado para rutarse de forma segura mediante HTTPS en Nginx Proxy Manager).
  * **Miniweb de Galería (`/fotos`):** Creada una interfaz web integrada en el puerto `5000/fotos`. Genera una vista de galería en modo oscuro fluido y moderno (fuente Google Outfit, bordes difuminados, sombras de neón). Incluye un visor a pantalla completa (*lightbox*) para ampliar las imágenes con su descripción al hacer clic sobre ellas.
  * **Asociación de metadatos:** Guarda un archivo `.json` de metadatos al lado de cada foto para registrar la descripción de la IA y la marca de tiempo de subida en tiempo real.
* **[docker-compose.yml](file:///home/marti/Documentos/Personal/Sonda/docker/docker-compose.yml):**
  * Integrado el nuevo servicio `image-store` en la pila de contenedores.
* **[telegraf.conf](file:///home/marti/Documentos/Personal/Sonda/docker/telegraf/telegraf.conf):**
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
1. Transferir la carpeta `image-store/` al servidor.
2. Añadir el bloque del servicio `image-store` a tu `docker-compose.yml` real.
3. Copiar el archivo `telegraf.conf` actualizado al servidor y reiniciar Telegraf (`docker compose restart telegraf`).
4. Levantar la pila actual (`docker compose up -d --build`).
5. En **Nginx Proxy Manager**, añadir el Proxy Host para redirigir tu subdominio `sondafotos.martivich.es` al contenedor `image-store` en el puerto `5000` con SSL forzado.
   * **Tip para la Miniweb:** El endpoint de la galería estará disponible públicamente también bajo `https://sondafotos.martivich.es/fotos`.
6. En el teléfono móvil, crear el archivo `sonda.env` a partir del de ejemplo y rellenar las contraseñas.
7. Importar el archivo JSON final en Grafana.

