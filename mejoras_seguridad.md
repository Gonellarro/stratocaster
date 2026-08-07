# Mejoras de seguridad y control de misión

> **Estado de implementación (06/08/2026):** aplicado el primer bloque de
> control: separación `ARMAR`/`LANZAR`, estado persistente, acuses, comandos
> autenticados desde la API, pre-vuelo explícito, confirmación visual de OBS,
> detección local de aterrizaje y alarma de recuperación. TLS/ACL MQTT, la
> autenticación del upload y la eliminación completa de credenciales del
> navegador siguen siendo trabajo pendiente de infraestructura.

## Alcance

Auditoría estática del repositorio Stratocaster. El objetivo es blindar la
infraestructura, reducir la superficie expuesta y hacer que la consola de
control refleje siempre el estado real de la sonda.

Este documento no sustituye una revisión del servidor desplegado, del proxy
inverso, del cortafuegos ni de los dispositivos físicos. Antes de una misión
real hay que comprobar también esa configuración en producción.

## Resumen ejecutivo

La arquitectura funcional es buena, pero actualmente hay cuatro problemas que
deben tratarse como prioritarios:

1. Existen credenciales y valores secretos en el repositorio o en valores por
   defecto del código. Deben rotarse y retirarse del historial.
2. MQTT se utiliza por una conexión sin TLS para los clientes remotos y la
   consola recibe credenciales MQTT compartidas dentro del navegador.
3. El control de misión no tiene una autoridad única ni una máquina de estados
   validada en servidor.
4. La orden `arm` del móvil termina la Fase 0 e inicia inmediatamente la Fase
   1, aunque la interfaz la presenta como un paso previo a la cuenta atrás.

La cuarta cuestión es tanto de seguridad como de seguridad operacional: la
interfaz puede mostrar “cuenta atrás pendiente” mientras el dispositivo ya ha
comenzado su secuencia de vuelo.

## Hallazgos priorizados

### CRÍTICOS

#### C1. Secretos versionados o predecibles

Se ha detectado un archivo de credenciales no destinado a Git en
`codigo/TXLora/credentials.h`, además de credenciales de respaldo y valores
conocidos en Docker Compose, Flask y archivos `.env.example`.

Impacto:

- acceso a la red Wi‑Fi de depuración del transmisor;
- acceso al broker MQTT;
- falsificación de telemetría o envío de comandos;
- posible acceso a servicios de InfluxDB/Grafana;
- compromiso histórico aunque el archivo se borre en un commit posterior.

Medidas:

- rotar inmediatamente todas las credenciales que hayan estado en el árbol o
  en el historial;
- eliminar los secretos del historial Git con una herramienta de saneamiento;
- añadir `credentials.h` y cualquier variante local a `.gitignore`;
- eliminar valores por defecto operativos (`admin`, claves de ejemplo y
  secretos embebidos);
- hacer que el arranque falle si falta una configuración obligatoria;
- usar un gestor de secretos o archivos montados fuera del repositorio.

#### C2. MQTT remoto sin cifrado efectivo

Mosquitto configura listeners TLS, pero Docker solo publica actualmente los
puertos de MQTT plano y WebSockets. El móvil y el receptor LoRa utilizan el
puerto 1883.

Impacto:

- las credenciales pueden capturarse en tránsito;
- los comandos pueden observarse, modificarse o repetirse;
- la seguridad depende de que la red intermedia sea confiable.

Medidas:

- usar MQTT sobre TLS en 8883 con verificación de certificado;
- no exponer 1883 fuera de la red interna;
- publicar 8883 solo si es estrictamente necesario y limitarlo mediante
  cortafuegos/VPN;
- valorar certificados de cliente por dispositivo para evitar compartir
  contraseñas.

#### C3. Credenciales MQTT compartidas en el navegador

La plantilla de control inyecta usuario y contraseña MQTT en `window.CONFIG`,
y el navegador se conecta directamente al broker. El mismo usuario sirve para
varios componentes.

Impacto:

- las credenciales quedan accesibles para el código JavaScript, extensiones y
  herramientas del navegador;
- un usuario con acceso a la consola puede publicar en topics no relacionados;
- un XSS o una dependencia comprometida obtiene capacidad de control de misión.

Medidas:

- eliminar la conexión directa navegador → MQTT;
- implementar API autenticada servidor → servicio de comandos → MQTT;
- crear usuarios MQTT separados por función y dispositivo;
- definir ACL explícitas para publicación y suscripción;
- limitar cada móvil a sus propios topics `sonda/mobile/<device_id>/...`.

### ALTOS

#### A1. Orden `arm` inicia el vuelo antes de la cuenta atrás

En `sonda_loop.sh`, el comando `arm` crea `ARMED_FLAG`. El bucle de Fase 0
termina al detectar ese archivo y el proceso entra en Fase 1, inicia vídeo y
telemetría. La consola, en cambio, cambia a `armando` y aún muestra el botón
“iniciar cuenta atrás”.

Impacto:

