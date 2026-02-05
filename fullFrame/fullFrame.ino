#include <Wire.h>
#include <LowPower.h>

// ------------------------- Pin definitions -------------------------
#define PIN_PI_POWER      7
#define PIN_BUTTON        3
#define PIN_BATTERY       A0
#define PIN_RTC_INT       2

// ------------------------- Globals -------------------------
volatile bool buttonIRQ = false;
volatile bool rtcWake = false;

uint32_t shutdownDeadline = 0; // millis() timestamp
volatile bool buttonEventToSend = false;

enum PiPowerState {
    PI_OFF,
    PI_ON,
    PI_SHUTDOWN_PENDING
};

volatile PiPowerState piState = PI_OFF;

// ------------------------- Functions -------------------------
float readBatteryVoltage() {
    const float R1 = 20000.0; // top resistor in voltage divider
    const float R2 = 10000.0; // bottom resistor in voltage divider
    const float DIVIDER_RATIO = (R1 + R2) / R2;
    const float VREF = 3.3; // Arduino ADC reference voltage
    uint16_t raw = analogRead(PIN_BATTERY);
    return (raw / 1023.0) * VREF * DIVIDER_RATIO; // actual LiPo voltage
}

// ------------------------- ISRs -------------------------
void buttonISR() {
    buttonIRQ = true;
}

void rtcISR() {
    rtcWake = true; // wake occurs automatically
}

// ------------------------- Pi control -------------------------
void turnPiOn() {
    digitalWrite(PIN_PI_POWER, HIGH);
    piState = PI_ON;
}

void turnPiOff() {
    digitalWrite(PIN_PI_POWER, LOW);
    piState = PI_OFF;    
}

// ------------------------- I2C -------------------------
#define I2C_ADDRESS 0x12
#define SHUTDOWN_DELAY_SECS 10
volatile uint8_t currentRegister = 0x00;

void onI2CReceive(int numBytes) {
    while (Wire.available()) {
        currentRegister = Wire.read();
        switch (currentRegister) {
            case 0x10:  // Pi shutting down
                piState = PI_SHUTDOWN_PENDING;
                shutdownDeadline = millis() + SHUTDOWN_DELAY_SECS * 1000;
              break;

            case 0x11:  // cancel shutdown (optional)
                piState = PI_ON;
                break;
        }
    }
}

void onI2CRequest() {
    switch (currentRegister) {
        case 0x01:  // button
            Wire.write(buttonEventToSend ? 1 : 0);
            buttonEventToSend = false;  // clear after read
            break;

        case 0x02: {  // voltage
            // Simple scaling to fit voltage into 0-255 range, will be 6v - 8.4v
            uint8_t v = (uint8_t)(readBatteryVoltage() * 25);
            Wire.write(v);
            break;
        }

        case 0x10: 
        case 0x11: { // Pi power state
            Wire.write(piState);
            break;
        }

        default:
            Wire.write(0xFF);  // invalid register
    }
}

// ------------------------- LED Status -------------------------

void updateLed() {
    static unsigned long lastToggle = 0;
    static bool ledOn = false;

    switch (piState) {
        case PI_OFF:
            digitalWrite(LED_BUILTIN, LOW);
            break;

        case PI_ON:
            digitalWrite(LED_BUILTIN, HIGH);
            break;

        case PI_SHUTDOWN_PENDING:
            if (millis() - lastToggle >= 500) {  // 2 Hz blink
                lastToggle = millis();
                ledOn = !ledOn;
                digitalWrite(LED_BUILTIN, ledOn ? HIGH : LOW);
            }
            break;
    }
}

void blink(int times, int delayMs = 100)
{
  for(int i = 0; i < times; i++)
  {
    digitalWrite(LED_BUILTIN, HIGH);
    delay(delayMs);
    digitalWrite(LED_BUILTIN, LOW);  
    delay(delayMs);
  }  
}

// ------------------------- RTC 32KHz Disable -------------------------

// DS3231 I2C address and registers
#define DS3231_ADDRESS 0x68
#define DS3231_STATUSREG 0x0F
#define EN32KHZ_BIT 3

// We cannot use the built-in RTClib functions to disable the 32KHz output as
// we don't want to perpetually be an I2C master, so we implement it ourselves
// However, currently this is implemented and called in the Python code
void disable32K() {
    // Read current status register
    Wire.beginTransmission(DS3231_ADDRESS);
    Wire.write(DS3231_STATUSREG);
    Wire.endTransmission();

    Wire.requestFrom(DS3231_ADDRESS, 1);
    uint8_t status = Wire.read();

    // Clear bit 3 (EN32kHz)
    status &= ~(0x1 << EN32KHZ_BIT);  // Clear bit 3

    // Write back
    Wire.beginTransmission(DS3231_ADDRESS);
    Wire.write(DS3231_STATUSREG);
    Wire.write(status);
    Wire.endTransmission();
}

// ------------------------- Setup -------------------------
void setup() {

    pinMode(PIN_PI_POWER, OUTPUT);
    pinMode(PIN_BUTTON, INPUT_PULLUP);
    pinMode(PIN_RTC_INT, INPUT_PULLUP);

    attachInterrupt(digitalPinToInterrupt(PIN_BUTTON), buttonISR, FALLING);
    attachInterrupt(digitalPinToInterrupt(PIN_RTC_INT), rtcISR, FALLING);

    Wire.begin(I2C_ADDRESS);
    Wire.onReceive(onI2CReceive);
    Wire.onRequest(onI2CRequest);

    turnPiOn(); // power Pi on startup

    buttonIRQ = false;

}

// ------------------------- Main loop -------------------------
void loop() {

    updateLed();

    // --- Low power mode ---
    if (piState == PI_OFF) {
        // If Pi is off, enter low power mode
        LowPower.powerDown(SLEEP_FOREVER, ADC_OFF, BOD_OFF);
    }    

    // --- Handle button press ---
    if (buttonIRQ) {
        buttonIRQ = false;

        if (piState != PI_ON) {
            turnPiOn();        // turn Pi on if off
        }
        else {
            buttonEventToSend = true;     // notify Pi of button press
        }
    }

    // --- Handle Pi shutdown request ---
    if (piState == PI_SHUTDOWN_PENDING && millis() >= shutdownDeadline) {
        turnPiOff();                 // cut power after 30s
    }

    // --- Handle waking Pi ---
    if (rtcWake) {
        rtcWake = false;
        turnPiOn();                 // ensure Pi is on after RTC wake
    }

    delay(50); // small loop delay
}
