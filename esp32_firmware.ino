/*
 * =====================================================================================
 * ESP32 DevKit V1 (30-Pin USB-C) - Multi-Threat Sensory Node
 * Integrates: Buzzer (Active or Passive), DHT22/DHT11, and MQ-2
 * =====================================================================================
 * 
 * BREADBOARD PINOUT (RIGHT COLUMN CONFIGURATION):
 * Oriented with USB-C connector at the TOP:
 * 
 *   - Pin 1 (Right):  VIN (5V power from USB) ---> MQ-2 VCC (for heater)
 *   - Pin 2 (Right):  GND                 ---> Breadboard Blue (-) Ground Rail
 *   - Pin 5 (Right):  D14                 <--- MQ-2 DO (Digital Output)
 *   - Pin 6 (Right):  D27                 <--- DHT Sensor DATA line
 *   - Pin 7 (Right):  D26                 ---> Red Alarm LED (+) [Optional]
 *   - Pin 8 (Right):  D25                 ---> Buzzer I/O or (+) Pin
 *   - Pin 12 (Right): D34                 <--- MQ-2 AO (Analog Output)
 *   - Pin 1 (Left):   3V3                 ---> Breadboard Red (+) Rail (for DHT & Buzzer VCC)
 * =====================================================================================
 */

#include <Arduino.h>
#include <DHT.h>

// =====================================================================================
// PIN DEFINITIONS
// =====================================================================================

const int PIN_MQ2_AO    = 34; // Pin 12 (Right) - MQ-2 Analog
const int PIN_MQ2_DO    = 14; // Pin 5  (Right) - MQ-2 Digital
const int PIN_DHT       = 27; // Pin 6  (Right) - DHT Data Line
const int PIN_BUZZER    = 25; // Pin 8  (Right) - Buzzer I/O
const int PIN_LED_ALARM = 26; // Pin 7  (Right) - Red LED (Optional)

// DHT Sensor Setup (Change to DHT11 if your sensor is blue)
#define DHTTYPE DHT22
DHT dht(PIN_DHT, DHTTYPE);

// Thresholds
int smokeAnalogThreshold = 1800;
const float HEAT_THRESHOLD_C = 48.0;

// Non-blocking intervals
const unsigned long TELEMETRY_INTERVAL_MS = 150;
const unsigned long DHT_SAMPLE_INTERVAL_MS = 2000;

enum AlertState {
  STATE_NORMAL,
  STATE_FIRE,
  STATE_WEAPON,
  STATE_SMOKE,
  STATE_HEAT
};

AlertState currentAlertState = STATE_NORMAL;

// Environmental variables
float currentTemperature = -999.0;
float currentHumidity = -999.0;
bool dhtConnected = false;

// Smoke variables
float smoothedSmokeValue = 0.0;
const float EMA_ALPHA = 0.15;
bool standaloneSmokeAlert = false;
bool mq2Connected = false;

// Non-blocking timers
unsigned long lastTelemetryTime = 0;
unsigned long lastDhtSampleTime = 0;
unsigned long lastBuzzerToggleTime = 0;
bool buzzerPhase = false;

// =====================================================================================
// BUZZER AUDIO FREQUENCY DRIVER (WORKS WITH PASSIVE & ACTIVE BUZZERS)
// =====================================================================================

void soundBuzzer(bool enable, int frequencyHz = 2200) {
  if (enable) {
    // Generate audible frequency tone (essential for passive buzzers!)
    tone(PIN_BUZZER, frequencyHz);
  } else {
    noTone(PIN_BUZZER);
    digitalWrite(PIN_BUZZER, LOW);
  }
}

// =====================================================================================
// COMMAND PROCESSING (FROM PYTHON)
// =====================================================================================

