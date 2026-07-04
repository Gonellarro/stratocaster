# Ecosistema IoT de Telemetría GPS (TIG 2.0)

Este repositorio contiene la infraestructura contenerizada, los firmwares para placas basadas en ESP32 y las especificaciones de diseño del cuadro de mando para desplegar un sistema autónomo de ingesta, almacenamiento y visualización de telemetría GPS en tiempo real.

El sistema está diseñado para operar con dos vectores de entrada simultáneos:

1. **Red de Radio de Largo Alcance (LoRa):** A través de nodos transceptores de hardware dedicados.
2. **Dispositivos Móviles Remotos:** Mediante clientes de telemetría que publiquen de forma inalámbrica a través del protocolo MQTT.

---

## 1. Arquitectura del Sistema

El flujo y procesamiento de los datos sigue un recorrido lineal unificado:

* **Emisión (Radio):** El nodo `TXLora` adquiere las coordenadas desde el módulo GPS por hardware, empaqueta las métricas crudas en una cadena delimitada y las radia usando modulación LoRa a 868 MHz.
* **Pasarela (Gateway):** El nodo `RXLora` captura los paquetes de radio, los convierte a formato JSON estructurado y los publica vía TCP en el bróker local. Adicionalmente, levanta un servidor HTTP asíncrono para diagnosis local en red.
* **Ingesta y Almacenamiento:** El bróker Eclipse Mosquitto valida las credenciales perimetrales y distribuye los mensajes a Telegraf, el cual normaliza las cadenas y las inyecta en InfluxDB v2.
* **Visualización:** Grafana explota los datos temporales almacenados utilizando el lenguaje nativo Flux para representar rutas geográficas y analíticas de movimiento.

![arquitectura](imagenes/arquitectura.png)

---

## 2. Estructura del Proyecto

Al clonar este repositorio, la disposición de los archivos y los volúmenes de persistencia local en el servidor se estructuran de la siguiente forma:

```text
~/docker/TIG2.0/
├── docker-compose.yml       # Orquestación de los servicios (InfluxDB, Mosquitto, Telegraf, Grafana)
├── .env                     # Archivo de variables de entorno y credenciales (Crear a partir de .env.example)
├── telegraf/
│   └── telegraf.conf        # Configuración del agente de ingesta y traductor de formato JSON
├── mosquitto/
│   ├── config/              # Archivo de configuración mosquitto.conf y password_file
│   ├── certs/               # Certificados SSL/TLS para conexiones seguras
│   ├── data/                # Persistencia de mensajes persistentes de Mosquitto
│   └── log/                 # Registros de eventos del bróker
├── influxdb/                # Base de datos de series temporales (Motor de almacenamiento)
└── grafana/                 # Datos, usuarios y paneles del cuadro de mando web

```

---

## 3. Despliegue de la Infraestructura

### 3.1. Preparación del Entorno y Seguridad

Antes de levantar la pila de contenedores por primera vez, es obligatorio configurar el archivo de contraseñas de Mosquitto y asegurar que los permisos a nivel de sistema operativo sean correctos para evitar bloqueos del demonio:

```bash
# 1. Crear el archivo de contraseñas vacío si no existe
sudo touch ./mosquitto/config/password_file

# 2. Asignar la propiedad al usuario interno de Mosquitto (ID 1883) y restringir lectura
sudo chown 1883:1883 ./mosquitto/config/password_file
sudo chmod 0600 ./mosquitto/config/password_file

```

### 3.2. Configuración de Credenciales MQTT

Para añadir el usuario perimetral de ingesta (`admin`), utiliza la herramienta nativa del bróker ejecutando el comando directamente dentro del volumen compartido:

```bash
docker run --rm -v $(pwd)/mosquitto/config:/mosquitto/config eclipse-mosquitto:2.1.2 mosquitto_passwd -b /mosquitto/config/password_file admin contraseñaseguramosquito

```

*(Nota: Este comando generará el hash criptográfico correspondiente dentro del archivo `password_file` sin comprometer sus permisos estrictos).*

### 3.3. Inicialización de los Servicios

1. Copia el archivo de plantilla `.env.example` como `.env` y edita las contraseñas base del ecosistema.
2. Levanta toda la pila en segundo plano mediante Docker Compose:

```bash
# Desplegar contenedores
docker compose up -d

# Verificar que el bróker acepta conexiones sin errores de autenticación
docker compose logs -f mosquitto

```

---

## 4. Guía de Configuración de Hardware (ESP32)

Los firmwares incluidos en la carpeta `firmware/` están optimizados para placas **LilyGO T-Beam v1.x** (ESP32 con chip LoRa a 868 MHz y módulo GPS integrado).

