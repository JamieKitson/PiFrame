#!/usr/bin/env python3

import argparse
import requests
import subprocess
import time
import os

from io import BytesIO
from PIL import Image
from inky.auto import auto
from gpiozero import Button
from smbus2 import SMBus, i2c_msg
from enum import IntEnum

url = "http://192.168.1.4/py/pics3.cgi"
BUTTON_PIN = 5
WAIT_SECONDS = 30

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
    button_state = i2c(I2CCommand.READ_BUTTON)
    return button_state == 1

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
piState = i2c(I2CCommand.SHUTDOWN)
print(f"I2C Shutdown command response: {piState}")
subprocess.run(["sudo", "shutdown", "-h", "now"])

