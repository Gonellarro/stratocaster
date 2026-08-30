# 🛰️ Manual de Operaciones: Sonda Meteorológica Stratocaster

Este manual contiene las instrucciones detalladas para preparar, desplegar y operar todo el ecosistema de la sonda meteorológica **Stratocaster**. 

El sistema consta de tres componentes principales:
1. **El Dispositivo Móvil (Sonda):** Ejecuta scripts en Termux para capturar fotos, obtener localización GPS y telemetría, y transmitir vídeo.
2. **El Servidor Terrestre (N100):** Aloja los contenedores de base de datos (InfluxDB), visualización (Grafana), bróker de mensajería (Mosquitto) y servidor de control de misión (Flask `image-store`).
3. **El Puesto del Operador (OBS Studio):** Realiza la maquetación y emisión del vídeo y telemetría (HUD) hacia plataformas de streaming (Twitch/YouTube).

---

## 🏗️ 1. Esquema General del Flujo de Datos

```
┌─────────────────────┐     MQTT (1883)      ┌──────────────────────┐
│  Android Phone      │◄────────────────────► │  Mosquitto Broker    │
│  (Termux)           │  sonda/comando (sub)  │  (Docker - TIG)      │
│  sonda_loop.sh      │  sonda/status (pub)   │  Ports: 1883, 8883,  │
│                     │  sonda/camera (pub)   │         9001 (WS)      │
│                     │  gps/data (pub)       └──────────┬───────────┘
│                     │                                  │
│  Fotos vía HTTPS    │     curl POST /upload  ┌─────────┴──────────┐
│  ──────────────────►├──────────────────────► │  Telegraf           │
│                     │                        │  → InfluxDB         │
│  Vídeo WebRTC       │                        │  → Grafana (:3000)  │
│  ──────────────────►│  (VDO.ninja P2P)       └────────────────────┘
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│  image-store (:5000)│  Flask App
│  /upload            │  - Recepción de imágenes
│  /images/<file>     │  - Galería de fotos /fotos
│  /control           │  - Consola del operador
└─────────────────────┘
```

---

## 🖥️ 2. Servidor Terrestre (N100) — Despliegue de Docker

El servidor central requiere levantar dos pilas de contenedores de Docker. Asegúrate de estar en el directorio del proyecto en la máquina N100.

### Paso 2.1: Levantar la pila de control y fotos (`docker-broadcast`)
Este servicio aloja la consola de control `/control` y el visor de fotografías `/fotos`.

1. Accede al directorio:
   ```bash
   cd ~/docker/stratocaster/docker-broadcast
   ```
2. Levanta los contenedores:
   ```bash
   docker compose up -d --build
   ```
3. Verifica que esté en marcha (puerto HTTP `5000` del host):
   * Consola: `http://<IP_SERVIDOR>:5000/control`
   * Galería: `http://<IP_SERVIDOR>:5000/fotos`

> [!NOTE]
> En producción, un Proxy Inverso (como Nginx Proxy Manager) expone este servicio de forma segura en `https://sondafotos.martivich.es` con certificados SSL forzados.

### Paso 2.2: Levantar la pila de telemetría y MQTT (`docker-TIG`)
Este servicio procesa la telemetría en tiempo real y almacena datos históricos para Grafana.

1. Accede al directorio:
   ```bash
   cd ~/docker/stratocaster/docker-TIG
   ```
2. Levanta los contenedores:
   ```bash
   docker compose up -d
   ```
3. Esto pondrá en marcha los siguientes servicios en segundo plano:
   * **Mosquitto (Broker MQTT):** Puerto `1883` (comunicación directa) y `9001` (comunicación WebSocket para la web).
   * **Telegraf (Puente de datos):** Lee de MQTT y escribe en la base de datos.
   * **InfluxDB (Base de datos):** Puerto `8086`.
   * **Grafana (Visualización):** Puerto `3000` (permite ver mapas de calor y gráficas históricas).

---

## 📱 3. Dispositivo Móvil — Puesta en Marcha (Termux)

El dispositivo móvil que irá a bordo de la sonda física requiere la suite de herramientas de Termux para interactuar con el hardware del terminal (cámara, chip GPS, altavoz y batería).

### Requisitos previos en el teléfono
El script requiere permisos de ejecución en Termux de las siguientes herramientas de hardware:
- `termux-api` (Debe estar instalado tanto desde la Google Play/F-Droid como dentro de Termux vía `pkg install termux-api`).
- Permiso de localización activa (GPS de alta precisión).
- Permiso de acceso a la cámara y al almacenamiento.
- Asegurar que el teclado virtual no bloquee el sistema (se recomienda desactivar suspensión de pantalla en los ajustes del terminal).

### Paso 3.1: Configuración de Variables (`sonda.env`)
El script de control lee sus credenciales y rutas de un archivo `sonda.env`. Este archivo debe estar al lado de `sonda_loop.sh`:

