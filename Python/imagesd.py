#!/usr/bin/env python3

import argparse
import requests
import subprocess
import time
import os
import adafruit_ds3231
import time
import board

#from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image
from inky.auto import auto
from gpiozero import Button
from smbus2 import SMBus, i2c_msg
from enum import IntEnum

url = "http://192.168.1.4/py/pics3.cgi"
BUTTON_PIN = 5
WAIT_SECONDS = 45
SLEEP_MINUTES = 5

class I2CCommand(IntEnum):
    READ_BUTTON = 0x01
    READ_VOLTAGE = 0x02
    SHUTDOWN = 0x10

def i2c(cmd):
    try:
        with SMBus(1) as bus:
            bus.write_byte(0x12, cmd)
            msg = i2c_msg.read(0x12, 1)
            bus.i2c_rdwr(msg)
            data = list(msg)
            return data[0]
    except Exception as e:
        print(f"I2C communication error: {e}")
        return -1

def read_voltage():
    voltage = i2c(I2CCommand.READ_VOLTAGE)
    return voltage / 25  # Convert to volts

def arduino_button_pressed():
    button_pressed = False
    while i2c(I2CCommand.READ_BUTTON) == 1:
        button_pressed = True
        time.sleep(0.1)  # Debounce
    return button_pressed

def setRtcAlarm(minutes):
    i2c_bus = board.I2C()  # uses board.SCL and board.SDA
    rtc = adafruit_ds3231.DS3231(i2c_bus)

    # Set alarm for 'minutes' minutes from now
    now = time.mktime(rtc.datetime)
    alarm_time = time.localtime(now + minutes * 60)
    rtc.alarm1 = (alarm_time, "once")
    
    # Enable alarm interrupt mode (after alarm is configured)
    rtc.alarm1_interrupt = True
    print(f"RTC alarm set for {minutes} minute(s) from now")

parser = argparse.ArgumentParser()

parser.add_argument("--saturation", "-s", type=float, default=0.5, help="Colour palette saturation")

inky = auto()

args, _ = parser.parse_known_args()

voltage = read_voltage()

response = requests.get(url + f"?v={voltage:.2f}")
img = Image.open(BytesIO(response.content))

img.save("/home/jamie/inky/examples/spectra6/image.jpg")
resizedimage = img.resize(inky.resolution)

try:
    inky.set_image(resizedimage, saturation=args.saturation)
except TypeError:
    inky.set_image(resizedimage)

inky.show()
# inky.show() returns before it has finished.
# clear any existing button presses to avoid wierd infinite looking photo updates
arduino_button_pressed()

print(f"Waiting {WAIT_SECONDS} seconds for input...")

start = time.time()

pi_button = Button(BUTTON_PIN) 

while time.time() - start < WAIT_SECONDS:
    if pi_button.is_pressed:
        print("Shutdown cancelled")
        exit(0)
        break

    if arduino_button_pressed():
        print("Arduino button pressed: restarting script")
        os.execv(__file__, ["python3", __file__]) # os.execv replaces the current process
        break

    time.sleep(0.1)

print("No button press, shutting down")
setRtcAlarm(SLEEP_MINUTES)
piState = i2c(I2CCommand.SHUTDOWN)
print(f"I2C Shutdown command response: {piState}")
subprocess.run(["sudo", "shutdown", "-h", "now"])

