/*
 * =====================================================================================
 * ESP32 DevKit V1 (30-Pin USB-C) - Multi-Threat Sensory Node
 * Integrates: Buzzer, DHT22 (Temp/Humidity), and MQ-2 (Gas/Smoke)
 * =====================================================================================
 * 
 * BREADBOARD PINOUT (RIGHT COLUMN CONFIGURATION):
 * Oriented with USB-C connector at the TOP:
 * 
 * | Pin # | Name  | Connected Component | Description |
 * |---|---|---|---|
 * | Pin 1 | VN    | ---                 | GPIO 39 (Leave Free) |
 * | Pin 2 | GND   | Breadboard GND Rail | Common Ground for all sensors & buzzer |
 * | Pin 3 | D13   | ---                 | GPIO 13 (Leave Free) |
 * | Pin 4 | D12   | ---                 | GPIO 12 (Leave Free) |
 * | Pin 5 | D14   | MQ-2 DO             | Digital Threshold (Active LOW) |
 * | Pin 6 | D27   | DHT22 DATA          | Temperature & Humidity Data Line |
 * | Pin 7 | D26   | Red LED (+)         | Alarm LED via 220-330Ω resistor (Optional) |
 * | Pin 8 | D25   | Buzzer (+)          | Audio Siren Output |
 * | Pin 9 | D33   | ---                 | GPIO 33 (Leave Free) |
 * | Pin 10| D32   | ---                 | GPIO 32 (Leave Free) |
 * | Pin 11| D35   | ---                 | GPIO 35 (Leave Free) |
 * | Pin 12| D34   | MQ-2 AO             | Analog Smoke Level (ADC1_CH6, 0-4095) |
 * | Pin 13| VN    | ---                 | GPIO 39 (Leave Free) |
 * | Pin 14| VP    | ---                 | GPIO 36 (Leave Free) |
 * | Pin 15| EN    | ---                 | Reset button pin |
 * 
 * POWER WIRING:
 * Run 1 wire from [3V3] (Pin 1 on the LEFT side) to the Breadboard Red (+) Rail.
 * Connect MQ-2 VCC and DHT22 VCC to this 3.3V rail.
 * 
 * HOT-PLUG & MODULAR DESIGN:
 * This firmware operates reliably whether all 3, any 2, 1, or NO sensors are connected!
 * - If DHT22 is missing or disconnected: reports null for temp/hum, never blocks or hangs.
 * - If MQ-2 is missing: reports baseline 0, never blocks.
 * - Buzzer works seamlessly on command from Python or local triggers.
 * 
 * REQUIRED ARDUINO LIBRARY:
 * - "DHT sensor library" by Adafruit (Install via Arduino IDE Library Manager)
 * =====================================================================================
 */

#include <Arduino.h>
#include <DHT.h>

// =====================================================================================
// PIN ASSIGNMENTS (RIGHT COLUMN)
// =====================================================================================

const int PIN_MQ2_AO    = 34;  // Pin 12 (Right) - MQ-2 Analog Output
const int PIN_MQ2_DO    = 14;  // Pin 5  (Right) - MQ-2 Digital Output
const int PIN_DHT22     = 27;  // Pin 6  (Right) - DHT22 Data Pin
const int PIN_BUZZER    = 25;  // Pin 8  (Right) - Buzzer (+)
const int PIN_LED_ALARM = 26;  // Pin 7  (Right) - Red Alarm LED (+) [Optional]

// DHT Sensor Object
#define DHTTYPE DHT22
DHT dht(PIN_DHT22, DHTTYPE);

// =====================================================================================
// SENSOR CONFIGURATION & STATE
// =====================================================================================

int smokeAnalogThreshold = 1800; // ADC threshold for smoke (0-4095)
const float HEAT_THRESHOLD_C = 50.0; // High heat threshold for standalone warning

// Non-blocking telemetry and sensor sampling intervals
const unsigned long TELEMETRY_INTERVAL_MS = 150; // Stream telemetry to Python every 150ms
const unsigned long DHT_SAMPLE_INTERVAL_MS = 2000; // DHT22 maximum sample rate is 0.5Hz (2s)

enum AlertState {
  STATE_NORMAL,
  STATE_FIRE,
  STATE_WEAPON,
  STATE_SMOKE,
  STATE_HEAT
};

AlertState currentAlertState = STATE_NORMAL;

// Environmental Data
float currentTemperature = -999.0;
float currentHumidity = -999.0;
bool dhtConnected = false;

// Smoke Data
float smoothedSmokeValue = 0.0;
const float EMA_ALPHA = 0.15;
bool standaloneSmokeAlert = false;
bool mq2Connected = false;