void processIncomingCommand(String cmd) {
  cmd.trim();
  cmd.toUpperCase();

  if (cmd == "ALERT:FIRE") {
    currentAlertState = STATE_FIRE;
  } else if (cmd == "ALERT:GUN" || cmd == "ALERT:KNIFE" || cmd == "ALERT:WEAPON") {
    currentAlertState = STATE_WEAPON;
  } else if (cmd == "ALERT:SMOKE") {
    currentAlertState = STATE_SMOKE;
  } else if (cmd == "ALERT:HEAT") {
    currentAlertState = STATE_HEAT;
  } else if (cmd == "ALERT:CLEAR" || cmd == "ALERT:NORMAL") {
    currentAlertState = STATE_NORMAL;
    soundBuzzer(false);
    digitalWrite(PIN_LED_ALARM, LOW);
  } else if (cmd.startsWith("THRESHOLD:")) {
    int val = cmd.substring(10).toInt();
    if (val > 100 && val < 4000) {
      smokeAnalogThreshold = val;
    }
  }
}

// =====================================================================================
// SETUP
// =====================================================================================

void setup() {
  Serial.begin(115200);

  pinMode(PIN_MQ2_AO, INPUT);
  pinMode(PIN_MQ2_DO, INPUT_PULLUP);
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_LED_ALARM, OUTPUT);

  digitalWrite(PIN_LED_ALARM, LOW);
  soundBuzzer(false);

  dht.begin();

  int rawInit = analogRead(PIN_MQ2_AO);
  smoothedSmokeValue = (float)rawInit;

  // Startup confirmation chirp (Audible 2500Hz tone)
  soundBuzzer(true, 2500);
  digitalWrite(PIN_LED_ALARM, HIGH);
  delay(150);
  soundBuzzer(false);
  digitalWrite(PIN_LED_ALARM, LOW);

  Serial.println(F("{\"status\":\"ESP32_READY\",\"version\":\"2.0\"}"));
}

// =====================================================================================
// MAIN LOOP
// =====================================================================================

