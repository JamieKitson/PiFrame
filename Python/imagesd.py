#!/usr/bin/env python3

import requests
import subprocess
import os
import adafruit_ds3231
import time
import board

from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from inky.auto import auto
from gpiozero import Button
from smbus2 import SMBus, i2c_msg
from enum import IntEnum
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    """Configuration constants"""
    IMAGE_URL: str = "http://192.168.1.4/py/pics3.cgi"
    BUTTON_PIN: int = 5
    WAIT_SECONDS: int = 45
    SLEEP_MINUTES: int = 5
    LOW_VOLTAGE_THRESHOLD: float = 6.75
    I2C_ADDRESS: int = 0x12
    VOLTAGE_DIVIDER: float = 25.0
    SATURATION: float = 0.5


class I2CCommand(IntEnum):
    READ_BUTTON = 0x01
    READ_VOLTAGE = 0x02
    SHUTDOWN = 0x10


class I2CController:
    """Handles I2C communication with Arduino"""
    
    def __init__(self, address: int = Config.I2C_ADDRESS):
        self.address = address
    
    def _send_command(self, cmd: I2CCommand) -> int:
        """Send I2C command and return response"""
        try:
            with SMBus(1) as bus:
                bus.write_byte(self.address, cmd)
                msg = i2c_msg.read(self.address, 1)
                bus.i2c_rdwr(msg)
                return list(msg)[0]
        except Exception as e:
            print(f"I2C communication error: {e}")
            return -1
    
    def read_voltage(self) -> float:
        """Read battery voltage"""
        raw_voltage = self._send_command(I2CCommand.READ_VOLTAGE)
        return raw_voltage / Config.VOLTAGE_DIVIDER
    
    def arduino_button_pressed(self) -> bool:
        """Check if Arduino button is pressed with debouncing"""
        button_pressed = False
        while self._send_command(I2CCommand.READ_BUTTON) == 1:
            button_pressed = True
            time.sleep(0.1)
        return button_pressed
    
    def shutdown(self) -> int:
        """Send shutdown command"""
        return self._send_command(I2CCommand.SHUTDOWN)


class RTCController:
    """Handles RTC alarm configuration"""
    
    def __init__(self):
        self.i2c_bus = board.I2C()
        self.rtc = adafruit_ds3231.DS3231(self.i2c_bus)
        self._disable_32khz_output()
    
    def _disable_32khz_output(self):
        """Disable the 32kHz output pin to save power"""
        DS3231_STATUSREG = 0x0F
        EN32KHZ_BIT = 3
        
        status = bytearray(1)
        self.rtc.i2c_device.write_then_readinto(bytes([DS3231_STATUSREG]), status)
        status[0] &= ~(1 << EN32KHZ_BIT)
        self.rtc.i2c_device.write(bytes([DS3231_STATUSREG, status[0]]))
    
    def set_alarm(self, minutes: int):
        """Set RTC alarm for specified minutes from now"""
        self.rtc.alarm1_status = False
        
        now = time.mktime(self.rtc.datetime)
        alarm_time = time.localtime(now + minutes * 60)
        self.rtc.alarm1 = (alarm_time, "monthly")
        self.rtc.alarm1_interrupt = True
        
        print(f"RTC alarm set for {minutes} minute(s) from now")


class NotificationService:
    """Handles voltage notifications"""
    
    @staticmethod
    def send_low_voltage_email(voltage: float):
        """Send email notification for low voltage"""
        try:
            subject = f"PiFrame Low Voltage Alert: {voltage:.2f}V"
            body = f"""Warning: PiFrame battery voltage is low!

Current Voltage: {voltage:.2f}V
Threshold: {Config.LOW_VOLTAGE_THRESHOLD}V

Please charge or replace the battery soon.
"""
            subprocess.run(
                ["s-nail", "-s", subject, os.getenv("USER", "root")],
                input=body.encode(),
                check=True
            )
            print("Low voltage email sent to local user mailbox")
        except subprocess.CalledProcessError as e:
            print(f"Failed to send email: {e}")
        except FileNotFoundError:
            print("s-nail command not found")


