# PiFrame - Battery-Powered E-Ink Photo Frame

A low-power digital photo frame using a Raspberry Pi Zero, Arduino power management, e-ink display, and RTC-based sleep scheduling.

Warning, below has been written by an LLM only lightly edited by me and may not be 100% correct.

## Table of Contents

- [Features](#features)
- [Hardware Requirements](#hardware-requirements)
- [System Architecture](#system-architecture)
- [Hardware Setup](#hardware-setup)
- [Software Installation](#software-installation)
- [Configuration](#configuration)
- [Operation](#operation)
- [I2C Communication Protocol](#i2c-communication-protocol)
- [Power Management](#power-management)
- [Troubleshooting](#troubleshooting)

## Features

- Low power consumption with sleep/wake cycles
- E-ink display for minimal power draw
- Battery voltage monitoring with warnings
- RTC-based automatic wake-up
- Arduino controls Pi power completely
- Button controls for manual operation
- Fetches images from network server
- Shows voltage warning overlay when battery is low

## Hardware Requirements

### Core Components

- Raspberry Pi Zero W (or Zero 2 W)
- Arduino Pro Mini (3.3V, 8MHz) or similar
- Inky wHAT/Impression e-ink display (Pimoroni)
- DS3231 RTC module with alarm capability
- LiPo battery (2S, 7.4V nominal)

### Additional Components

- 5V boost converter for Pi
- 3.3V regulator for Arduino
- PCA9515A I2C buffer/isolator module
- Voltage divider: 20kΩ + 10kΩ resistors for battery monitoring
- N-channel MOSFET (logic level)
- P-channel MOSFET for high-side switching
- Push button (momentary switch)

### Wiring Diagram

```
LiPo Battery (7.4V)
    ├─→ Arduino A0 (via voltage divider: 20kΩ / 10kΩ)
    ├─→ P-MOSFET Source
    └─→ 3.3V Regulator → Arduino VCC

Pi Power Control:
    Arduino D7 → N-MOSFET Gate
    N-MOSFET Drain → P-MOSFET Gate
    P-MOSFET Source → Battery+
    P-MOSFET Drain → 5V Boost Converter → Pi 5V

Buttons:
    Arduino D3 → Push Button → GND
    Arduino D2 → DS3231 SQW/INT (RTC alarm)

I2C Bus (via PCA9515A buffer):
    Side 0 (Pi):
        Pi 3.3V ────────────→ PCA9515A VCC_0
        Pi GPIO 2 (SDA) ────→ PCA9515A SDA_0
        Pi GPIO 3 (SCL) ────→ PCA9515A SCL_0
    
    Side 1 (Arduino + RTC):
        Arduino A4 (SDA) ───→ PCA9515A SDA_1
        Arduino A5 (SCL) ───→ PCA9515A SCL_1
        DS3231 SDA ─────────→ PCA9515A SDA_1
        DS3231 SCL ─────────→ PCA9515A SCL_1
    
    Enable Control:
        Pi 3.3V ────────────→ PCA9515A EN (auto-disable when Pi is off)
        (VCC_1 not connected)

Pi GPIO 5 → Inky Impression Top Button → GND
Pi GPIO (SPI) → Inky Display

GND ────────────────────────→ PCA9515A GND
```

## System Architecture

### Component Responsibilities

**Arduino (Power Manager)**
- Controls Pi power via dual MOSFET circuit
- Sleeps in low power mode when Pi is off
- Monitors battery voltage
- I2C slave device at address 0x12

**Raspberry Pi (Image Processor)**
- Fetches images from network server
- Displays images on e-ink screen
- Configures RTC alarms
- Monitors battery via I2C
- Sends shutdown commands to Arduino

**DS3231 RTC (Timer)**
- Maintains time during deep sleep
- Triggers wake-up via alarm interrupt

**PCA9515A I2C Buffer**
- Isolates I2C bus between Pi and Arduino/RTC
- Automatically disabled when Pi is off (EN tied to Pi 3.3V)
- Reduces power consumption in deep sleep

**E-ink Display**
- No power draw when static
- Updates only when new image is displayed

### Power States

1. **Active**: Pi on, displaying image (~500mA)
2. **Waiting**: Pi on, waiting for input (<200mA)
3. **Deep Sleep**: Pi off, Arduino sleeping (<100µA)
4. **Wake**: Arduino wakes, powers on Pi (10 seconds)

## Hardware Setup

### 1. Voltage Divider for Battery Monitoring

```
Battery+ ─┬─ 20kΩ ─┬─ Arduino A0
          │        │
          │       10kΩ
          │        │
Battery- ─┴────────┴─ GND
```

This divides 7.4V battery to ~2.5V for Arduino ADC.

### 2. Pi Power Control Circuit

```
Battery+ ──→ P-MOSFET Source
            │
            Gate ←─── N-MOSFET Drain
            │              │
            Drain ──→ 5V Boost Converter → Pi 5V
                           
Arduino D7 ──→ N-MOSFET Gate
               │
               Source ──→ GND
```

When Arduino D7 is HIGH:
- N-MOSFET turns ON
- Pulls P-MOSFET gate to ground
- P-MOSFET turns ON
- Power flows to Pi

### 3. I2C Buffer (PCA9515A)

```
Pi 3.3V ──┬───→ PCA9515A VCC_0
          └───→ PCA9515A EN (auto-disable when Pi off)

Side 0 (Pi):
    Pi GPIO 2 (SDA) ────→ PCA9515A SDA_0
    Pi GPIO 3 (SCL) ────→ PCA9515A SCL_0

Side 1 (Arduino + RTC):
    Arduino A4 (SDA) ───→ PCA9515A SDA_1
    Arduino A5 (SCL) ───→ PCA9515A SCL_1
    DS3231 SDA ─────────→ PCA9515A SDA_1
    DS3231 SCL ─────────→ PCA9515A SCL_1

GND ────────────────────→ PCA9515A GND

Note: VCC_1 is left disconnected
```

The PCA9515A provides:
- Buffering between Arduino/RTC and Pi I2C buses
- Built-in pull-ups (no external resistors needed)
- Bus isolation
- Rise-time acceleration
- **Automatic disable when Pi is off** - EN pin tied to Pi 3.3V means the buffer powers down completely when the Pi shuts off, eliminating any leakage current through the I2C bus

### 4. Button Connections

```
3.3V ──┬─ Internal Pull-up ─── Arduino D3 ─── Button ─── GND
       │
       └─ Internal Pull-up ─── Pi GPIO 5 (top Inky Impression button) ─── GND
```

## Software Installation

### Raspberry Pi Setup

1. Flash Raspberry Pi OS Lite with SSH and WiFi enabled

2. Update system:
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

3. Install dependencies:
   ```bash
   sudo apt install -y python3-pip python3-pil python3-numpy \
                       python3-smbus python3-rpi.gpio i2c-tools \
                       s-nail
   
   pip3 install inky requests gpiozero adafruit-circuitpython-ds3231 \
                smbus2 pillow
   ```

4. Enable I2C:
   ```bash
   sudo raspi-config
   # Interface Options → I2C → Enable
   sudo reboot
   ```

5. Verify I2C devices:
   ```bash
   sudo i2cdetect -y 1
   # Should show 0x12 (Arduino) and 0x68 (DS3231)
   ```

6. Copy Python script to Pi:
   ```bash
   mkdir -p ~/PiFrame/Python
   # Copy imagesd.py to this directory
   ```

7. Set up auto-start:
   ```bash
   sudo nano /etc/rc.local
   # Add before "exit 0":
   sudo -u pi python3 /home/pi/PiFrame/Python/imagesd.py &
   ```

### Arduino Setup

1. Install Arduino IDE and LowPower library (Rocket Scream)

2. Configure board:
   - Board: Arduino Pro or Pro Mini
   - Processor: ATmega328P (3.3V, 8MHz)

3. Upload fullFrame.ino

4. Verify I2C address is 0x12

## Configuration

### Python Configuration

Edit `Python/imagesd.py`:

```python
@dataclass
class Config:
    IMAGE_URL: str = "http://192.168.1.4/py/pics3.cgi"  # Your image server
    BUTTON_PIN: int = 5                                   # Pi button GPIO
    WAIT_SECONDS: int = 45                                # Wait before shutdown
    SLEEP_MINUTES: int = 5                                # Sleep duration
    LOW_VOLTAGE_THRESHOLD: float = 6.75                   # Low battery warning
    SATURATION: float = 0.5                               # E-ink color saturation
```

### Arduino Configuration

Edit `fullFrame/fullFrame.ino`:

```cpp
namespace Config {
    constexpr uint8_t I2C_ADDRESS = 0x12;               // I2C slave address
    constexpr uint8_t DEFAULT_SHUTDOWN_DELAY_SECS = 10; // Shutdown delay
    constexpr float VOLTAGE_DIVIDER_R1 = 20000.0f;      // Top resistor (Ω)
    constexpr float VOLTAGE_DIVIDER_R2 = 10000.0f;      // Bottom resistor (Ω)
}
```

### Image Server

The Pi fetches images from a web server. The server should accept GET requests with a voltage parameter and return an image:

```
GET http://your-server/pics3.cgi?v=7.85
```

Example PHP implementation:
```php
<?php
$voltage = $_GET['v'] ?? '0.00';
$images = glob('images/*.jpg');
$image = $images[array_rand($images)];

file_put_contents('voltage.log', date('Y-m-d H:i:s') . " - $voltage V\n", FILE_APPEND);

header('Content-Type: image/jpeg');
readfile($image);
?>
```

## Operation

### Normal Operation Cycle

1. RTC alarm wakes Arduino
2. Arduino powers on Pi
3. Pi boots (2:30 minutes)
4. Pi fetches image from server
5. Image displayed on e-ink screen
6. System waits 45 seconds for button press
7. If no button pressed, Pi commands Arduino to shutdown
8. Arduino cuts Pi power, sets RTC alarm, enters deep sleep
9. PCA9515A buffer automatically disables (EN goes low with Pi 3.3V)
10. Cycle repeats after sleep period

### Manual Controls

**Arduino Button (D3)**:
- When Pi is off: Powers on Pi
- When Pi is on: Restarts script (fetch new image)

**Inky Impression Top Button (GPIO 5)**:
- During wait period: Cancels shutdown (keeps Pi running)

### LED Indicator

Arduino built-in LED:
- Off: Pi powered off (deep sleep)
- On (solid): Pi powered on
- Blinking: Shutdown pending (countdown)

## I2C Communication Protocol

Arduino is I2C slave at address 0x12.

### Commands

| Command | Value | Type | Description |
|---------|-------|------|-------------|
| READ_BUTTON | 0x01 | Read | Returns 1 if button pressed, 0 otherwise |
| READ_VOLTAGE | 0x02 | Read | Returns voltage × 25 (0-255) |
| CANCEL_SHUTDOWN | 0x00 | Write | Cancels pending shutdown |
| SHUTDOWN | 0x03-0xFF | Write | Shutdown with N second delay |

### Python Examples

```python
i2c = I2CController()

# Read voltage
voltage = i2c.read_voltage()  # Returns float, e.g., 7.85

# Check button
if i2c.is_button_pressed():
    print("Button pressed")

# Shutdown in 15 seconds
i2c.shutdown(delay_seconds=15)

# Cancel shutdown
i2c.cancel_shutdown()
```

## Power Management

### Current Consumption

| State | Current | Duration |
|-------|---------|----------|
| Deep Sleep | ~0.1mA | 5 min |
| Boot | ~510mA | 30s |
| Display Update | ~510mA | 5s |
| Waiting | ~210mA | 45s |
| Shutdown | ~210mA | 10s |

### Battery Life

With 2S LiPo (7.4V, 2000mAh):
- Deep sleep: 24 hours @ 0.08mA ~ 2 mAh
- Wake cycle: 3 min @ 200mA avg = 10 mAh
- Total per day: ~12 mAh
- Battery life: ~100 days

Adjust `SLEEP_MINUTES` to extend battery life.

### Low Voltage Protection

When voltage drops below threshold (default 6.75V):
- Warning overlay added to image
- Email sent to local mailbox
- Voltage logged to server

## Troubleshooting

### Pi Won't Boot

Check:
- 5V regulator output voltage
- MOSFET wiring (D7 HIGH should turn on Pi)
- Battery voltage
- SD card is inserted properly

### I2C Communication Fails

```bash
sudo i2cdetect -y 1
# Should show 0x12 (Arduino) and 0x68 (RTC)
```

Check:
- PCA9515A power (VCC_0 at 3.3V from Pi)
- EN pin has voltage when Pi is on
- SDA/SCL connections on both sides of buffer
- Arduino is powered
- I2C address matches

### Display Not Updating

Check:
- SPI connections to display
- Display power (3.3V)
- Python logs for errors

### Arduino Not Waking

Check:
- RTC alarm is set
- RTC battery
- INT pin connection (D2)
- Test with manual button

### Battery Drains Quickly

Check:
- Pi is actually shutting down
- Arduino enters deep sleep
- Measure current draw
- Increase `SLEEP_MINUTES`
- Verify PCA9515A is disabling (EN should go to 0V when Pi is off)

### Email Notifications Not Working

```bash
# Test mail
echo "Test" | s-nail -s "Test" $USER

# Check mail
mail
```

### I2C Buffer Issues

If devices aren't visible on `i2cdetect`:
- Verify PCA9515A VCC_0 has 3.3V from Pi
- Check EN pin is high when Pi is running
- Verify VCC_1 is disconnected (not used)
- Check all ground connections
- Ensure buffer is oriented correctly (Pi on side 0, Arduino/RTC on side 1)
- Try connecting devices directly (temporarily) to isolate issue

Note: The buffer will only work when the Pi is powered on, as EN is tied to Pi 3.3V.

## License

[Your license here]

## Credits

- Inky library: Pimoroni
- LowPower library: Rocket Scream
- DS3231 library: Adafruit