#!/usr/bin/env python3

import sys
import requests
import subprocess
import os
import adafruit_ds3231
import time
import board
import logging

from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from inky.auto import auto as inky_auto
from gpiozero import Button
from smbus2 import SMBus, i2c_msg
from enum import IntEnum

# Get the directory containing this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(SCRIPT_DIR, "piframe.log")


def setup_logging():
    """Log to a file (emailed off-device before shutdown) and to stdout for cron capture"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH),
            logging.StreamHandler(sys.stdout),
        ],
    )

class Config:
    """Configuration for PiFrame"""
    IMAGE_URL: str = "http://192.168.1.4/py/pics3.cgi"
    PI_BUTTON_PIN: int = 5
    WAIT_BEFORE_SHUTDOWN_SECONDS: int = 45
    PI_POWER_SLEEP_MINUTES: int = 24 * 60
    LOW_VOLTAGE_THRESHOLD: float = 6.75
    IMAGE_SATURATION: float = 0.5
    ARDUINO_I2C_ADDRESS: int = 0x12
    VOLTAGE_SCALE_FACTOR: float = 25.0
    WARNING_FONT_PATH: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    WARNING_FONT_SIZE: int = 24

class I2CCommand(IntEnum):
    READ_BUTTON = 0x01
    READ_VOLTAGE = 0x02
    SHUTDOWN = 0x10

class I2CController:
    """Handles I2C communication with Arduino"""

    # BCM pin numbers used by the Pi's hardware I2C1 bus (i2c-1 / /dev/i2c-1)
    SDA_GPIO = 2
    SCL_GPIO = 3
    MAX_RETRIES = 3

    def __init__(self, address: int = Config.ARDUINO_I2C_ADDRESS):
        self.address = address

    def _recover_bus(self):
        """Bit-bang SCL to force a slave that's holding SDA low to release the bus,
        then issue a STOP condition, per the I2C spec bus-recovery procedure.
        Uses pinctrl so it works even while the kernel i2c-bcm2835 driver owns the pins.
        """
        try:
            subprocess.run(["pinctrl", "set", str(self.SCL_GPIO), "op", "dh"], check=True)
            for _ in range(9):
                subprocess.run(["pinctrl", "set", str(self.SCL_GPIO), "dl"], check=True)
                time.sleep(0.00001)
                subprocess.run(["pinctrl", "set", str(self.SCL_GPIO), "dh"], check=True)
                time.sleep(0.00001)
            # Generate a STOP: SDA low, then SDA high while SCL is high
            subprocess.run(["pinctrl", "set", str(self.SDA_GPIO), "op", "dl"], check=True)
            time.sleep(0.00001)
            subprocess.run(["pinctrl", "set", str(self.SDA_GPIO), "dh"], check=True)
        except Exception as e:
            logging.error(f"I2C bus recovery failed: {e}")
        finally:
            # Hand the pins back to the I2C peripheral (ALT0 function)
            subprocess.run(["pinctrl", "set", str(self.SDA_GPIO), "a0"], check=True)
            subprocess.run(["pinctrl", "set", str(self.SCL_GPIO), "a0"], check=True)

    def _send_command(self, cmd: int) -> int:
        """Send I2C command and read single byte response, recovering the bus on failure"""
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                with SMBus(1) as bus:
                    bus.write_byte(self.address, cmd)
                    msg = i2c_msg.read(self.address, 1)
                    bus.i2c_rdwr(msg)
                    data = list(msg)
                    return data[0]
            except Exception as e:
                logging.error(f"I2C communication error (attempt {attempt}/{self.MAX_RETRIES}): {e}")
                self._recover_bus()
                time.sleep(0.05)
        return -1
    
    def read_voltage(self) -> float:
        """Read battery voltage from Arduino"""
        raw_voltage = self._send_command(I2CCommand.READ_VOLTAGE)
        return raw_voltage / Config.VOLTAGE_SCALE_FACTOR
    
    def arduino_button_pressed(self) -> bool:
        """Check if Arduino button is pressed (with debounce)"""
        button_pressed = False
        while self._send_command(I2CCommand.READ_BUTTON) == 1:
            button_pressed = True
            time.sleep(0.1)  # Debounce
        
        return button_pressed
    
    def shutdown(self) -> int:
        """Send shutdown command to Arduino"""
        return self._send_command(I2CCommand.SHUTDOWN)

class RTCController:
    """Handles DS3231 RTC configuration"""
    
    DS3231_STATUSREG = 0x0F
    EN32KHZ_BIT = 3
    
    def __init__(self):
        self.i2c_bus = board.I2C()
        self.rtc = adafruit_ds3231.DS3231(self.i2c_bus)
    
    def _disable_32khz_output(self):
        """Disable the 32kHz output pin on DS3231 to save power"""
        # Read current status register
        status = bytearray(1)
        self.rtc.i2c_device.write_then_readinto(
            bytes([self.DS3231_STATUSREG]), status
        )
        
        # Clear bit 3 (EN32kHz)
        status[0] &= ~(1 << self.EN32KHZ_BIT)
        
        # Write back
        self.rtc.i2c_device.write(bytes([self.DS3231_STATUSREG, status[0]]))
    
    def set_alarm(self, minutes: int):
        """Set RTC alarm to wake in specified minutes"""
        # Disable 32kHz output to save a lot of power
        self._disable_32khz_output()
        
        # Reset alarm status to clear any existing alarm flags
        self.rtc.alarm1_status = False
        
        # Set alarm for 'minutes' minutes from now
        now = time.mktime(self.rtc.datetime)
        alarm_time = time.localtime(now + minutes * 60)
        self.rtc.alarm1 = (alarm_time, "monthly")
        
        # Enable alarm interrupt mode (after alarm is configured)
        self.rtc.alarm1_interrupt = True
        logging.info(f"RTC alarm set for {minutes} minute(s) from now")

class ImageHandler:
    """Handles image fetching, processing, and display"""
    
    def __init__(self, inky_display):
        self.display = inky_display
    
    def fetch_image(self, voltage: float) -> Image.Image:
        """Fetch image from server"""
        response = requests.get(Config.IMAGE_URL + f"?v={voltage:.2f}")
        return Image.open(BytesIO(response.content))
    
    def add_voltage_warning(self, img: Image.Image, voltage: float) -> Image.Image:
        """Add low voltage warning overlay to image"""
        draw = ImageDraw.Draw(img)
        
        # Try to use a larger font, fall back to default if not available
        try:
            font = ImageFont.truetype(Config.WARNING_FONT_PATH, Config.WARNING_FONT_SIZE)
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
    
    def display_image(self, img: Image.Image, save_path: str = None):
        """Resize and display image on e-ink display"""
        if save_path:
            img.save(save_path)
        
        resized = img.resize(self.display.resolution)
        
        try:
            self.display.set_image(resized, saturation=Config.IMAGE_SATURATION)
        except TypeError:
            self.display.set_image(resized)
        
        self.display.show()

class NotificationService:
    """Handles system notifications"""
    
    @staticmethod
    def send_low_voltage_email(voltage: float):
        """Send email notification for low voltage using local mail"""
        try:
            subject = f"PiFrame Low Voltage Alert: {voltage:.2f}V"
            body = f"""Warning: PiFrame battery voltage is low!