### 4.1. Configuración del Arduino IDE

1. Añade la URL oficial de tarjetas ESP32 en las preferencias del IDE:
`https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
2. Desde el Gestor de Tarjetas, instala el paquete `esp32` de Espressif Systems y selecciona el modelo **T-Beam** (o *ESP32 Dev Module*).
3. Instala las siguientes librerías desde el Gestor:
* **`LoRa`** (por Sandeep Mistry)
* **`PubSubClient`** (por Nick O'Leary)
* **`TinyGPS++`** (por Mikal Hart)
* **`ESPAsyncWebServer`** e **`AsyncTCP`**



### 4.2. Flujo de los Módulos de Hardware

* **`TXLora.ino` (Nodo Móvil):** Inicializa el puerto de comunicación serie por hardware (`HardwareSerial 1`) para decodificar las sentencias NMEA del GPS. Si los datos son válidos, construye una trama con el formato `lat,lng;fecha;hora;altitud;rumbo;velocidad` y la radia por radiofrecuencia a 868 MHz cada 10 segundos.
* **`RXLora.ino` (Gateway Fijo):** Escucha las tramas LoRa entrantes, segmenta los datos y publica un JSON estructurado en el topic `gps/data` del bróker configurado. Dispone de un *Watchdog* de software que reinicia el chip de radio si detecta inactividad prolongada y ofrece un servidor web local en el puerto 80 para consultar el estado del enlace.

---

## 5. Diseño del Cuadro de Mando (Grafana)

Para la correcta visualización de los paneles, Grafana debe conectarse a InfluxDB v2 configurando un *Datasource* de tipo InfluxDB, seleccionando el lenguaje **Flux** y apuntando a la URL interna `http://influxdb:8086`.

### 5.1. Panel de Mapa (Geolocalización)

* **Tipo de Panel:** `Trackmap` o `Geomap`
* **Consulta Flux:**
```flux
from(bucket: "telegraf_db")
  |> range(start: -1h)
  |> filter(fn: (r) => r["topic"] == "gps/data")
  |> filter(fn: (r) => r["_field"] == "lat" or r["_field"] == "lng")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> keep(columns: ["_time", "lat", "lng"])

```



### 5.2. Panel de Altitud Histórica

* **Tipo de Panel:** `Time series`
* **Consulta Flux:**
```flux
from(bucket: "telegraf_db")
  |> range(start: -1h)
  |> filter(fn: (r) => r["topic"] == "gps/data")
  |> filter(fn: (r) => r["_field"] == "altitude")

```



### 5.3. Panel de Velocidad Histórica

* **Tipo de Panel:** `Time series`
* **Consulta Flux:**
```flux
from(bucket: "telegraf_db")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r["topic"] == "gps/data")
  |> filter(fn: (r) => r["_field"] == "speed")

```



### 5.4. Panel de Velocidad Actual

* **Tipo de Panel:** `Gauge`
* **Consulta Flux:**
```flux
from(bucket: "telegraf_db")
  |> range(start: -1h)
  |> filter(fn: (r) => r["topic"] == "gps/data")
  |> filter(fn: (r) => r["_field"] == "speed")
  |> last()

```



### 5.5. Panel de Dirección / Rumbo Actual

* **Tipo de Panel:** `Stat`
* **Consulta Flux:**
```flux
from(bucket: "telegraf_db")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r["topic"] == "gps/data")
  |> filter(fn: (r) => r["_field"] == "course")
  |> last()

```



#### Transformaciones Requeridas en el Panel de Dirección:

Para formatear el valor angular del rumbo antes de mapearlo, añade secuencialmente las siguientes transformaciones de Grafana en la pestaña *Transform*:

1. **Reduce row:** Configura el modo en `Reduce row`, selecciona el cálculo `Last*` y define el alias como `Rumbo_Entero`.
2. **Filter fields by name:** Activa únicamente el campo calculado `Rumbo_Entero` para limpiar el hilo visual.

#### Mapeos de Valores (Value Mappings):

Añade las siguientes reglas de rango para traducir los grados angulares en identificadores cardinales legibles:

* `[0 - 22]` $\rightarrow$ **N**
* `[23 - 67]` $\rightarrow$ **NE**
* `[68 - 112]` $\rightarrow$ **E**
* `[113 - 157]` $\rightarrow$ **SE**
* `[158 - 202]` $\rightarrow$ **S**
* `[203 - 247]` $\rightarrow$ **SW**
* `[248 - 292]` $\rightarrow$ **W**
* `[293 - 337]` $\rightarrow$ **NW**
* `[338 - 360]` $\rightarrow$ **N**