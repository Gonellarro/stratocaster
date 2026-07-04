#include <TinyGPS++.h>
#include <SoftwareSerial.h>
#include <LoRa.h>
/*
   This sample sketch demonstrates the normal use of a TinyGPSPlus (TinyGPSPlus) object.
   It requires the use of SoftwareSerial, and assumes that you have a
   4800-baud serial GPS device hooked up on pins 4(rx) and 3(tx).
*/
static const int RXPin = 12, TXPin = 34;
static const uint32_t GPSBaud = 9600;
// Fixam quin dispositiu és: T o L (TTGO o LilyGO)
String identificador = "L";
// The TinyGPSPlus object
TinyGPSPlus gps;

// The serial connection to the GPS device
SoftwareSerial ss(TXPin, RXPin);

String missatge = "Inicialitzant...";

unsigned long previousMillis = 0;  // Almacena el último tiempo en el que se actualizó el LED
const long interval = 10000;  // Intervalo de envío de 10 segundos (10000 ms)

// Pines LoRa
#define LORA_SCK 5
#define LORA_MISO 19
#define LORA_MOSI 27
#define LORA_SS 18
#define LORA_RST 14
#define LORA_DI0 26

void setup()
{
  Serial.begin(115200);
  ss.begin(GPSBaud);

  Serial.println(F("DeviceExample.ino"));
  Serial.println(F("A simple demonstration of TinyGPSPlus with an attached GPS module"));
  Serial.print(F("Testing TinyGPSPlus library v. ")); Serial.println(TinyGPSPlus::libraryVersion());
  Serial.println(F("by Mikal Hart"));
  Serial.println();

  // Configura LoRa
  LoRa.setPins(LORA_SS, LORA_RST, LORA_DI0);
  if (!LoRa.begin(868E6)) {  // Frecuencia 915 MHz (ajusta según tu región)
    Serial.println("No se pudo inicializar LoRa.");
    while (1);
  }
  Serial.println("LoRa inicializado.");

}

void loop()
{
  // This sketch displays information every time a new sentence is correctly encoded.
  while (ss.available() > 0){
    //if (gps.encode(ss.read()))
    gps.encode(ss.read());  // Codifica los datos NMEA
    displayInfo();    
    sendInfo();
  }
  if (millis() > 5000 && gps.charsProcessed() < 10)
  {
    Serial.println(F("No GPS detected: check wiring."));
    delay(1000);
  }

}

void displayInfo()
{
  //Identificam el dispositiu que envia
  missatge = identificador + ";";

  if (gps.location.isValid())
  {
    missatge += String(gps.location.lat(), 6) + "," + String(gps.location.lng(), 6);
  }
  else
  {
    missatge += ";0.0,0.0";
    Serial.println("Sense coordenades");
  }

  if (gps.date.isValid())
  {
    missatge += ";" + String(gps.date.month()) + "/" + String(gps.date.day()) + "/" + String(gps.date.year());
  }
  else
  {
    missatge += ";00/00/0000";
    Serial.println("Sense data");
  }

  if (gps.time.isValid())
  {
    missatge += ";" + String(gps.time.hour()) + ":" + String(gps.time.minute()) + ":" + String(gps.time.second());
  }
  else
  {
    Serial.println("Sense temps");
    missatge += ";00:00:00";
  }

  if(gps.altitude.isValid()){
    missatge += ";" + String(gps.altitude.meters());
  }
  else
  {
    missatge += ";0";
    Serial.println("Sense altitud");
  }

  if(gps.course.isValid()){
    missatge += ";" + String(gps.course.deg());
  }
  else
  {
    missatge += ";0";
    Serial.println("Sense rumb");
  }  

  if(gps.speed.isValid()){
    missatge += ";" + String(gps.speed.kmph());
  }
  else
  {
    missatge += ";0";
    Serial.println("Sense velocitat");
  }  


}

void sendInfo(){
  unsigned long currentMillis = millis();  // Obtiene el tiempo actual
  // Comprueba si ha pasado más de n segundos (interval)
  if (currentMillis - previousMillis >= interval) {
    previousMillis = currentMillis;  // Actualiza el tiempo del último cambio
    
    if(!missatge.startsWith("0.0,0.0;")){
      Serial.println("Enviant missatge: " + missatge);
      // Enviar las coordenadas a través de LoRa
      LoRa.beginPacket();
      LoRa.print(missatge);
      LoRa.endPacket();    
    }

  }
}
