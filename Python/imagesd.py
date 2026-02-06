#!/usr/bin/env python3

import sys
import requests
import subprocess
import os
import adafruit_ds3231
import time
import board

from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from inky.auto import auto as inky_auto
from gpiozero import Button
from smbus2 import SMBus, i2c_msg
from enum import IntEnum

url = "http://192.168.1.4/py/pics3.cgi"
BUTTON_PIN = 5
WAIT_SECONDS = 45
SLEEP_MINUTES = 5
LOW_VOLTAGE_THRESHOLD = 6.75
SATURATION = 0.5

# Get the directory containing this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

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

def shutdown():
    """Send shutdown command"""
    return i2c(I2CCommand.SHUTDOWN)

# rtc.disable_oscillator does not appear to work, so we implement our own
def disable_32khz_output(rtc):
    """Disable the 32kHz output pin on DS3231"""
    DS3231_STATUSREG = 0x0F
    EN32KHZ_BIT = 3
    
    # Read current status register
    status = bytearray(1)
    rtc.i2c_device.write_then_readinto(bytes([DS3231_STATUSREG]), status)
    
    # Clear bit 3 (EN32kHz)
    status[0] &= ~(1 << EN32KHZ_BIT)
    
    # Write back
    rtc.i2c_device.write(bytes([DS3231_STATUSREG, status[0]]))

def setRtcAlarm(minutes):
    i2c_bus = board.I2C()  # uses board.SCL and board.SDA
    rtc = adafruit_ds3231.DS3231(i2c_bus)

    # Disable 32kHz output to save a lot of power
    disable_32khz_output(rtc)

    # reset alarm status to clear any existing alarm flags
    rtc.alarm1_status = False

    # Set alarm for 'minutes' minutes from now
    now = time.mktime(rtc.datetime)
    alarm_time = time.localtime(now + minutes * 60)
    rtc.alarm1 = (alarm_time, "monthly")
    
    # Enable alarm interrupt mode (after alarm is configured)
    rtc.alarm1_interrupt = True
    print(f"RTC alarm set for {minutes} minute(s) from now")

def send_low_voltage_email(voltage):
    """Send email notification for low voltage using local mail"""
    try:
        subject = f"PiFrame Low Voltage Alert: {voltage:.2f}V"
        body = f"""Warning: PiFrame battery voltage is low!

Current Voltage: {voltage:.2f}V
Threshold: {LOW_VOLTAGE_THRESHOLD}V

Please charge or replace the battery soon.
"""
        MAIL_CMD = "s-nail"
        # Send to current user - mail will deliver to local mailbox
        subprocess.run(
            [MAIL_CMD, "-s", subject, os.getenv("USER", "root")],
            input=body.encode(),
            check=True
        )
        
        print(f"Low voltage email sent to local user mailbox")
    except subprocess.CalledProcessError as e:
        print(f"Failed to send email: {e}")
    except FileNotFoundError:
        print(f"{MAIL_CMD} command not found.")

def add_voltage_warning(img, voltage):
    """Add low voltage warning text to image"""
    draw = ImageDraw.Draw(img)
    
    # Try to use a larger font, fall back to default if not available
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
    except:
        font = ImageFont.load_default()
    
    warning_text = f"LOW BATTERY: {voltage:.2f}V"
    
    # Get text size for background rectangle
    bbox = draw.textbbox((0, 0), warning_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # Position at top center with padding
    x = (img.width - text_width) // 2
    y = 10
    padding = 5
    
    # Draw background rectangle
    draw.rectangle(
        [(x - padding, y - padding), 
         (x + text_width + padding, y + text_height + padding)],
        fill=(255, 0, 0)  # Red background
    )
    
    # Draw white text
    draw.text((x, y), warning_text, fill=(255, 255, 255), font=font)
    
    return img

inky = inky_auto()

voltage = read_voltage()
print(f"Battery voltage: {voltage:.2f}V")

response = requests.get(url + f"?v={voltage:.2f}")
img = Image.open(BytesIO(response.content))

img.save(os.path.join(SCRIPT_DIR, "image.jpg"))
resizedimage = img.resize(inky.resolution)

# Check for low voltage and send email if needed
if voltage < LOW_VOLTAGE_THRESHOLD:
    print(f"WARNING: Low voltage detected ({voltage:.2f}V < {LOW_VOLTAGE_THRESHOLD}V)")

    send_low_voltage_email(voltage)
    resizedimage = add_voltage_warning(resizedimage, voltage)

try:
    inky.set_image(resizedimage, saturation=SATURATION)
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
        os.execv(sys.executable, [sys.executable, __file__]) # os.execv replaces the current process
        break

    time.sleep(0.1)

print("No button press, shutting down")
setRtcAlarm(SLEEP_MINUTES)
piState = shutdown()
print(f"I2C Shutdown command response: {piState}")
subprocess.run(["sudo", "shutdown", "-h", "now"])