void loop() {
  unsigned long currentMillis = millis();

  // -------------------------------------------------------------------
  // 1. SAMPLE MQ-2 SENSOR
  // -------------------------------------------------------------------
  int rawSmoke = analogRead(PIN_MQ2_AO);
  mq2Connected = (rawSmoke > 20 && rawSmoke < 4090);

  smoothedSmokeValue = (EMA_ALPHA * rawSmoke) + ((1.0 - EMA_ALPHA) * smoothedSmokeValue);

  bool digitalSmokeTrigger = (digitalRead(PIN_MQ2_DO) == LOW);
  bool analogSmokeTrigger = (smoothedSmokeValue >= smokeAnalogThreshold);
  standaloneSmokeAlert = (digitalSmokeTrigger || analogSmokeTrigger) && mq2Connected;

  // -------------------------------------------------------------------
  // 2. SAMPLE DHT SENSOR (EVERY 2 SECONDS)
  // -------------------------------------------------------------------
  if (currentMillis - lastDhtSampleTime >= DHT_SAMPLE_INTERVAL_MS) {
    lastDhtSampleTime = currentMillis;

    float t = dht.readTemperature();
    float h = dht.readHumidity();

    if (isnan(t) || isnan(h) || t < -40.0 || t > 125.0) {
      dhtConnected = false;
      currentTemperature = -999.0;
      currentHumidity = -999.0;
    } else {
      dhtConnected = true;
      currentTemperature = t;
      currentHumidity = h;
    }
  }

  // -------------------------------------------------------------------
  // 3. STANDALONE LOCAL HAZARD TRIGGERS
  // -------------------------------------------------------------------
  bool standaloneHeatAlert = dhtConnected && (currentTemperature >= HEAT_THRESHOLD_C);

  if (currentAlertState == STATE_NORMAL) {
    if (standaloneSmokeAlert) {
      currentAlertState = STATE_SMOKE;
    } else if (standaloneHeatAlert) {
      currentAlertState = STATE_HEAT;
    }
  } else if (currentAlertState == STATE_SMOKE && !standaloneSmokeAlert) {
    currentAlertState = STATE_NORMAL;
    soundBuzzer(false);
  } else if (currentAlertState == STATE_HEAT && !standaloneHeatAlert) {
    currentAlertState = STATE_NORMAL;
    soundBuzzer(false);
  }

  // -------------------------------------------------------------------
  // 4. PROCESS PYTHON COMMANDS
  // -------------------------------------------------------------------
  while (Serial.available() > 0) {
    String line = Serial.readStringUntil('\n');
    processIncomingCommand(line);
  }

  // -------------------------------------------------------------------
  // 5. DRIVE AUDIBLE SIRENS & LEDS (POLICE/FIRE EMERGENCY TONES)
  // -------------------------------------------------------------------
  switch (currentAlertState) {

    case STATE_FIRE:
      // TWO-TONE EMERGENCY SIREN (1800Hz <---> 2600Hz high-low alternating)
      if (currentMillis - lastBuzzerToggleTime >= 160) {
        lastBuzzerToggleTime = currentMillis;
        buzzerPhase = !buzzerPhase;
        if (buzzerPhase) {
          soundBuzzer(true, 2600); // High pitch
          digitalWrite(PIN_LED_ALARM, HIGH);
        } else {
          soundBuzzer(true, 1750); // Low pitch
          digitalWrite(PIN_LED_ALARM, LOW);
        }
      }
      break;

    case STATE_SMOKE:
    case STATE_HEAT:
      // RAPID PULSE ALARM (2200Hz, 120ms on, 120ms off)
      if (currentMillis - lastBuzzerToggleTime >= 120) {
        lastBuzzerToggleTime = currentMillis;
        buzzerPhase = !buzzerPhase;
        soundBuzzer(buzzerPhase, 2200);
        digitalWrite(PIN_LED_ALARM, buzzerPhase ? HIGH : LOW);
      }
      break;

    case STATE_WEAPON:
      // TACTICAL WEAPON ALERT (High-pitch 2800Hz double-chirp every 500ms)
      digitalWrite(PIN_LED_ALARM, HIGH);
      {
        unsigned long cycle = currentMillis % 500;
        if (cycle < 100 || (cycle >= 180 && cycle < 280)) {
          soundBuzzer(true, 2800);
        } else {
          soundBuzzer(false);
        }
      }
      break;

    case STATE_NORMAL:
    default:
      soundBuzzer(false);
      digitalWrite(PIN_LED_ALARM, LOW);
      break;
  }

  // -------------------------------------------------------------------
  // 6. STREAM JSON TELEMETRY TO PYTHON
  // -------------------------------------------------------------------
  if (currentMillis - lastTelemetryTime >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryTime = currentMillis;

    const char* stateStr = "NORMAL";
    if (currentAlertState == STATE_FIRE) stateStr = "FIRE";
    else if (currentAlertState == STATE_WEAPON) stateStr = "WEAPON";
    else if (currentAlertState == STATE_SMOKE) stateStr = "SMOKE";
    else if (currentAlertState == STATE_HEAT) stateStr = "HEAT";

    Serial.print(F("{\"smoke\":"));
    Serial.print((int)smoothedSmokeValue);
    Serial.print(F(",\"raw\":"));
    Serial.print(rawSmoke);
    Serial.print(F(",\"smoke_alert\":"));
    Serial.print(standaloneSmokeAlert ? 1 : 0);
    Serial.print(F(",\"mq2_ok\":"));
    Serial.print(mq2Connected ? 1 : 0);

    Serial.print(F(",\"temp\":"));
    if (dhtConnected) Serial.print(currentTemperature, 1);
    else Serial.print(F("null"));

    Serial.print(F(",\"hum\":"));
    if (dhtConnected) Serial.print(currentHumidity, 1);
    else Serial.print(F("null"));

    Serial.print(F(",\"dht_ok\":"));
    Serial.print(dhtConnected ? 1 : 0);

    Serial.print(F(",\"state\":\""));
    Serial.print(stateStr);
    Serial.println(F("\"}"));
  }
}
