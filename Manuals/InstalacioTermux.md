# Instal·lació d'F-Droid al mòbil
1. Descarregar l'apk de la pàgina [d'Fdroid](https://f-droid.org/F-Droid.apk) o anar al pàgina [d'Fdroid](https://f-droid.org/es/)
2. Executar i permetre descarregar les aplicacions d'aquesta font
3. Instal·lar i obrir

# Instal·lació de Termux i Termux API
1. Anar a F-Droid
2. Cerca (Botó de lupa): Termux (El trobarem baixant i escollint l'emulador de terminal i paquets). Descarregar. Instal·lar. Si surt un missatge de **Google Play Protect - Aplicación no segura bloqueada***, desplegar i trobareu **Instalar de todas formas**. **NO PICAR DAUMNT ENTENDIDO**
3. Permetre les aplicacions de la font de F-Droid
4. Cerca (Botó de lupa): Termux API. Descarregar. Instal·lar.

# Instal·lar dependències
- Instal·lar mosquitto, jq i curl. Escriure: `pkg install -y jq curl mosquitto`

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
1. 