class ImageProcessor:
    """Handles image fetching and processing"""
    
    def __init__(self, url: str):
        self.url = url
    
    def fetch_image(self, voltage: float) -> Image.Image:
        """Fetch image from server"""
        response = requests.get(f"{self.url}?v={voltage:.2f}")
        return Image.open(BytesIO(response.content))
    
    def add_voltage_warning(self, img: Image.Image, voltage: float) -> Image.Image:
        """Add low voltage warning overlay to image"""
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24
            )
        except:
            font = ImageFont.load_default()
        
        warning_text = f"LOW BATTERY: {voltage:.2f}V"
        bbox = draw.textbbox((0, 0), warning_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        x = (img.width - text_width) // 2
        y = 10
        padding = 5
        
        draw.rectangle(
            [(x - padding, y - padding), 
             (x + text_width + padding, y + text_height + padding)],
            fill=(255, 0, 0)
        )
        draw.text((x, y), warning_text, fill=(255, 255, 255), font=font)
        
        return img
    
    def save_image(self, img: Image.Image, filename: str = "image.jpg"):
        """Save image to disk"""
        scriptdir = os.path.dirname(os.path.abspath(__file__))
        filepath = os.path.join(scriptdir, filename)
        img.save(filepath)


class PiFrameController:
    """Main controller for PiFrame operations"""
    
    def __init__(self):
        self.i2c = I2CController()
        self.rtc = RTCController()
        self.notification = NotificationService()
        self.image_processor = ImageProcessor(Config.IMAGE_URL)
        self.inky = auto()
        self.pi_button = Button(Config.BUTTON_PIN)
    
    def update_display(self):
        """Fetch and display new image"""
        voltage = self.i2c.read_voltage()
        print(f"Battery voltage: {voltage:.2f}V")
        
        # Fetch and process image
        img = self.image_processor.fetch_image(voltage)
        self.image_processor.save_image(img)
        resized_img = img.resize(self.inky.resolution)
        
        # Add warning if voltage is low
        if voltage < Config.LOW_VOLTAGE_THRESHOLD:
            print(f"WARNING: Low voltage detected ({voltage:.2f}V)")
            self.notification.send_low_voltage_email(voltage)
            resized_img = self.image_processor.add_voltage_warning(resized_img, voltage)
        
        # Display image
        try:
            self.inky.set_image(resized_img, saturation=Config.SATURATION)
        except TypeError:
            self.inky.set_image(resized_img)
        
        self.inky.show()
    
    def wait_for_input(self) -> Optional[str]:
        """Wait for button input, return action or None"""
        print(f"Waiting {Config.WAIT_SECONDS} seconds for input...")

        # Clear any existing button presses
        self.i2c.arduino_button_pressed()

        start = time.time()
        
        while time.time() - start < Config.WAIT_SECONDS:
            if self.pi_button.is_pressed:
                return "cancel"
            
            if self.i2c.arduino_button_pressed():
                return "restart"
            
            time.sleep(0.1)
        
        return None
    
    def shutdown(self):
        """Shutdown the system"""
        self.rtc.set_alarm(Config.SLEEP_MINUTES)
        response = self.i2c.shutdown()
        print(f"I2C Shutdown command response: {response}")
        subprocess.run(["sudo", "shutdown", "-h", "now"])
    
    def run(self):
        """Main run loop"""
        self.update_display()
        
        action = self.wait_for_input()
        
        if action == "cancel":
            print("Shutdown cancelled")
            return
        elif action == "restart":
            print("Arduino button pressed: restarting script")
            os.execv(__file__, ["python3", __file__])
        else:
            print("No button press, shutting down")
            self.shutdown()


def main():
    """Entry point"""
    controller = PiFrameController()
    controller.run()


if __name__ == "__main__":
    main()