- divergencia entre el estado mostrado y el comportamiento físico;
- una prueba de armado puede iniciar vídeo y la secuencia de vuelo;
- abortos y reintentos difíciles de razonar.

Medidas:

- separar las órdenes `armar` y `lanzar`;
- `armar` debe dejar el móvil en estado `ARMED` sin entrar en Fase 1;
- el servidor debe iniciar la cuenta atrás y enviar `launch` al llegar a cero;
- el móvil debe confirmar cada transición con un `command_id`;
- si no llega confirmación, pasar a estado de fallo seguro.

#### A2. Máquina de estados controlada principalmente por el frontend

El navegador modifica `mission.state` y llama a endpoints que aceptan acciones
sin validar de forma completa la transición anterior. El estado se guarda en
un JSON bajo `/tmp`, no en almacenamiento durable de misión.

Impacto:

- transiciones imposibles o repetidas;
- divergencias con varios workers, reinicios o peticiones duplicadas;
- pérdida del estado al recrear el contenedor;
- imposibilidad de reconstruir con precisión qué ocurrió.

Medidas:

- convertir el backend en autoridad única;
- validar cada transición con estado actual, identidad y `mission_id`;
- persistir misión, eventos y comandos en SQLite/PostgreSQL o almacenamiento
  durable;
- aplicar idempotencia y bloqueo transaccional;
- guardar un registro de auditoría inmutable.

#### A3. Upload público sin límites ni validación suficiente

`/upload` no exige autenticación de dispositivo, no limita tamaño y acepta el
archivo basándose principalmente en la extensión saneada.

Impacto:

- agotamiento de disco y memoria;
- abuso como endpoint de almacenamiento;
- imágenes o contenidos no esperados en la galería;
- falta de trazabilidad del dispositivo emisor.

Medidas:

- exigir token/certificado por dispositivo;
- limitar tamaño, frecuencia y cuota por dispositivo;
- validar MIME y contenido con decodificación real;
- aceptar solo formatos necesarios y normalizar imágenes;
- registrar hash, tamaño, dispositivo y hora;
- almacenar fuera del árbol de aplicación y servir con cabeceras seguras.

#### A4. Acciones de control sin anti-CSRF, rate limiting ni control de intentos

El login no limita intentos. Las acciones REST no tienen token CSRF ni
protección adicional frente a peticiones desde una sesión legítima. El endpoint
`/control_lanzamiento/ok` no exige sesión.

Medidas:

- exigir autenticación también en endpoints de transición y confirmación;
- añadir CSRF para acciones basadas en cookie;
- aplicar rate limiting al login y a las operaciones sensibles;
- registrar IP, usuario, misión, acción y resultado;
- devolver errores de transición claros sin cambiar estado parcialmente.

#### A5. Servicios internos publicados directamente

InfluxDB, Grafana, MQTT, WebSockets, Telegraf y Flask se publican mediante
puertos del host. La exposición final depende de la configuración externa del
proxy y del cortafuegos.

Medidas:

- publicar externamente solo HTTPS del proxy inverso;
- mantener bases de datos, Telegraf y broker en una red Docker privada;
- restringir administración por VPN o red de gestión;
- revisar reglas del cortafuegos desde una lista explícita de puertos.

### MEDIOS

#### M1. CORS demasiado permisivo y basado en coincidencias parciales

La validación comprueba si ciertas cadenas aparecen dentro de `Origin`, lo que
puede aceptar dominios que solo contienen esos textos.

Medidas:

- usar una lista exacta de orígenes permitidos;
- no permitir credenciales CORS salvo que sea imprescindible;
- limitar métodos y cabeceras por endpoint;
- añadir CSP, `X-Content-Type-Options`, `Referrer-Policy` y
  `frame-ancestors` apropiados.

#### M2. Cookies de sesión no endurecidas explícitamente

Flask no configura de forma explícita `Secure`, `HttpOnly` y `SameSite` para la
sesión.

Medidas:

- `SESSION_COOKIE_SECURE=true`;
- `SESSION_COOKIE_HTTPONLY=true`;
- `SESSION_COOKIE_SAMESITE=Lax` o `Strict` según el flujo;
- rotar sesión al iniciar sesión y expirar sesiones inactivas.

#### M3. LoRa sin autenticidad ni anti-replay

Los paquetes LoRa se transmiten como texto delimitado y el receptor los publica
si el formato es válido.

Impacto:

- una transmisión falsa puede alterar posición, altura, rumbo o velocidad en
  el HUD y Grafana;
- un paquete antiguo puede repetirse como si fuese actual.

Medidas:

- añadir versión de protocolo, `device_id`, contador monotónico y timestamp;
- firmar/autenticar el payload con una clave compartida por misión o un
  esquema adecuado al hardware;
- rechazar contadores repetidos, timestamps fuera de ventana y datos
  físicamente imposibles;
- conservar RSSI/SNR y fuente para distinguir datos dudosos.

#### M4. Dependencias externas sin fijación ni integridad

