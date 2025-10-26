#include <WiFi.h>
#include <HTTPClient.h>
#include "AdafruitIO_WiFi.h"
#include "DHT.h"
#include <ArduinoJson.h>

// ---------- CONFIG ----------
#define IO_USERNAME  "Sagarika"
#define IO_KEY       "SECRET"
#define WIFI_SSID    "SPHONE"
#define WIFI_PASS    "SECRET"

// ---------- DHT11 ----------
#define DHTPIN 4
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

// ---------- BUZZER ----------
#define BUZZER_PIN 18

// ---------- ADAFRUIT IO ----------
AdafruitIO_WiFi io(IO_USERNAME, IO_KEY, WIFI_SSID, WIFI_PASS);

// Feeds
AdafruitIO_Feed *temperatureFeed = io.feed("temperature");
AdafruitIO_Feed *humidityFeed    = io.feed("humidity");
AdafruitIO_Feed *fireFeed        = io.feed("fire");
AdafruitIO_Feed *alarmFeed       = io.feed("alarm");
AdafruitIO_Feed *apiTempFeed     = io.feed("api_temp");
AdafruitIO_Feed *apiHumFeed      = io.feed("api_humidity");

bool fireDetected = false;

// ---------- WEATHER CONFIG ----------
const char* weatherURL = "https://api.open-meteo.com/v1/forecast?latitude=37.7749&longitude=-122.4194&current_weather=true&hourly=relativehumidity_2m";

// ---------- CALLBACK ----------
void fireChanged(AdafruitIO_Data *data) {
  fireDetected = data->toBool();
  Serial.print("🔥 Fire feed changed: ");
  Serial.println(fireDetected ? "ON" : "OFF");

  alarmFeed->save(fireDetected ? 1 : 0);

  if (fireDetected) {
    tone(BUZZER_PIN, 2000);   // buzzer ON
  } else {
    noTone(BUZZER_PIN);       // buzzer OFF
  }
}

void setup() {
  Serial.begin(115200);
  dht.begin();
  pinMode(BUZZER_PIN, OUTPUT);

  // Connect to Adafruit IO
  Serial.print("Connecting to Adafruit IO");
  io.connect();
  while (io.status() < AIO_CONNECTED) {
    Serial.print(".");
    delay(500);
  }
  Serial.println("\n Connected to Adafruit IO!");
  fireFeed->onMessage(fireChanged);
}

void loop() {
  io.run();

  // --- Read local DHT11 ---
  float temp = dht.readTemperature();
  float hum  = dht.readHumidity();

  if (!isnan(temp) && !isnan(hum)) {
    Serial.printf("Local DHT11: %.1f°C, %.1f%%\n", temp, hum);
    temperatureFeed->save(temp);
    humidityFeed->save(hum);
  } else {
    Serial.println("Failed to read from DHT sensor!");
  }

  // --- Fetch Open-Meteo Data ---
  HTTPClient http;
  http.begin(weatherURL);
  int httpCode = http.GET();

  if (httpCode == 200) {
    String payload = http.getString();
    StaticJsonDocument<2048> doc;
    DeserializationError error = deserializeJson(doc, payload);

    if (!error) {
      float apiTemp = doc["current_weather"]["temperature"];
      
      JsonArray humidityArray = doc["hourly"]["relativehumidity_2m"];
      float apiHum = NAN;
      if (!humidityArray.isNull() && humidityArray.size() > 0) {
        apiHum = humidityArray[humidityArray.size() - 1];
      }

      Serial.printf("API Weather: %.1f°C, %.1f%%\n", apiTemp, apiHum);
      apiTempFeed->save(apiTemp);
      if (!isnan(apiHum)) apiHumFeed->save(apiHum);
    } else {
      Serial.println("⚠️ JSON parse error");
    }
  } else {
    Serial.printf("Failed to fetch weather, code: %d\n", httpCode);
  }

  http.end();

  delay(10000); // 10 sec interval
}
