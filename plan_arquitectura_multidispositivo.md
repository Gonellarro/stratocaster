# Plan de Arquitectura IoT Multi-Dispositivo (Sonda Stratocaster)

**Estado:** Implementado (Live)

Este documento detalla la reestructuración del ecosistema de comunicaciones IoT del proyecto. El objetivo es permitir que la sonda albergue **múltiples teléfonos móviles simultáneos** (ej: redundancia, diferentes ángulos de cámara), además de rastreadores LoRa, drones o móviles de asistencia en tierra, evitando colisiones de datos y automatizando su visualización en el stack TIG y el HUD de OBS.

---

## 1. El Problema del Diseño Original
* **Topics Genéricos:** Todos los móviles escribían en los mismos canales (`sonda/status`, `sonda/camera` y `gps/data`). Con dos móviles activos, se producían conflictos de escritura y el Dashboard mostraba datos alternos de forma caótica.
* **Comandos Masivos:** Las órdenes enviadas al canal común `sonda/comando` (como capturar foto) se ejecutaban en todos los móviles conectados a la vez.
* **Rigidez en Grafana:** Añadir nuevos dispositivos requería duplicar consultas e interfaces de forma manual.

---

## 2. Nueva Estructura de Canales (Jerarquía IoT)

Para direccionar de forma única la información, se implementa el patrón de direccionamiento:
$$\text{sonda} \,/\, \text{subsistema} \,/\, \text{device\_id} \,/\, \text{tipo\_datos}$$

### Comparativa de Canales:

| Canal Antiguo | Nuevo Canal Propuesto | Propósito |
| :--- | :--- | :--- |
| `sonda/status` | `sonda/mobile/<device_id>/status` | Diagnóstico de batería, temperatura y red celular del móvil |
| `gps/data` (móvil) | `sonda/mobile/<device_id>/telemetry` | Coordenadas GPS del móvil (en vuelo o respaldo) |
| `sonda/camera` | `sonda/mobile/<device_id>/camera` | Enlace de foto subida con descripción y coordenadas |
| `sonda/comando` | `sonda/mobile/<device_id>/command` | Canal exclusivo de entrada para comandos a ese móvil |
| `gps/data` (LoRa) | `sonda/lora/<device_id>/telemetry` | Coordenadas, altitud y velocidad recibidas por radio LoRa |
| `sonda/meshtastic` | `sonda/mesh/<node_id>/telemetry` | Datos de cobertura y posición de la red mallada |

---

## 3. Modelo de Datos Estandarizado (JSON Único)

Cualquier dispositivo que envíe telemetría por MQTT (`telemetry`) utilizará las mismas claves de JSON:

```json
{
  "timestamp": 1784567754.7,
  "lat": 41.12345,
  "lng": 1.98765,
  "alt": 1205.4,
  "speed": 12.3,
  "course": 180.0,
  "battery": 87,
  "temp": 24.5,
  "status": "ok"
}
```
*Si un dispositivo no cuenta con algún sensor (ej: la placa LoRa no reporta temperatura del procesador o porcentaje de batería del móvil), simplemente omite esas propiedades, pero los campos comunes siempre se llaman igual.*

---

## 4. Análisis de Impacto en el Ecosistema

### A. Script del Móvil (`sonda_loop.sh`)
* Se añade una variable en `sonda.env`: `DEVICE_ID="movil_sonda_1"`.
* Las llamadas a `mosquitto_pub` concatenan la variable en el topic:
  `mosquitto_pub -t "sonda/mobile/$DEVICE_ID/telemetry" ...`
* El receptor de comandos se suscribe a su canal exclusivo: `sonda/mobile/$DEVICE_ID/command`.

### B. Servidor de Imágenes (Flask `app.py`)
* La ruta `/upload` recibe un parámetro adicional `device_id` en el formulario multipart de subida.
* El archivo `.json` de metadatos de la imagen almacena el origen de la foto, permitiendo segmentar la galería web.

### C. Telegraf (`telegraf.conf`)
* Se sustituyen los topics fijos por comodines:
  `topics = ["sonda/+/+/telemetry", "sonda/+/+/camera", "sonda/+/+/status"]`
* Se activa el parser de topics (`topic_parsing`) para trocear la ruta del topic y guardarla como etiquetas nativas en InfluxDB:
  * El segundo término del topic se convierte en el Tag `subsystem`.
  * El tercer término se convierte en el Tag `device_id`.

### D. Grafana (`Geomap` y Gráficas)
* **Visualización Dinámica:** Las consultas en Grafana se agrupan usando la cláusula `GROUP BY "device_id"`.
* **Crecimiento Automático:** Si se conecta un tercer móvil o una segunda baliza de radio, Grafana la dibujará en el mapa de forma automática con un color diferenciado, sin necesidad de que el operador modifique la interfaz.

### E. HUD de OBS (`telemetria.html`)
* El archivo HTML acepta el parámetro `device_id` en la URL:
  `telemetria.html?device_id=movil_sonda_principal`
* El script de JavaScript se suscribe únicamente a los canales correspondientes a ese dispositivo, permitiendo tener múltiples fuentes en OBS monitoreando cámaras distintas de forma independiente.

---

## 5. Plan de Retorno (Rollback)
Si por cualquier motivo el sistema multi-dispositivo fallara en pruebas de rampa:
1. Volver a las versiones anteriores de `telemetria.html` y del script de Android `sonda_loop.sh`.
2. Revertir el archivo `telegraf.conf` en el servidor y reiniciar el contenedor de Telegraf.
3. El broker Mosquitto seguirá procesando los topics genéricos originales de forma transparente.