La interfaz carga MQTT.js, Leaflet y fuentes desde CDN. No hay lockfiles ni
pruebas automatizadas visibles en el repositorio.

Medidas:

- fijar versiones exactas;
- usar `integrity`/SRI o servir dependencias locales;
- revisar actualizaciones de forma controlada;
- añadir pruebas de API, transiciones, parsing MQTT y flujo de autotest.

#### M5. Acciones de interfaz que no reflejan capacidades reales

Hay acciones que no tienen un manejador completo en el móvil o que muestran
funcionalidad retirada, como `sirena_on`, la referencia a IA local y algunos
checks de vídeo/LoRa/Meshtastic marcados como válidos sin prueba efectiva.

Medidas:

- retirar botones no implementados;
- diferenciar `OK`, `OMITIDO`, `NO DISPONIBLE`, `ERROR` y `SIN PRUEBA`;
- no permitir que una caché o un mensaje pasivo convierta automáticamente un
  requisito obligatorio en aprobado;
- mostrar evidencia, hora, dispositivo y umbral de cada prueba.

## Modelo de control propuesto

La consola debería trabajar con una máquina de estados validada por servidor:

```text
Preparación
  → Autotest
  → Lista en rampa
  → Armando
  → Armada
  → Cuenta atrás
  → En vuelo
  → Descenso/recuperación

Desde cualquier fase segura:
  → Abortada
  → Fallo seguro
```

Flujo recomendado:

1. El operador inicia un `mission_id` nuevo.
2. El servidor ejecuta el autotest y guarda la evidencia de cada paso.
3. El operador autoriza `ARMAR`.
4. El dispositivo confirma `ARMED`; todavía no se inicia Fase 1.
5. El operador mantiene pulsado o confirma explícitamente el inicio de cuenta
   atrás.
6. El servidor cuenta hasta cero y publica `LAUNCH` con caducidad.
7. El móvil confirma `FLIGHT_PHASE_1` y comienza vídeo/telemetría.
8. Todo comando tiene `command_id`, resultado, timestamp y acuse.
9. La pérdida de comunicación no se interpreta como éxito: provoca estado
   `UNKNOWN` o `FAIL_SAFE` según la fase.

## Rediseño de la consola

### Vista Misión

Una vista guiada con un solo siguiente paso visible:

- estado actual real del servidor;
- estado confirmado de cada dispositivo;
- checklist con evidencias y caducidad;
- bloqueos explicados;
- botón de acción principal contextual;
- abortar siempre visible, pero con confirmación y motivo.

### Vista Vuelo

Una vista principalmente de lectura:

- fuente activa: 4G, LoRa o degradada;
- última posición válida y edad del dato;
- batería, temperatura y cobertura;
- trayectoria y calidad de enlace;
- última foto y estado de almacenamiento;
- línea de eventos de misión.

Las acciones no críticas, simuladas o no implementadas deben desaparecer de
esta vista.

### Acciones críticas

Cada acción peligrosa debe mostrar:

- fase actual;
- efecto esperado;
- dispositivo destino;
- caducidad;
- confirmación del dispositivo;
- resultado o timeout.

## Orden de ejecución recomendado

### Fase 0 — Contención inmediata

- rotar secretos y sanear historial;
- apagar Wi‑Fi de depuración del TX en builds de vuelo;
- cerrar puertos directos al exterior;
- detener el uso de MQTT plano remoto;
- retirar botones/órdenes no implementados.

### Fase 1 — Identidad y transporte

- MQTT TLS/VPN;
- ACL por dispositivo;
- tokens de subida;
- cookies y CSRF;
- rate limiting y cabeceras HTTP.

### Fase 2 — Control fiable

- máquina de estados en backend;
- almacenamiento durable;
- `mission_id`, `command_id` y acuses;
- separación ARMAR/LANZAR;
- auditoría de eventos.

### Fase 3 — Nueva interfaz

- vista Misión guiada;
- vista Vuelo de lectura;
- checks basados en evidencia;
- estados `OK`, `OMITIDO`, `ERROR`, `DESCONOCIDO` y `CADUCADO`;
- pruebas de extremo a extremo en banco.

## Criterios de aceptación antes de vuelo

- Ningún secreto operativo aparece en Git, imágenes Docker o JavaScript.
- Los clientes remotos usan TLS/VPN y credenciales individuales.
- Un usuario no puede publicar comandos fuera de su dispositivo autorizado.
- Reiniciar el servidor no borra la misión ni su auditoría.
- `ARMAR` nunca inicia Fase 1 por sí solo.
- La cuenta atrás solo empieza con dispositivo armado y confirmación válida.
- Un comando duplicado no repite una acción peligrosa.
- La pérdida de MQTT tiene un comportamiento definido y visible.
- `/upload` tiene autenticación, límites y cuota.
- Todas las acciones visibles en la interfaz están implementadas y probadas.
- Existe una prueba de aborto en cada fase y una prueba de recuperación tras
  reinicio del servidor.
