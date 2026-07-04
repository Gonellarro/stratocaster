Aquí tienes el dossier técnico resumido con la arquitectura que hemos diseñado, estructurado de forma clara y limpia para que puedas importarlo directamente en tu flujo de trabajo o pasárselo a Antigravity:

---

## 🛰️ 1. Origen de las Fuentes de Señal (Captura)

El sistema se compone de múltiples cámaras en movimiento y una gestión inteligente de datos:

* **Móvil de la Sonda Stratosférica (Vídeo/Fotos/Telemetría):**
* **Fase Inicial (Hasta ~1.000m):** Emite vídeo en directo en alta definición usando **Larix Broadcaster** configurado con **Bitrate Adaptativo** y codificación **SRT (Secure Reliable Transport)** para mitigar la pérdida de paquetes por la altitud.
* **Fase Autónoma (Orquestador Termux):** Al alcanzar la altura límite o tiempo programado, un script en Bash en **Termux** detiene el streaming mediante *Intents* de Android. Toma el control de la cámara con `termux-camera-photo` para disparar fotos secuenciales, procesarlas localmente con IA (`llama.cpp` + `Qwen3-VL-2B`) y extraer telemetría con `termux-location` (GPS, altitud, latitud).


* **Envío de Datos:** Los datos de telemetría e imágenes capturadas se envían mediante ráfagas HTTP y MQTT en cuanto el dispositivo dispone de cobertura móvil.




* **Móviles de Apoyo en Tierra (Vídeo):**
* Diferentes smartphones distribuidos en la zona de lanzamiento que emiten vídeo en tiempo real hacia la central utilizando protocolos SRT o RTMP (vía Larix Broadcaster o apps similares).



---

## 🖥️ 2. Infraestructura del Servidor (Backend en N100)

Toda la recepción de datos y distribución multimedia se centraliza en un miniservidor Intel N100 de 16 GB de RAM mediante contenedores Docker:

* **MediaMTX (Servidor Multimedia):** Actúa como el enrutador ciego y ultra-eficiente de vídeo. Escucha en los puertos correspondientes (`8889` para SRT y `1935` para RTMP), unificando y estabilizando todos los flujos entrantes de los móviles (tierra y sonda) sin necesidad de transcodificar ni consumir apenas CPU.
* **Stack TIG (Telegraf + InfluxDB + Grafana):** Se encarga de la monitorización pura. Recibe la telemetría del script de la sonda (y del ESP32 con LoRa) a través del broker MQTT integrado, registrando el histórico de altitud, velocidad y coordenadas para su posterior análisis técnico.

---

## 🎬 3. Orquestación y Realización en Vivo (Frontend de Vídeo)

Para generar la señal final de vídeo inspirada en las retransmisiones de SpaceX (vídeo dinámico con telemetría fija abajo), se utiliza una estación de control en tierra:

* **OBS Studio (Mesa de Mezclas Visual):**
* Se crean escenas independientes para cada flujo de vídeo proveniente de MediaMTX (Cámara Tierra 1, Cámara Tierra 2, Sonda).
* **Automatización de Escenas:** Mediante el plugin *Advanced Scene Switcher*, OBS alterna de forma aleatoria entre las cámaras de tierra cada 15 segundos para dar dinamismo, pero cuenta con una regla de prioridad absoluta: **si MediaMTX vuelve a recibir señal de la sonda, OBS pincha la cámara del cohete inmediatamente**.


* **Incrustación de Telemetría Real-Time (`telemetria.html`):**
* Una interfaz web ligera (HTML/JS) se añade en OBS como **Fuente de Navegador** en capa superior fija con fondo transparente.
* Esta web se conecta por WebSockets al broker MQTT del N100, escucha el topic de la sonda y actualiza al instante los marcadores visuales de altitud, latitud y longitud sobre el vídeo que se esté reproduciendo en el fondo.


* **Resultado:** Mientras las cámaras cambian de forma automática o manual, los datos espaciales y de posición de la sonda permanecen estables abajo en la pantalla, ofreciendo un show televisivo impecable.