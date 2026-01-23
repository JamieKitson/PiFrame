#include <Wire.h>
#include <RTClib.h>
#include <LowPower.h>

// ------------------------- Pin definitions -------------------------
#define PIN_PI_POWER      7
#define PIN_BUTTON        3
#define PIN_BATTERY       A0
#define PIN_RTC_INT       2

// ------------------------- Globals -------------------------
RTC_DS3231 rtc;

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
    const float R2 = 10000.0;  // bottom resistor in voltage divider
    const float DIVIDER_RATIO = (R1 + R2) / R2;  // actual LiPo voltage
    const float VREF = 3.3; // 1.1;
    uint16_t raw = analogRead(PIN_BATTERY);
    return (raw / 1023.0) * VREF * DIVIDER_RATIO;
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

// ------------------------- RTC alarm -------------------------
#define SLEEP_MINUTES     1

void setRTCAlarm24h() {
    DateTime now = rtc.now();
    DateTime wake = now + TimeSpan(0, SLEEP_MINUTES, 0, 0); // 24 hours later
    rtc.clearAlarm(1);
    rtc.setAlarm1(wake, DS3231_A1_Date); // match date/time
//    rtc.armAlarm(1, true);
    rtc.clearAlarm(1); // clear previous flags
}

// ------------------------- I2C -------------------------
#define I2C_ADDRESS 0x12
#define SHUTDOWN_DELAY_SECS 30
volatile uint8_t currentRegister = 0x00;

void onI2CReceive(int numBytes) {
    while (Wire.available()) {
        uint8_t cmd = Wire.read();
        switch (cmd) {
            case 0x01:
            case 0x02:
                currentRegister = cmd;
                break;

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
            uint8_t v = (uint8_t)(readBatteryVoltage() * 25);
            Wire.write(v);
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

// ------------------------- Setup -------------------------
void setup() {

    pinMode(PIN_PI_POWER, OUTPUT);
    pinMode(PIN_BUTTON, INPUT_PULLUP);
    pinMode(PIN_RTC_INT, INPUT_PULLUP);

    attachInterrupt(digitalPinToInterrupt(PIN_BUTTON), buttonISR, FALLING);
    attachInterrupt(digitalPinToInterrupt(PIN_RTC_INT), rtcISR, FALLING);

    // initializing the rtc
    while(!rtc.begin()) {
      digitalWrite(LED_BUILTIN, HIGH);
      delay(100);
      digitalWrite(LED_BUILTIN, LOW);  
      delay(100);
    }

    //we don't need the 32K Pin, so disable it
    rtc.disable32K();

    // set alarm 1, 2 flag to false (so alarm 1, 2 didn't happen so far)
    // if not done, this easily leads to problems, as both register aren't reset on reboot/recompile
    rtc.clearAlarm(1);
    rtc.clearAlarm(2);

    // stop oscillating signals at SQW Pin
    // otherwise setAlarm1 will fail
    rtc.writeSqwPinMode(DS3231_OFF);

    // turn off alarm 2 (in case it isn't off already)
    // again, this isn't done at reboot, so a previously set alarm could easily go overlooked
    rtc.disableAlarm(2);

    Wire.begin(I2C_ADDRESS);
    Wire.onReceive(onI2CReceive);
    Wire.onRequest(onI2CRequest);

    turnPiOn(); // power Pi on startup

    buttonIRQ = false;
}

// ------------------------- Main loop -------------------------
void loop() {

    updateLed();
    
    // --- Handle button press ---
    if (buttonIRQ) {
        buttonIRQ = false;

        if (piState != PI_ON) turnPiOn();        // turn Pi on if off
        buttonEventToSend = true;     // notify Pi of button press
    }

    // --- Handle Pi shutdown request ---
    if (piState == PI_SHUTDOWN_PENDING && millis() >= shutdownDeadline) {
        turnPiOff();                 // cut power after 30s

        setRTCAlarm24h();            // schedule next wake
        rtcWake = false;             // clear wake flag

        LowPower.powerDown(SLEEP_FOREVER, ADC_OFF, BOD_OFF); // sleep until RTC alarm
        return;                      // loop continues after wake
    }

    // --- Optional: read battery voltage while Pi is on ---
//    float batteryVoltage = readBatteryVoltage();
    // Can be sent over I2C when Pi requests it

    delay(50); // small loop delay
}
