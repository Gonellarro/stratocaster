#include <LoRa.h>
#include <PubSubClient.h> // Librería para MQTT
#include <WiFi.h>     
#include <ESPAsyncWebServer.h>
const char* ssid = "TU_RED_WIFI"; 
const char* password = "TU_CONTRASEÑA_WIFI";  
AsyncWebServer server(80); 
const char* mqtt_server = "10.10.10.10"; //IP del servidor de MQTT

// Pines LoRa
#define LORA_SCK 5
#define LORA_MISO 19
#define LORA_MOSI 27
#define LORA_SS 18
#define LORA_RST 14
#define LORA_DI0 26

// Mensaje recibido y datos a enviar
String incoming = "";
String longitud = "";   
String latitud = "";
String coordenadas = "";
String fecha = "";
String hora = "";
String altitud = "";
String rumbo = "";
String velocidad = "";
String dispositivo = "";
int tiempoReset = 60000; // Tiempo de reset de LORA 60 segundos


WiFiClient espClient;
PubSubClient client(espClient);
const long interval = 10000;  // Intervalo de 10 segundos (10000 ms)
unsigned long previousMillis = 0;  // Almacena el último tiempo en el que se actualizó el LED

unsigned long currentMillis1 = millis();  // Obtiene el tiempo actual
unsigned long previousMillis1 = 0;

void setup() {
  // Configura el monitor serie
  Serial.begin(115200);

  // Configura LoRa
  LoRa.setPins(LORA_SS, LORA_RST, LORA_DI0);
  if (!LoRa.begin(868E6)) {  // Frecuencia 915 MHz (ajusta según tu región)
    Serial.println("No se pudo inicializar LoRa.");
    while (1);
  }
  Serial.println("LoRa inicializado.");

  // Connect to Wi-Fi 
	 WiFi.begin(ssid, password); 
	 while (WiFi.status() != WL_CONNECTED) { 
	   delay(1000); 
	   Serial.println("Connecting to WiFi..."); 
	 } 
	 Serial.println("Connected to WiFi"); 
	 // Print the ESP32's IP address 
	 Serial.print("ESP32 Web Server's IP address: "); 
	 Serial.println(WiFi.localIP()); 

  // Define a route to serve the HTML page
    server.on("/", HTTP_GET, [](AsyncWebServerRequest* request) {
    Serial.println("ESP32 Web Server: New request received:");  // for debugging

    String html = "<!DOCTYPE HTML>";
    html += "<html>";
    html += "<head>";
    html += "<link rel=\"icon\" href=\"data:,\">";
    html += "</head>";
    html += "<p>";
    html += "Coordenades rebudes: <span style=\"color: red;\">";
    html += incoming;
    html += "</span>";
    html += "</p>";
    html +=  "<a href='https://www.google.com/maps?q=" + latitud + "," + longitud +"'>Coordenades</a>";
    html += "</html>";

    request->send(200, "text/html", html);
  });

  // Start the server
  server.begin();  

  // Conexión al servidor MQTT
  client.setServer(mqtt_server, 1883);

  // Conectar a MQTT
  reconnectMQTT();


}

void loop() {
  //Serial.println("Inicia el loop");


  // Verificar si hay un paquete LoRa disponible
  int packetSize = LoRa.parsePacket();
  if (packetSize) {
    // Recibir datos del paquete
    incoming = "";
    bool salir = false; 
    while (LoRa.available()) {
      incoming += (char)LoRa.read();
    }
    // Mostrar el mensaje recibido
    Serial.println(incoming);

    //Extraemos las coordenadas del paquete recibido por LORA
    extraeCoordenadas();

    // Enviamos las coordenadas al servidor MQTT
    enviaDatosMQTT();
    
  }
  else{
  // Si no recibimos nada en LORA
  // Comprueba si han pasado más de tiempoReset y si es así, reiniciamos LORA
    currentMillis1 = millis();
    if (currentMillis1 - previousMillis1 >= tiempoReset) {  
      previousMillis1 = currentMillis1;      
      Serial.println("Sense rebre dades durant 60 segons, reiniciam lora");
      incoming = "Sense rebre dades durant 60 segons, reiniciam lora";
      LoRa.end();  // Parar LoRa
      delay(1000); // Esperar un segundo antes de reiniciar
      if (!LoRa.begin(868E6)) {
        Serial.println("Error al reiniciar LoRa");
        incoming += "Error al reiniciar LoRa";
      } else {
        Serial.println("LoRa reiniciado correctamente");
        incoming += "LoRa reiniciado correctamente";
        reconnectMQTT();
      }
    }   
  }   
}

