# Instalación de F-Droid en el móvil
1. Descargar el apk desde la página [de F-Droid](https://f-droid.org/F-Droid.apk) o ir a la página [de F-Droid](https://f-droid.org/es/)
2. Ejecutar y permitir la descarga de aplicaciones desde esta fuente.
3. Instalar y abrir.

# Instalación de Termux y Termux API
1. Ir a F-Droid.
2. Buscar (botón de lupa): Termux (lo encontraremos bajando y eligiendo el emulador de terminal y paquetes). Descargar e instalar. Si aparece un mensaje de **Google Play Protect - Aplicación no segura bloqueada**, desplegar y seleccionar **Instalar de todas formas**. **NO PULSAR EN ENTENDIDO**.
3. Permitir las aplicaciones de la fuente de F-Droid.
4. Buscar (botón de lupa): Termux API. Descargar e instalar.

# Instalar dependencias
- Instalar mosquitto, jq, curl y openssl. Escribir en la terminal: `pkg install -y jq curl mosquitto openssl`

# Permisos especiales
- Otorgar el permiso especial "Mostrar sobre otras aplicaciones" (Draw over other apps). Es muy importante conceder este permiso tanto a Termux como a Termux:API en los ajustes de Android.

# Comprobar que funciona Termux y Termux API
- Abrir Termux.
- Instalar Termux-API en la terminal: `pkg install termux-api`
- Instalar OpenSSH: `pkg install openssh`
- Cambiar la contraseña: escribir `passwd` y repetirla.
- Averiguar el nombre de usuario de Termux: escribir `whoami` (guarda este nombre).
- Habilitar el acceso al almacenamiento compartido del teléfono: escribir `termux-setup-storage`
	- Aceptar el diálogo de permisos que aparecerá en pantalla.
- Probar el GPS ejecutando: `termux-location -p gps`
 
El resultado debe tener un formato similar a este:

```json
{
  "latitude": 39.55157048,
  "longitude": 2.59788352,
  "altitude": 124.7523193359375,
  "accuracy": 30.53166389465332,
  "vertical_accuracy": 384.0,
  "bearing": 245.39999389648438,
  "speed": 0.5,
  "elapsedMs": 50,
  "provider": "gps"
}
```

- Probar la cámara tomando una foto de prueba: `termux-camera-photo -c 0 foto.jpg`
	- Conceder permisos de cámara si lo solicita.
	- Mover la foto a la carpeta de imágenes públicas para verificarla: `mv foto.jpg ~/storage/shared/Pictures/`
	- Confirmar que la foto aparece en la galería del teléfono.
- Probar la síntesis de voz (TTS): `termux-tts-speak "Iniciando búsqueda de satélites GPS."`

---

# Copiar el programa de la sonda al móvil

Hay dos maneras fáciles de copiar el script `sonda_loop.sh` y el archivo de configuración `sonda.env` desde un ordenador Windows al móvil:

### Opción A: Sin cables (Mediante SSH / SFTP) — Recomendado
Este método utiliza el servidor OpenSSH que hemos instalado en Termux.

1. **Preparar el móvil (Termux):**
   * Asegúrate de que el móvil y el ordenador de Windows estén conectados a la **misma red Wi-Fi**.
   * Inicia el servidor SSH en Termux escribiendo:
     ```bash
     sshd
     ```
   * Averigua la IP local del móvil ejecutando en Termux:
     ```bash
     termux-wifi-connectioninfo
     ```
     o bien:
     ```bash
     ifconfig
     ```
     *(Apunta la IP local, por ejemplo: `192.168.1.150`)*.
   * Averigua tu nombre de usuario en Termux ejecutando:
     ```bash
     whoami
     ```
     *(Apunta el usuario, por ejemplo: `u0_a245`)*.

2. **Copiar desde Windows:**
   * **Método 1: Desde la consola de Windows (Cmd o PowerShell)**
     Abre la consola de Windows en la carpeta donde tienes el archivo `sonda_loop.sh` y ejecuta:
     ```cmd
     scp -P 8022 sonda_loop.sh usuario_termux@IP_DEL_MOBIL:~
     ```
     *(Ejemplo real: `scp -P 8022 sonda_loop.sh u0_a245@192.168.1.150:~`)*.
     Escribe la contraseña de Termux (la que has definido con `passwd`) cuando te la pida.
   
   * **Método 2: Mediante un cliente gráfico (WinSCP o FileZilla)**
     * Descarga y abre [WinSCP](https://winscp.net/) en Windows.
     * Crea una nueva conexión con los siguientes datos:
       * **Protocolo de transferencia:** SFTP
       * **Nombre del servidor (Host name):** La IP del móvil (`192.168.1.150`)
       * **Número de puerto:** `8022`
       * **Nombre de usuario:** El obtenido con `whoami` (`u0_a245`)
       * **Contraseña:** La contraseña que definiste en Termux
     * Conéctate y arrastra los archivos (`sonda_loop.sh` y `sonda.env`) de la carpeta de Windows al directorio home del móvil (a la derecha).

---

### Opción B: Con cable USB (Método clásico MTP)
Si no dispones de Wi-Fi o prefieres hacerlo por cable:

1. Conecta el móvil al ordenador con el cable USB.
2. En el móvil, selecciona el modo de conexión **"Transferencia de archivos" (MTP)** en las notificaciones del sistema.
3. Desde Windows, abre el Explorador de archivos, busca el dispositivo móvil y copia los archivos `sonda_loop.sh` y `sonda.env` a la carpeta **Descargas** (o *Download*) del almacenamiento interno del teléfono.
4. Abre Termux en el móvil y mueve los archivos a tu carpeta de inicio ejecutando:
   ```bash
   cp ~/storage/shared/Download/sonda_loop.sh ~
   cp ~/storage/shared/Download/sonda.env ~
   ```

---

# Ejecución y permisos
Una vez tengas el script en la carpeta home de Termux, haz lo siguiente para poder ejecutarlo:

1. **Dar permisos de ejecución:**
   ```bash
   chmod +x ~/sonda_loop.sh
   ```
2. **Arrancar el programa:**
   ```bash
   ./sonda_loop.sh
   ```
