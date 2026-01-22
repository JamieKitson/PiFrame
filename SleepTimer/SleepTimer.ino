//#include <Wire.h>
#include "RTClib.h"
#include <LowPower.h>

// the pin that is connected to SQW
#define CLOCK_INTERRUPT_PIN 2
#define PMOS_GATE 7
#define DELAY_SECS 5

RTC_DS3231 rtc;

bool ledState = false;
volatile bool wakeFlag = false;

void wakeUp() {
  wakeFlag = true; // interrupt sets this flag
}

void setup() {
//  Wire.begin();

    // initializing the rtc
    while(!rtc.begin()) {
      digitalWrite(LED_BUILTIN, HIGH);
      delay(100);
      digitalWrite(LED_BUILTIN, LOW);  
      delay(100);
    }

//    if(rtc.lostPower()) {
        // this will adjust to the date and time at compilation
        rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
//    }

    //we don't need the 32K Pin, so disable it
    rtc.disable32K();

    // Making it so, that the alarm will trigger an interrupt
    pinMode(CLOCK_INTERRUPT_PIN, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(CLOCK_INTERRUPT_PIN), wakeUp, FALLING);

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

  pinMode(PMOS_GATE, OUTPUT);
  digitalWrite(PMOS_GATE, LOW);  // MOSFET OFF at boot
}

void loop() {

      digitalWrite(LED_BUILTIN, HIGH);
      delay(100);
      digitalWrite(LED_BUILTIN, LOW);  
      delay(100);
      digitalWrite(LED_BUILTIN, HIGH);
      delay(100);
      digitalWrite(LED_BUILTIN, LOW);  
      delay(100);

  rtc.setAlarm1(rtc.now() + TimeSpan(DELAY_SECS), DS3231_A1_Second);  // Alarm triggers when seconds=0 of next minute

  // Go to sleep until RTC triggers interrupt
  wakeFlag = false;
  
  while (!wakeFlag) {
    LowPower.powerDown(SLEEP_FOREVER, ADC_OFF, BOD_OFF);
  }

  // Wake up, toggle LED
  ledState = !ledState;
  digitalWrite(LED_BUILTIN, HIGH);
  digitalWrite(PMOS_GATE, HIGH);   // MOSFET ON
  delay(5000);
  digitalWrite(LED_BUILTIN, LOW);
  digitalWrite(PMOS_GATE, LOW);  // MOSFET OFF

  // Clear the alarm so it can trigger next time
  rtc.clearAlarm(1);
  
}