Current Voltage: {voltage:.2f}V
Threshold: {Config.LOW_VOLTAGE_THRESHOLD}V

Please charge or replace the battery soon.
"""
            MAIL_CMD = "s-nail"
            # Send to current user - mail will deliver to local mailbox
            subprocess.run(
                [MAIL_CMD, "-s", subject, os.getenv("USER", "root")],
                input=body.encode(),
                check=True
            )
            
            logging.info("Low voltage email sent to local user mailbox")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to send email: {e}")
        except FileNotFoundError:
            logging.error(f"{MAIL_CMD} command not found.")

    @staticmethod
    def send_log_email(log_path: str):
        """Email the run log off-device before shutdown, then truncate it for the next run"""
        if not os.path.exists(log_path) or os.path.getsize(log_path) == 0:
            return
        try:
            # Flush/close file handlers so all buffered log lines are on disk before we read it
            for handler in logging.root.handlers:
                handler.flush()

            subject = "PiFrame run log"
            MAIL_CMD = "s-nail"
            subprocess.run(
                [MAIL_CMD, "-s", subject, "-a", log_path, os.getenv("USER", "root")],
                input=b"See attached log.\n",
                check=True,
            )
            logging.info("Run log emailed to local user mailbox")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to email log: {e}")
        except FileNotFoundError:
            logging.error(f"{MAIL_CMD} command not found.")
        finally:
            # Truncate so next run starts with a fresh log
            open(log_path, "w").close()

class PiFrameApp:
    """Main application controller"""
    
    def __init__(self):
        self.i2c = I2CController()
        self.rtc = RTCController()
        self.image_handler = ImageHandler(inky_auto())
        self.pi_button = Button(Config.PI_BUTTON_PIN)
        self.notifications = NotificationService()
    
    def check_and_display_image(self):
        """Fetch and display image with voltage warning if needed"""
        voltage = self.i2c.read_voltage()
        logging.info(f"Battery voltage: {voltage:.2f}V")
        
        img = self.image_handler.fetch_image(voltage)
        
        # Check for low voltage
        if voltage < Config.LOW_VOLTAGE_THRESHOLD:
            logging.warning(f"Low voltage detected ({voltage:.2f}V < {Config.LOW_VOLTAGE_THRESHOLD}V)")
            self.notifications.send_low_voltage_email(voltage)
            img = self.image_handler.add_voltage_warning(img, voltage)
        
        self.image_handler.display_image(img, os.path.join(SCRIPT_DIR, "image.jpg"))
    
    def wait_for_input(self) -> bool:
        """Wait for button input. Returns True if shutdown should proceed."""
        logging.info(f"Waiting {Config.WAIT_BEFORE_SHUTDOWN_SECONDS} seconds for input...")
        
        # Clear any button presses that occurred during display update
        self.i2c.arduino_button_pressed()
        
        start = time.time()
        
        while time.time() - start < Config.WAIT_BEFORE_SHUTDOWN_SECONDS:
            if self.pi_button.is_pressed:
                logging.info("Shutdown cancelled")
                return False
            
            if self.i2c.arduino_button_pressed():
                time.sleep(0.5)  # Allow I2C to fully close before restart
                logging.info("Arduino button pressed: restarting script")
                os.execv(sys.executable, [sys.executable, __file__])
                # Execution never reaches here
            
            time.sleep(0.1)
        
        return True
    
    def shutdown(self):
        """Prepare for shutdown and power off"""
        logging.info("No button press, shutting down")
        self.rtc.set_alarm(Config.PI_POWER_SLEEP_MINUTES)
        pi_state = self.i2c.shutdown()
        logging.info(f"I2C Shutdown command response: {pi_state}")
        # Get the log off-device before the Pi loses power
        self.notifications.send_log_email(LOG_PATH)
        subprocess.run(["sudo", "shutdown", "-h", "now"])
    
    def run(self):
        """Main application entry point"""
        try:
            self.check_and_display_image()
            
            if self.wait_for_input():
                self.shutdown()
        except Exception:
            logging.exception("Unhandled error during run")
            self.notifications.send_log_email(LOG_PATH)
            raise

def main():
    """Application entry point"""
    setup_logging()
    app = PiFrameApp()
    app.run()

if __name__ == "__main__":
    main()