```env
IMAGE_SERVER_URL="https://stratocaster.martivich.es"
MQTT_HOST="stratocaster.martivich.es"
MQTT_PORT=1883
MQTT_USER="admin"
MQTT_PASS="<TU_CONTRASEÑA_MQTT>"
MQTT_TOPIC="sonda/mobile/movil_sonda_1/camera"
```

### Paso 3.2: Arrancar la Sonda
1. Abre la aplicación **Termux** en el teléfono.
2. Accede al directorio del código de Android:
   ```bash
   cd ~/stratocaster/codigo/Android
   ```
3. Ejecuta el bucle principal de control:
   ```bash
   ./sonda_loop.sh
   ```
4. El teléfono dirá por voz TTS: *"Sonda en línea y lista para la comprobación."* si se ha enlazado correctamente con el servidor MQTT terrestre.
5. El script se queda a la escucha de comandos en el canal `sonda/comando`. El terminal **debe permanecer con la pantalla activa** (el script solicita automáticamente un Wake Lock de Android para evitar que el sistema duerma la CPU).

---

## 📋 4. Protocolo Pre-Vuelo y Validación (Checklist)

Una vez que el servidor terrestre y el móvil están en marcha, el operador realiza los chequeos de rampa desde la consola web:

1. Abre en tu navegador de PC la dirección: **`https://sondafotos.martivich.es/control`**
2. Haz clic en el botón **🤖 PROBAR SISTEMAS** (abajo a la izquierda en el panel "Check de sistemas").
3. El secuenciador automático ejecutará los siguientes tests de forma secuencial:
   * **Móvil (Android):** Verifica el latido del teléfono.
   * **GPS Sonda:** Activa la escucha pasiva del GPS y comprueba que devuelve coordenadas.
   * **Batería:** Revisa que el nivel del terminal supere el 50% de capacidad.
   * **Sensores:** Lee la temperatura interna del terminal.
   * **Altavoz:** Manda un pitido y orden TTS al móvil. Escucharás: *"Sonda en línea..."*.
   * **Cámara (Foto):** Toma una foto con la cámara trasera, la sube al servidor y la muestra en la tarjeta "Cámara de vuelo".
4. El operador debe confirmar manualmente que ha oído la prueba de audio.
5. Pulsa **INICIAR PREVISUALIZACIÓN** y verifica visualmente en OBS que VDO.ninja muestra la cámara trasera actual. Después pulsa **CONFIRMAR VÍDEO EN OBS**.
6. La telemetría LoRa debe haber entregado una muestra nueva durante el autotest. Los módulos no utilizados se muestran como **No requerido**, nunca como aprobados.
7. Solo después de todo lo anterior se habilita **ARMAR SONDA**.

---

## 🚀 5. El Despegue y Control del Vuelo (Fases)

### Secuencia de Lanzamiento (T-10 segundos)
1. Con todos los checks y el vídeo confirmados, pulsa **ARMAR SONDA**.
2. El móvil responde `armed`, reproduce el aviso de armado y queda esperando. Todavía no inicia la Fase 1.
3. Cuando el operador confirma que todo sigue correcto, pulsa **🚀 INICIAR CUENTA ATRÁS**.
4. El servidor inicia el segundero y, al llegar a `00:00:00`, envía la orden `launch` al móvil. El dashboard muestra **Lanzamiento pendiente** hasta tener acuse.
5. El móvil confirma `launched`; entonces el dashboard declara **En vuelo** y activa la **Fase 1: Ignición**.

### Fase 1: Vuelo en Directo (Streaming)
* El terminal móvil abre de forma automática Google Chrome con la emisión configurada de VDO.ninja de la cámara trasera.
* El vídeo se publica bajo el identificador `sonda_stratocaster` y el HUD de OBS engancha la transmisión al instante.
* El móvil envía telemetría de posición cada 5 segundos al canal `gps/data`.
* Esta fase se mantiene activa hasta que se cumpla cualquiera de las siguientes condiciones:
   * **Altitud de Seguridad:** La sonda supera los **1.000 metros** sobre el nivel del mar.
   * **Límite de tiempo (Timeout):** Transcurren **10 minutos (600 segundos)** de vuelo.
* Al saltar cualquiera de los dos gatillos, el móvil cierra la transmisión de vídeo para conservar batería y ancho de banda, dando paso a la siguiente fase.

### Fase 2: Captura Autónoma y Recuperación
* El móvil entra en un bucle infinito cada 10 segundos:
  1. Toma una foto con la cámara trasera de forma silenciosa.
  2. Lee la posición del módulo de GPS en segundo plano.
  3. Sube la foto mediante HTTPS a `https://sondafotos.martivich.es/upload`.
  4. Envía un paquete JSON por MQTT en `sonda/camera` con las coordenadas, altitud y la URL de la imagen.
