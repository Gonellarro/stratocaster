# Instal·lació d'F-Droid al mòbil
1. Descarregar l'apk de la pàgina [d'Fdroid](https://f-droid.org/F-Droid.apk) o anar al pàgina [d'Fdroid](https://f-droid.org/es/)
2. Executar i permetre descarregar les aplicacions d'aquesta font
3. Instal·lar i obrir

# Instal·lació de Termux i Termux API
1. Anar a F-Droid
2. Cerca (Botó de lupa): Termux (El trobarem baixant i escollint l'emulador de terminal i paquets). Descarregar. Instal·lar. Si surt un missatge de **Google Play Protect - Aplicación no segura bloqueada**, desplegar i trobareu **Instalar de todas formas**. **NO PICAR DAUMNT ENTENDIDO**
3. Permetre les aplicacions de la font de F-Droid
4. Cerca (Botó de lupa): Termux API. Descarregar. Instal·lar.

# Instal·lar dependències
- Instal·lar mosquitto, jq i curl. Escriure: `pkg install -y jq curl mosquitto openssl`

# Permisos especials

- Permís especial "Mostrar sobre altres aplicacions" (Draw over other apps). És molt important atorgar aquest permís tant a Termux com a Termux:API.

# Comprovar que funciona Termux i Termux API
- Obrir Termux
- Instal·lar Termux-API: Escriure `pkg install termux-api`
- Instal·lar OpenSSH. Escirure: `pkg install openssh`
- Canviar la contrasenya. Escriure: `passwd` i repetirla
- Esbrinar l'usuari. Escriure: `whoami`
- Habilitar l'espai per compartir dades. Escriure `termux-setup-storage`
	- Repetir el procés fins que tengui permisos
- Provar el GPS. Escriure `termux-location -p gps`
 
El resultat ha de donar:

```bash
~ $ termux-location -p gps
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

- Provar les fotos. Escriure `termux-camera-photo -c 0 foto.jpg`
	- Repetir el procés fins tengui permisos
	- Moure la foto a la carpeta d'imatges: `mv foto.jpg ~/storage/shared/Pictures/`
	- Confirmar que hi ha la foto a la carpeta Imatges
- Provar el TTS. Escriure `termux-tts-speak "Iniciando búsqueda de satélites GPS."`
 

# Copiar el programa de la sonda al mòbil

Hi ha dues maneres fàcils de copiar el script `sonda_loop.sh` i el fitxer de configuració `sonda.env` des de Windows al mòbil:

### Opció A: Sense cables (Mitjançant SSH / SFTP) — Recomanat
Aquest mètode utilitza el servidor OpenSSH que hem instal·lat a Termux.

1. **Preparar el mòbil (Termux):**
   * Assegura't que el mòbil i l'ordinador Windows estan connectats a la **mateixa xarxa Wi-Fi**.
   * Inicia el servidor SSH a Termux escrivint:
     ```bash
     sshd
     ```
   * Esbrina la IP local del mòbil executant a Termux:
     ```bash
     termux-wifi-connectioninfo
     ```
     o bé:
     ```bash
     ifconfig
     ```
     *(Apunta la IP local, per exemple: `192.168.1.150`)*.
   * Esbrina el teu nom d'usuari a Termux executant:
     ```bash
     whoami
     ```
     *(Apunta l'usuari, per exemple: `u0_a245`)*.

2. **Copiar des de Windows:**
   * **Mètode 1: Des de la consola de Windows (Cmd o PowerShell)**
     Obre la consola de Windows a la carpeta on tens el fitxer `sonda_loop.sh` i executa:
     ```cmd
     scp -P 8022 sonda_loop.sh usuari_termux@IP_DEL_MOBIL:~
     ```
     *(Exemple real: `scp -P 8022 sonda_loop.sh u0_a245@192.168.1.150:~`)*.
     Escriu la contrasenya del Termux (la que has definit amb `passwd`) quan te la demani.
   
   * **Mètode 2: Mitjançant un programa gràfic (WinSCP o FileZilla)**
     * Descarrega i obre [WinSCP](https://winscp.net/) a Windows.
     * Crea una nova connexió amb les dades següents:
       * **Protocol de transferència:** SFTP
       * **Nom del servidor (Host name):** La IP del mòbil (`192.168.1.150`)
       * **Número de port:** `8022`
       * **Nom d'usuari:** L'obtingut amb `whoami` (`u0_a245`)
       * **Contrasenya:** La contrasenya del Termux
     * Connecta't i arrossega els fitxers (`sonda_loop.sh` i `sonda.env`) de la carpeta de Windows a la carpeta arrel del mòbil que es mostra a la dreta.

---

### Opció B: Amb cable USB (Mètode clàssic MTP)
Si no tens Wi-Fi o prefereixes fer-ho físicament:

1. Connecta el mòbil a l'ordinador amb el cable USB.
2. Al mòbil, selecciona el mode de connexió **"Transferència de fitxers" (MTP)** a les notificacions.
3. Des de Windows, obre l'Explorador de fitxers, busca el mòbil i copia els fitxers `sonda_loop.sh` i `sonda.env` a la carpeta **Descargas** (o *Download*) de l'emmagatzematge intern.
4. Obre el Termux al mòbil i copia els fitxers a la teva carpeta home executant:
   ```bash
   cp ~/storage/shared/Download/sonda_loop.sh ~
   cp ~/storage/shared/Download/sonda.env ~
   ```

---

# Executar i donar permisos
Un cop tinguis el script a la carpeta home del Termux, fes el següent per poder-lo posar en marxa:

1. **Donar permisos d'execució:**
   ```bash
   chmod +x ~/sonda_loop.sh
   ```
2. **Executar el programa:**
   ```bash
   ./sonda_loop.sh
   ```