void extraeCoordenadas(){
  // Montam aquí la URL a partir de les dades rebudes
    char separator1 = ';';  // El carácter separador
    char separator2 = ',';
    int startIndex = 0;
    int endIndex = 0; 

  // Extraer dispositivo
    startIndex = 0;
    endIndex = incoming.indexOf(separator1);  // Busca el índice del separador
    dispositivo = incoming.substring(startIndex, endIndex);  // Extrae las coordenadas
    incoming = incoming.substring(endIndex + 1);     

  // Extraer la coordenadas
    startIndex = 0;
    endIndex = incoming.indexOf(separator1);  // Busca el índice del separador
    coordenadas = incoming.substring(startIndex, endIndex);  // Extrae las coordenadas
    incoming = incoming.substring(endIndex + 1);

  // Extraer la longitud
    endIndex = coordenadas.indexOf(separator2);  // Busca el índice del separador
    latitud = coordenadas.substring(startIndex, endIndex);  // Extrae la longitud
  
  // Extraer la latitud
    startIndex = endIndex + 1;  // Mueve el índice de inicio
    longitud = coordenadas.substring(startIndex);  // Extrae la latitud hasta el final

    //Serial.println(longitud + "," +  latitud);

  // Extraer la fecha
    startIndex = 0;
    endIndex = incoming.indexOf(separator1);  // Busca el índice del separador
    fecha = incoming.substring(startIndex, endIndex);  // Extrae las coordenadas
    incoming = incoming.substring(endIndex + 1);

  // Extraer la hora
    startIndex = 0;
    endIndex = incoming.indexOf(separator1);  // Busca el índice del separador
    hora = incoming.substring(startIndex, endIndex);  // Extrae las coordenadas
    incoming = incoming.substring(endIndex + 1);    

  // Extraer la altitud
    startIndex = 0;
    endIndex = incoming.indexOf(separator1);  // Busca el índice del separador
    altitud = incoming.substring(startIndex, endIndex);  // Extrae las coordenadas
    incoming = incoming.substring(endIndex + 1);   

  // Extraer el rumbo
    startIndex = 0;
    endIndex = incoming.indexOf(separator1);  // Busca el índice del separador
    rumbo = incoming.substring(startIndex, endIndex);  // Extrae las coordenadas
    incoming = incoming.substring(endIndex + 1);       

  // Extraer la velocidad
    startIndex = 0;
    endIndex = incoming.indexOf(separator1);  // Busca el índice del separador
    velocidad = incoming.substring(startIndex, endIndex);  // Extrae las coordenadas
    incoming = incoming.substring(endIndex + 1);   

}

void enviaDatosMQTT(){

  unsigned long currentMillis = millis();  // Obtiene el tiempo actual
  // Comprueba si ha pasado más de 100 mili segundos. Si ha pasado, enviamos los datos por MQTT
  
  if (currentMillis - previousMillis >= 100) {  
    previousMillis = currentMillis;

    if (!client.connected()) {
        reconnectMQTT();  // Reconectar si la conexión se pierde
    }

    Serial.println("Datos recibidos: " + latitud + "," + longitud + ";" + fecha + ";" + hora + ";" + altitud + ";" + rumbo + ";" + velocidad);
    //String payload = String("{\"lat\":") + latitud + ",\"lng\":" + longitud + "}";
    String payload = String("{\"lat\":") + latitud + ",\"lng\":" + longitud +
                  ",\"fecha\":\"" + fecha + "\",\"hora\":\"" + hora + "\"," +
                  "\"altitud\":" + altitud + ",\"rumbo\":" + rumbo + ",\"velocidad\":" + velocidad + "}";
    Serial.println("Enviant per MQTT..." + payload);
    if (dispositivo == "L"){
      client.publish("gpsLILYGO/datos", payload.c_str());  // Topic y mensaje
      previousMillis1 = currentMillis;
      incoming = payload;
    }
    else if (dispositivo == "T"){
      client.publish("gpsTTGO/datos", payload.c_str());  // Topic y mensaje
      previousMillis1 = currentMillis;
      incoming = payload;
    }
    else if (dispositivo == "J"){
      client.publish("gpsJUANJOGO/datos", payload.c_str());  // Topic y mensaje
      previousMillis1 = currentMillis;
      incoming = payload;
    }    
    else{
      Serial.println("Dispositiu desconegut. No enviam dades");
      incoming = "Dispositiu desconegut. No enviam dades";
    }
  }
}
// Función para conectar a MQTT
void reconnectMQTT() {
  while (!client.connected()) {
    Serial.print("Connecting to MQTT...");
    if (client.connect("ClientMQTTLora")) {  // Intentar conexión con el broker
      Serial.println("connected");

      // Puedes añadir aquí las suscripciones si es necesario
    } else {
      Serial.print("failed with state ");
      Serial.print(client.state());
      delay(2000);  // Esperar 2 segundos antes de reintentar
    }
  }
}