* Si el teléfono pierde cobertura 4G temporalmente durante el ascenso, el script almacena la telemetría en el log local `sonda_offline.log` para no perder el registro de la misión.
* La galería de imágenes de la web (`/fotos`) se actualizará automáticamente con las últimas fotografías y vistas espaciales enviadas desde la estratosfera.
* Si el móvil detecta que ha descendido y permanece varios minutos estable con velocidad baja, entra en estado `landed` y reproduce en ciclos `~/sonidos/alarma_recuperacion.mp3`. Esta detección es local y funciona sin cobertura.
* Con cobertura, el operador puede solicitar la alarma de recuperación, `message_1` o detener el audio. Solo se permiten archivos preinstalados.

### Recuperación y cierre de misión
1. Durante el vuelo, pulsa **SOLICITAR RECUPERACIÓN**. El panel mostrará **RECUP. PENDIENTE** hasta que el móvil confirme la orden.
2. Si no hay cobertura, el móvil no puede confirmar ni recibir órdenes MQTT. El operador puede pulsar **FORZAR RECUPERACIÓN**: cambia la fase de la consola, pero queda registrado explícitamente que no existe confirmación del móvil.
3. Cuando la recuperación esté confirmada o haya sido forzada, pulsa **CERRAR MISIÓN**. Después se habilita **NUEVA MISIÓN**. El cierre no borra fotos ni telemetría ya almacenadas.

### Abortar Lanzamiento
Si durante la cuenta atrás de 10 segundos el operador detecta anomalías en rampa, puede pulsar el botón **🚨 ABORTAR LANZAMIENTO** (situado justo debajo del temporizador).
* La interfaz muestra **ABORTO PENDIENTE** hasta que el móvil confirme la orden.
* Solo tras el acuse del móvil se restablece la **Fase 0 (Espera)** y se resetea el checklist.
* Si el móvil no tiene cobertura, la consola no afirma que el aborto se haya ejecutado.

---

## 🎬 6. Configuración del Directo en OBS Studio (Twitch)

Para emitir la misión en directo combinando el vídeo y la telemetría del proyecto:

### 1. El vídeo de la cámara (VDO.ninja)
* En OBS, añade una fuente de tipo **Navegador (Browser)**.
* URL de la fuente:
  ```text
  https://vdo.ninja/?view=sonda_stratocaster&autoplay&mute
  ```
* Dimensiones recomendadas: `640 x 480` (o `1280 x 720` si hay buena cobertura).

### 2. El HUD de Telemetría (Superposición gráfica)
El HUD se encuentra en el archivo local: `/home/marti/Documentos/Personal/Sonda/codigo/HUD/telemetria.html`.
* En OBS, añade otra fuente de tipo **Navegador (Browser)**.
* Marca la casilla **"Archivo local"** y selecciona la ruta del archivo `telemetria.html`.
* Si deseas que conecte al servidor de internet en lugar de usar fallbacks de red local, añade el parámetro del servidor en la URL de OBS. Ejemplo:
  ```text
  file:///home/marti/Documentos/Personal/Sonda/codigo/HUD/telemetria.html?server=sondafotos.martivich.es
  ```
* Dimensiones recomendadas: `1920 x 1080` (pantalla completa, transparente).
* **Comportamiento dinámico:** El HUD mostrará en primera instancia una cuenta atrás gigante en el centro de la pantalla mientras la sonda esté armada. Al llegar a cero, el overlay se desvanece de forma limpia y entra el panel de instrumentos del vuelo con el reloj de tiempo total de misión y los indicadores de altitud, rumbo y velocidad activos.

---

## 🔧 7. Solución de Problemas Comunes (Faq)

#### 🔴 La cámara del móvil emite en negro en la prueba de vídeo o en la Fase 1
* **Causa:** El driver de la cámara del móvil está bloqueado por el proceso de fotos de Termux (`termux-camera-photo`).
* **Solución:** Cierra Chrome en el móvil (deslízalo de las apps abiertas en segundo plano) y ejecuta en la terminal de Termux:
  ```bash
  pkill -9 -f termux-camera
  ```
  Si el driver de Android sigue sin responder, reinicia el teléfono.

#### 🛰️ El checklist de GPS no pasa de "Buscando satélites..."
* **Causa:** El teléfono no tiene suficiente visibilidad del cielo (dentro de un taller o casa) para realizar una triangulación precisa.
* **Solución:** Saca el teléfono al exterior. Si estás haciendo pruebas de escritorio y quieres saltarte el check, el script tiene un fallback de red que lee la última posición aproximada de la antena celular si no logra enganchar señal de satélite tras 15 segundos.

#### ⚠️ La web muestra el mensaje "TELEMETRÍA OFFLINE"
* **Causa:** Pérdida de comunicación con el bróker MQTT del servidor o credenciales incorrectas.
* **Solución:** Revisa que el contenedor de `mosquitto` esté en marcha en el N100 (`docker ps`). Comprueba que el archivo `sonda.env` del móvil tenga la contraseña correcta.
