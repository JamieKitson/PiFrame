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
volatile bool i2cShutdownRequested = false;

bool piOn = false;
uint32_t shutdownDeadline = 0; // millis() timestamp
volatile bool buttonEventToSend = false;

// ------------------------- Functions -------------------------
float readBatteryVoltage() {
    const float R1 = 20000.0; // top resistor in voltage divider
    const float R2 = 10000.0;  // bottom resistor in voltage divider
    const float DIVIDER_RATIO = (R1 + R2) / R2; // adjust to your resistor divider
    const float VREF = 3.3; // 1.1;
//    analogReference(INTERNAL);
//    delay(5);
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
    digitalWrite(LED_BUILTIN, HIGH);
    piOn = true;
}

void turnPiOff() {
    digitalWrite(PIN_PI_POWER, LOW);
    digitalWrite(LED_BUILTIN, LOW);
    piOn = false;
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
uint8_t i2cData[2]; // [0] = button event, [1] = battery voltage (0-255)

void onI2CReceive(int numBytes) {
    while (Wire.available()) {
        uint8_t cmd = Wire.read();
        if (cmd == 0x01) {
            // Button event from Pi (optional)
        } else if (cmd == 0x02) {
            // Pi requests shutdown
            i2cShutdownRequested = true;
            shutdownDeadline = millis() + SHUTDOWN_DELAY_SECS * 1000; // 30s wait
        }
    }
}

void onI2CRequest() {
//    noInterrupts();
    i2cData[0] = buttonEventToSend ? 1 : 0;
    i2cData[1] = (uint8_t)(readBatteryVoltage() * 25); // scale ~0–11V to 0–255
    buttonEventToSend = false; // clear flag after read
//    interrupts();

    Wire.write(i2cData, 2);
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
}

// ------------------------- Main loop -------------------------
void loop() {

    // --- Handle button press ---
    if (buttonIRQ) {
        noInterrupts();
        buttonIRQ = false;
        interrupts();

        if (!piOn) turnPiOn();        // turn Pi on if off
        buttonEventToSend = true;     // notify Pi of button press
    }

    // --- Handle Pi shutdown request ---
    if (piOn && i2cShutdownRequested && millis() >= shutdownDeadline) {
        turnPiOff();                 // cut power after 30s
        i2cShutdownRequested = false;

        setRTCAlarm24h();            // schedule next wake
        rtcWake = false;             // clear wake flag

        LowPower.powerDown(SLEEP_FOREVER, ADC_OFF, BOD_OFF); // sleep until RTC alarm
        return;                      // loop continues after wake
    }

    // --- Optional: read battery voltage while Pi is on ---
    float batteryVoltage = readBatteryVoltage();
    // Can be sent over I2C when Pi requests it

    delay(50); // small loop delay
}
