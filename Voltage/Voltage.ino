//#include <LowPower.h>
#include <Wire.h>

const int analogPin = A0;
const float R1 = 20000.0; // top resistor in voltage divider
const float R2 = 10000.0;  // bottom resistor in voltage divider
const float ADC_REF = 3.3; // Arduino reference voltage

const byte I2C_ADDR = 0x12; // Arduino I2C address, must differ from RTC

void setup() {
  // put your setup code here, to run once:
  pinMode(LED_BUILTIN, OUTPUT);
  Wire.begin(I2C_ADDR); // join I2C bus as slave
  Wire.onRequest(sendVoltage); // called when master requests data
}

void loop() {
  // put your main code here, to run repeatedly:
//  LowPower.powerDown(SLEEP_8S, ADC_OFF, BOD_OFF);

  float batteryVoltage = getVoltage();
//  uint16_t v_int = (uint16_t)(batteryVoltage * 100);
  float d = 10.0 * (batteryVoltage - (int)batteryVoltage);

  blink((int)batteryVoltage);

  delay(1000);

  blink((int)d);

  delay(5000);
}

void blink(int times)
{
  for(int i = 0; i < times; i++)
  {
    digitalWrite(LED_BUILTIN, HIGH);
    delay(200);
    digitalWrite(LED_BUILTIN, LOW);  
    delay(200);
  }  
}

float getVoltage() {
  int raw = analogRead(analogPin);
  float voltage = (raw / 1023.0) * ADC_REF; // voltage at A0
  float batteryVoltage = voltage * (R1 + R2) / R2; // actual LiPo voltage

  // Send as two bytes (scaled by 100 for 0.01 V precision)
  return batteryVoltage; // * 100;
}

void sendVoltage() {
  float batteryVoltage = getVoltage();

  // Send as two bytes (scaled by 100 for 0.01 V precision)
  uint16_t v_int = (uint16_t)(batteryVoltage * 100);
  Wire.write(highByte(v_int));
  Wire.write(lowByte(v_int));
}