// Timers
unsigned long lastTelemetryTime = 0;
unsigned long lastDhtSampleTime = 0;
unsigned long lastBuzzerToggleTime = 0;
bool buzzerState = false;

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

  // Initialize Pins
  pinMode(PIN_MQ2_AO, INPUT);
  pinMode(PIN_MQ2_DO, INPUT_PULLUP);
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_LED_ALARM, OUTPUT);

  digitalWrite(PIN_BUZZER, LOW);
  digitalWrite(PIN_LED_ALARM, LOW);

  // Initialize DHT22
  dht.begin();

  // Baseline calibration for MQ-2
  int rawInit = analogRead(PIN_MQ2_AO);
  smoothedSmokeValue = (float)rawInit;

  // Startup chirp confirmation
  digitalWrite(PIN_BUZZER, HIGH);
  digitalWrite(PIN_LED_ALARM, HIGH);
  delay(120);
  digitalWrite(PIN_BUZZER, LOW);
  digitalWrite(PIN_LED_ALARM, LOW);

  Serial.println(F("{\"status\":\"ESP32_READY\",\"hardware\":[\"MQ2\",\"DHT22\",\"BUZZER\"]}"));
}

// =====================================================================================
// MAIN LOOP (100% NON-BLOCKING)
// =====================================================================================

void loop() {
  unsigned long currentMillis = millis();

  // -------------------------------------------------------------------
  // 1. SAMPLE MQ-2 GAS/SMOKE SENSOR
  // -------------------------------------------------------------------
  int rawSmoke = analogRead(PIN_MQ2_AO);
  
  // Detect if sensor is plugged in (open/floating readings or connected)
  mq2Connected = (rawSmoke > 20 && rawSmoke < 4090);

  smoothedSmokeValue = (EMA_ALPHA * rawSmoke) + ((1.0 - EMA_ALPHA) * smoothedSmokeValue);

  bool digitalSmokeTrigger = (digitalRead(PIN_MQ2_DO) == LOW);
  bool analogSmokeTrigger = (smoothedSmokeValue >= smokeAnalogThreshold);
  standaloneSmokeAlert = (digitalSmokeTrigger || analogSmokeTrigger) && mq2Connected;

  // -------------------------------------------------------------------
  // 2. SAMPLE DHT22 (EVERY 2 SECONDS)
  // -------------------------------------------------------------------
  if (currentMillis - lastDhtSampleTime >= DHT_SAMPLE_INTERVAL_MS) {
    lastDhtSampleTime = currentMillis;

    float t = dht.readTemperature(); // Celsius
    float h = dht.readHumidity();    // Relative humidity %

    // If reading failed (sensor unplugged or wiring issue), handle gracefully
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
  // 3. STANDALONE FAILSAFE DETECTION (LOCAL SENSORY ALARMS)
  // -------------------------------------------------------------------
  bool standaloneHeatAlert = dhtConnected && (currentTemperature >= HEAT_THRESHOLD_C);

  // If no computer vision override from Python is active, trigger local alarms
  if (currentAlertState == STATE_NORMAL) {
    if (standaloneSmokeAlert) {
      currentAlertState = STATE_SMOKE;
    } else if (standaloneHeatAlert) {
      currentAlertState = STATE_HEAT;
    }
  } else if (currentAlertState == STATE_SMOKE && !standaloneSmokeAlert) {
    currentAlertState = STATE_NORMAL;
  } else if (currentAlertState == STATE_HEAT && !standaloneHeatAlert) {
    currentAlertState = STATE_NORMAL;
  }

  // -------------------------------------------------------------------
  // 4. READ SERIAL COMMANDS FROM PYTHON
  // -------------------------------------------------------------------
  while (Serial.available() > 0) {
    String line = Serial.readStringUntil('\n');
    processIncomingCommand(line);
  }

  // -------------------------------------------------------------------
  // 5. DRIVE BUZZER & LED ALARM PATTERNS
  // -------------------------------------------------------------------
  switch (currentAlertState) {

    case STATE_FIRE:
      // RAPID SIREN: Rapid oscillation (80ms on, 80ms off) + flashing LED
      if (currentMillis - lastBuzzerToggleTime >= 80) {
        lastBuzzerToggleTime = currentMillis;
        buzzerState = !buzzerState;
        digitalWrite(PIN_BUZZER, buzzerState ? HIGH : LOW);
        digitalWrite(PIN_LED_ALARM, buzzerState ? HIGH : LOW);
      }
      break;

    case STATE_SMOKE:
    case STATE_HEAT:
      // STACCATO ALARM: (150ms on, 150ms off)
      if (currentMillis - lastBuzzerToggleTime >= 150) {
        lastBuzzerToggleTime = currentMillis;
        buzzerState = !buzzerState;
        digitalWrite(PIN_BUZZER, buzzerState ? HIGH : LOW);
        digitalWrite(PIN_LED_ALARM, buzzerState ? HIGH : LOW);
      }
      break;

    case STATE_WEAPON:
      // WEAPON ALARM: Double-beep pattern (500ms cycle) + solid LED
      digitalWrite(PIN_LED_ALARM, HIGH);
      {
        unsigned long cycle = currentMillis % 500;
        if (cycle < 100 || (cycle >= 180 && cycle < 280)) {
          digitalWrite(PIN_BUZZER, HIGH);
        } else {
          digitalWrite(PIN_BUZZER, LOW);
        }
      }
      break;

    case STATE_NORMAL:
    default:
      digitalWrite(PIN_BUZZER, LOW);
      digitalWrite(PIN_LED_ALARM, LOW);
      break;
  }

  // -------------------------------------------------------------------
  // 6. DISPATCH JSON TELEMETRY TO PYTHON
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

    // Temperature & Humidity (null if sensor disconnected)
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
