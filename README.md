# PiFrame

Battery-powered color e-ink photo frame driven by a Raspberry Pi and an Arduino power controller.

Warning, below has been written by an LLM only lightly edited by me and may not be 100% correct.

## Table of Contents

- [Video and Build Image](#video-and-build-image)
- [What This Project Does](#what-this-project-does)
- [Hardware Architecture](#hardware-architecture)
- [Component List and Purchase Links](#component-list-and-purchase-links)
- [Software Components](#software-components)
- [I2C Protocol (Pi master -> Arduino slave `0x12`)](#i2c-protocol-pi-master----arduino-slave-0x12)
- [Pi App Behavior](#pi-app-behavior)
- [Image Server Behavior](#image-server-behavior)
- [Setup Guide](#setup-guide)
- [Known Issues and Practical Notes](#known-issues-and-practical-notes)
- [Safety and Power Notes](#safety-and-power-notes)
- [Verification Checklist](#verification-checklist)

## Video and Build Image

- YouTube video: https://www.youtube.com/watch?v=AknCTQES6c4

![PiFrame Circuit Photo](Images/Circuit/CircuitPhoto.png)

![PiFrame Circuit Sketch](Images/Circuit/CircuitSketch.svg)

## What This Project Does

PiFrame updates a 4:3 image on an e-ink screen, then shuts the Raspberry Pi fully off to save power. An Arduino Pro Mini stays alive, watches a button/RTC interrupt, and switches Pi power back on when needed.

High-level behavior:

1. Arduino powers Pi on.
2. Pi runs [Python/imagesd.py](Python/imagesd.py), requests one image from a local CGI endpoint, and renders it to the e-ink display.
3. Pi waits for user input for 45 seconds.
4. If no cancel input is received, Pi sets an RTC alarm and requests shutdown.
5. Arduino receives shutdown request over I2C, waits 10 seconds, then cuts Pi power.
6. RTC alarm (or manual button press) wakes the system for the next update.

## Hardware Architecture

### Core parts

- Raspberry Pi (the transcript notes moving away from original Pi Zero due to boot time; Pi Zero 2 class is more practical).
- Arduino Pro Mini (3.3V variant expected by current voltage logic).
- Pimoroni Inky color display (transcript references 13.3-inch color e-ink panel).
- DS3231 RTC module (alarm interrupt wake).
- LiPo battery pack powering the whole frame.
- DC-DC converter to Pi 5V rail.
- High-side switching stage using one N-channel and one P-channel MOSFET.
- Voltage divider into Arduino A0 for battery telemetry.
- Button on frame side (plus optional duplicate button in parallel).
- I2C buffer/isolator (mentioned in transcript as part of bus-stability work).

### Signals used by current firmware

From [fullFrame/fullFrame.ino](fullFrame/fullFrame.ino):

- `D7`: Pi power switch control.
- `D3`: user button interrupt.
- `D2`: RTC interrupt input.
- `A0`: battery voltage ADC.
- I2C slave address: `0x12`.

From [Python/imagesd.py](Python/imagesd.py):

- Pi local button: GPIO 5 via `gpiozero.Button`.
- I2C bus `1` for Arduino (`0x12`) and DS3231 (`0x68`).

## Component List and Purchase Links

Where possible I've linked to the actual items I bought, but Pis seem to be expensive/hard to come by at the moment.

### Core Electronics

- Inky Impression 13" Colour e-Ink Screen: [Product page](https://shop.pimoroni.com/products/inky-impression?variant=55186435277179)
- Raspberry Pi Zero 2 W: [Listing](https://amzn.to/4vAQTbX)
- SanDisk Micro SD Card: [Listing](https://www.ebay.co.uk/itm/286984118600?var=589027763072&mkcid=1&mkrid=710-53481-19255-0&siteid=3&campid=5339149883&customid=&toolid=10001&mkevt=1)
- Arduino Pro Mini 3.3V: [Listing](https://www.ebay.co.uk/itm/305210446733?amdata=enc%3AAQALAAAAoGfYFPkwiKCW4ZNSs2u11xC4nr3QEtbYIPgSo109z3%2F99pj%2F78aagCKRMMDPo47ZgEDSY%2B9l6Myd%2BPsWHjZGPAq7Iu6FWSLnkMMgMS%2B5Rv%2BcjZxPDu5CrwdKwdmrCoYc6iskB3QD%2BlzFHN0LnBJtQLctfqp5VjuYQen2Xhh4plgIRprMRl%2Bz52B1KMeDSCfuauFmnXumVCvIy7GkCO%2Bp5sc%3D&mkcid=1&mkrid=710-53481-19255-0&siteid=3&campid=5339149883&customid=&toolid=10001&mkevt=1)
- USB Programming Board FT232RL FTDI Module 5V/3.3V: [Listing](https://www.ebay.co.uk/itm/127377038303?var=428474503338&amdata=enc%3AAQALAAAAoGfYFPkwiKCW4ZNSs2u11xBeSO3v0zUO%2BkLxqV0lq9NPYpgPaomHOi167GZbA6h3SGMtwCM6Emi2WzsqI2%2BCKljP5%2F3OVNVMRJibYeaWQd2af5qs9iTyPsyKcGCBPWvaf8L%2BuUKsm%2FwsENku5w11dbEUp%2Fq3m%2BljCKpyuzrMRJ8ThV0trX1fTHbDHikX4kxdPCr%2FfYMPw2%2B2lGeUdlXpCHU%3D&mkcid=1&mkrid=710-53481-19255-0&siteid=3&campid=5339149883&customid=&toolid=10001&mkevt=1)
- RTC DS3231 Real Time Clock: [Listing](https://www.ebay.co.uk/itm/155491320233?var=455730810590&amdata=enc%3AAQALAAAAoGfYFPkwiKCW4ZNSs2u11xDCbSprMC6s1bo3FYyfD0UZR0BDyHkcoCx8oRQfG0LA6YavVKyJyndnl3l%2F7IfuT%2FKf3mQMgt75M0F20lJvE2rJiGv76afqXj%2BsAOc%2F4Wc68lXj2y94BXnM%2Bi8a%2B1LQEdQX7N1tl7wlAeHdg0kg7giPhWAN3wvuBzuHXcWlg%2BpHIk%2FMRCsBZbJpk10w%2FjBbX2M%3D&mkcid=1&mkrid=710-53481-19255-0&siteid=3&campid=5339149883&customid=&toolid=10001&mkevt=1)
  - I forgot to mention that I removed the battery cell and contacts, and replaced the right-angle pins with straight.

### Power and Switching

- IRF9540N P-Channel MOSFET: [Listing](https://www.ebay.co.uk/itm/155878954226?amdata=enc%3AAQALAAAAoGfYFPkwiKCW4ZNSs2u11xCep1Enb%2B0LVTzZ1DnGT79usCtSbpo1aUQ4M1lIIrjJQbsIGD7h9EohXPRyQW219kLfZM9gSF5BQNnlct6YBC%2FQHBUUtaV9bV1mMzhcLyqkYeFlG%2FK9PjTBiO5N8vG4SQWuKpgm%2FU9s3RCj4kRkOKEFu7IGL0TSDAeEWzQKsbdSfHCyeKccbBvG%2FomOF4o3dIw%3D&mkcid=1&mkrid=710-53481-19255-0&siteid=3&campid=5339149883&customid=&toolid=10001&mkevt=1)
- FQP30N06L N-Channel MOSFET: [Listing](https://www.ebay.co.uk/itm/365657913471?amdata=enc%3AAQALAAAAoGfYFPkwiKCW4ZNSs2u11xCHPlOEgLx0V5dto7WHQ4Z2S%2FsVeTNSD%2FaSBYLbKvH30K0rK03Vcrj0qk53XBtrHzZqjB3OkDKc%2B8VZCBro6CLOfCJF0%2BzzJgAPjoJ8K9vIuZAVTzbp2xAgaVkIJ4EZyZhQKCBH8AErrf6WFDRcuppp47LPpnfnjthuxXgITR3fEnspouW%2FKXQLC9veFnHWwvA%3D&mkcid=1&mkrid=710-53481-19255-0&siteid=3&campid=5339149883&customid=&toolid=10001&mkevt=1)
- Step Down Voltage Regulator 5v~24v to 1.8v/3.3v/12v 3A: [Listing](https://www.ebay.co.uk/itm/335700668123?mkcid=1&mkrid=710-53481-19255-0&siteid=3&campid=5339149883&customid=&toolid=10001&mkevt=1)
  - Note that adjustment is very sensitive and can be jogged; ended up soldering to fixed 5V rather than manually setting 5.2V.
- MCP1702-3302E/TO IC REGULATOR LINEAR 3.3V 250MA TO92-3: [Listing](https://www.ebay.co.uk/itm/156363523627?mkcid=1&mkrid=710-53481-19255-0&siteid=3&campid=5339149883&customid=&toolid=10001&mkevt=1)
  - A good option for higher voltages.
- MCP1700-3302E LDO Voltage Regulator 3.3V 250mA TO-92: [Listing](https://www.ebay.co.uk/itm/234899648343?mkcid=1&mkrid=710-53481-19255-0&siteid=3&campid=5339149883&customid=&toolid=10001&mkevt=1)
  - Another option for lower voltages, with slightly lower quiescent current.
- MT3608 DC-DC Voltage Step-Up Adjustable Converter Module 1A: [Listing](https://www.ebay.co.uk/itm/174123815317?var=473007178646&mkcid=1&mkrid=710-53481-19255-0&siteid=3&campid=5339149883&customid=&toolid=10001&mkevt=1)
  - This was my original failed step-up option.

### Interconnects, Controls, and General Parts

- Pack of resistors: [Listing](https://www.ebay.co.uk/itm/235925598928?mkcid=1&mkrid=710-53481-19255-0&siteid=3&campid=5339149883&customid=&toolid=10001&mkevt=1)
- Solder: [Listing](https://www.ebay.co.uk/itm/363938676112?mkcid=1&mkrid=710-53481-19255-0&siteid=3&campid=5339149883&customid=&toolid=10001&mkevt=1)
- Single Row Male Breakable Pin Header Connector Strip: [Listing](https://www.ebay.co.uk/itm/203585637263?amdata=enc%3AAQALAAAAoGfYFPkwiKCW4ZNSs2u11xDCRthPzNSBgSiNEhjaSJAQRhHUPV%2By7nfXfxB4gbhkAZTc9pU%2BQOZjGvQ%2FzpKYra3bjP9rMuGjSd6MAl%2ByqhrAi7nbyqBtb2AIqCRJTT1RgS%2FMr4jSn0CAxuf%2FbcdhF--M%2FRGFFZ2WqW%2Bp895gt1bMS37COx8Qn1THZ%2FlCsuwlNz4GdrjWI%2FxAjV8GkPIOTfo%3D&mkcid=1&mkrid=710-53481-19255-0&siteid=3&campid=5339149883&customid=&toolid=10001&mkevt=1)
  - Very handy for various uses.
- On-On Mini PCB Slide Switch SPDT 5A: [Listing](https://www.ebay.co.uk/itm/265245651666?amdata=enc%3AAQALAAAAoGfYFPkwiKCW4ZNSs2u11xCaz85n%2FaMX3F4P63CyuQOG9xXAGG%2FFxtXiB0tEXhK0Mcg%2BQi%2FZ0RFaOPRHr1EKSUG2cWFcFwEYEsOyQ34ZarbVufYTUYW455VCjKHAR3XqGmLQazy3t%2BqkNHeKPXP5a0PeodpMBA8QBrBJKHHJlxGow%2Be6Pa%2FBIU%2FZQoqpiz%2FROVjvwWFnndkAhrTyz%2BY%2BZA0%3D&mkcid=1&mkrid=710-53481-19255-0&siteid=3&campid=5339149883&customid=&toolid=10001&mkevt=1)
  - A little too big for normal PCB/breadboard, and 5A is likely overkill.
- Nive Red Buttons: [Listing](https://www.ebay.co.uk/itm/389373230382?var=656697025919&amdata=enc%3AAQALAAAAoGfYFPkwiKCW4ZNSs2u11xC8mc5GQBEv5gOB2AAOv6oAF9Gntwk4cyBeMKzea%2BhyL7L6fDxnIs0f8uBRJOLDXF1u1XNo4BECa4f4evzoG%2BRxFinNJ7K%2B9jH4oUR4at90mhw1lEJiErKOaNILjvUZwMvmvfi0G1ZrMKQTk--q7VrFjfhvyi%2FbFSPSe3G2MTF2Cvi3KBl6SHhkH6qe%2BIxUjus%3D&mkcid=1&mkrid=710-53481-19255-0&siteid=3&campid=5339149883&customid=&toolid=10001&mkevt=1)
  - These took a long time to ship (from China).
- USB Type A Right Angle Socket: [Listing](https://www.ebay.co.uk/itm/255670818538?amdata=enc%3AAQALAAAAoGfYFPkwiKCW4ZNSs2u11xBXo8ag%2BywvzVt6qBu0xyGwm35V8WS4DfRbeS%2B5W8KtB5Vitw5CWHtI6xnyk1MxUzUF%2BisPEyOlxZwNxxwO49mzoErVW1O7YCWgr%2B27K%2FB2mhRitawscAR5xvIieFyhkwR0wlPnIVfxyB16pXI7TbmGDqz7tNP%2FECRLf3hkDNWVXPBW6Uc9PWkwahnQ2PZZF3Y%3D&mkcid=1&mkrid=710-53481-19255-0&siteid=3&campid=5339149883&customid=&toolid=10001&mkevt=1)
- Solderless Prototype Breadboard: [Listing](https://amzn.to/4myC6L3)
- ElectroCookie Solderable Breadboard: [Listing](https://amzn.to/4cBqLoZ)
- Colored 9 Meter Spools 22 Gauge Jumper Wire: [Listing](https://amzn.to/4cwGjdt)
- Balsa Wood Bundle: [Listing](https://www.ebay.co.uk/itm/277512476279?mkcid=1&mkrid=710-53481-19255-0&siteid=3&campid=5339149883&customid=&toolid=10001&mkevt=1)
  - For mounting
- Ikea picture frame: [Product range](https://www.ikea.com/gb/en/cat/roedalm-series-700545/)

### I2C Bus Options

- PCA9515A I2C Buffer / Repeater: [Listing](https://www.ebay.co.uk/itm/317770823716?mkcid=1&mkrid=710-53481-19255-0&siteid=3&campid=5339149883&customid=&toolid=10001&mkevt=1)
- Texas 74HC4066 Quad SPST Analog Switch SOIC-14 (alternative option): [Listing](https://www.ebay.co.uk/itm/185962448952?mkcid=1&mkrid=710-53481-19255-0&siteid=3&campid=5339149883&customid=&toolid=10001&mkevt=1)

### Optional Battery Meters

- Mini LED Battery Meter: [Listing](https://www.ebay.co.uk/itm/177016305844?mkcid=1&mkrid=710-53481-19255-0&siteid=3&campid=5339149883&customid=&toolid=10001&mkevt=1)
  - I had real problems creating a voltage divider for this; likely better to use one matched to your battery (for example, 2-cell LiPo).
- LED 2S Battery Meter: [Listing](https://www.ebay.co.uk/itm/336375640422?amdata=enc%3AAQALAAAAoGfYFPkwiKCW4ZNSs2u11xDP6LchFftfnhtO%2F5xMTtVDCR1nRD2W4w5Aen53KkhmaIAJsKhg3AFE1nceorJYLRMCG1CmdgWNAOiSjydbOoeCpUrcePngKlE57GWJuPNUWcGy%2FPnJLw9Bl3PllEcR835XvERjDuTKdBfzhqFQ%2B8xRfbndd7fRTz7yfrIjYpcNLfCzOxLIok%2BW19GzQn5laPw%3D&mkcid=1&mkrid=710-53481-19255-0&siteid=3&campid=5339149883&customid=&toolid=10001&mkevt=1)
  - I have no direct experienceof this, but it's likely a better fit.

## Software Components

### Main runtime files

- [fullFrame/fullFrame.ino](fullFrame/fullFrame.ino): production Arduino firmware (power switching, sleep, I2C slave protocol, button/RTC interrupts).
- [Python/imagesd.py](Python/imagesd.py): production Pi app (fetch image, display, low-battery warning, RTC alarm setup, controlled shutdown).
- [Python/pics3.cgi](Python/pics3.cgi): image server script (random selection, avoids immediate repeats, portrait handling, blur-fill to 4:3, JPEG response).
- [Python/piframe.service](Python/piframe.service): systemd unit that waits for network readiness, then runs git pull before launching the Python app.

### Supporting/legacy files

- [SleepTimer/SleepTimer.ino](SleepTimer/SleepTimer.ino): RTC sleep/wake experiment sketch.
- [Voltage/Voltage.ino](Voltage/Voltage.ino): battery measurement test sketch.

## I2C Protocol (Pi master -> Arduino slave `0x12`)

Defined by [fullFrame/fullFrame.ino](fullFrame/fullFrame.ino) and consumed in [Python/imagesd.py](Python/imagesd.py):

- `0x01` read: button event (1 once, then cleared).
- `0x02` read: battery voltage encoded as one byte where `volts = raw / 25.0`.
- `0x10` write: Pi is shutting down (Arduino enters delayed power-off state).
- `0x11` write: cancel shutdown (implemented in Arduino).

Arduino LED states:

- Off: Pi power off.
- Solid on: Pi power on.
- 2 Hz blink: shutdown pending.

## Pi App Behavior

Current defaults in [Python/imagesd.py](Python/imagesd.py):

- Image endpoint: `http://192.168.1.4/py/pics3.cgi`.
- Wait before shutdown: `45` seconds.
- Sleep interval before next RTC wake: `24 * 60` minutes (24 hours).
- Low battery threshold: `6.75V`.
- Display saturation: `0.5`.

Flow:

1. Read voltage from Arduino over I2C.
2. Fetch one image from CGI endpoint (`?v=<voltage>` appended).
3. If low voltage, send local email via `s-nail` and overlay warning text on the image.
4. Display image on Inky panel.
5. During wait window:
   - Pi GPIO button cancels shutdown.
   - Arduino button triggers immediate script restart (new image).
6. On timeout:
   - Disable DS3231 32kHz output bit.
   - Program DS3231 alarm.
   - Send shutdown command to Arduino.
   - Run `sudo shutdown -h now`.

## Image Server Behavior

The CGI script [Python/pics3.cgi](Python/pics3.cgi):

- Reads source images from `/srv/http/192.168.1.4/resized/`.
- Picks a random image but avoids repeating the most recently logged filename.
- Logs timestamp, filename, and incoming voltage query value to `log.log`.
- Processing:
  - Portrait image: center-crop to square first.
  - If narrower than 4:3: generates blurred side fill.
  - Else: center-crops to exact 4:3.
  - Resizes output to `1600x1200` JPEG.

## Setup Guide

### 1) Arduino firmware

1. Open [fullFrame/fullFrame.ino](fullFrame/fullFrame.ino) in Arduino IDE.
2. Board settings from [.vscode/arduino.json](.vscode/arduino.json):
   - Board: `arduino:avr:pro`
   - CPU: `16MHzatmega328`
3. Install required library:
   - `LowPower` (Rocket Scream variant).
4. Upload firmware to Pro Mini using your USB-serial programmer.

Note: the transcript indicates power-saving hardware mods (removing board LEDs/regulator) were used; those are optional but materially affect standby current.

### 2) Raspberry Pi dependencies

Install system and Python packages needed by [Python/imagesd.py](Python/imagesd.py):

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-pil python3-smbus i2c-tools s-nail
pip3 install requests pillow gpiozero smbus2 adafruit-circuitpython-ds3231 inky
```

Enable I2C in `raspi-config`, then reboot.

### 3) Deploy Pi runtime

1. Copy repository to Pi (expected by service as `/home/jamie/PiFrame`).
2. Ensure [Python/imagesd.py](Python/imagesd.py) is executable.
3. Install service file [Python/piframe.service](Python/piframe.service) to `/etc/systemd/system/piframe.service`.
4. Edit service paths/user for your machine.
5. Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable piframe.service
sudo systemctl start piframe.service
```

Service behavior in this repo:

- It blocks startup until internet is reachable (ping checks in `ExecStartPre`).
- On each run, it changes into the repo, runs `git pull`, activates the virtualenv, then runs [Python/imagesd.py](Python/imagesd.py).
- Practical workflow: you can commit and push updates while the frame is off; at the next wake/update cycle, the service pulls latest changes automatically. You do not need to modify files with the frame powered on.

### 4) Configure image endpoint

If using the included CGI script:

1. Deploy [Python/pics3.cgi](Python/pics3.cgi) to your web server CGI path.
2. Update `IMAGE_FOLDER` to your photo directory.
3. Ensure script has execute permission and PIL/Pillow available on host.
4. Update `Config.IMAGE_URL` in [Python/imagesd.py](Python/imagesd.py).

## Known Issues and Practical Notes

- I2C lockups can still occur (explicitly described in the transcript); a hard power rail break/reset jumper is useful for recovery.
- E-ink color quality is image-dependent; photos with strong contrast and limited color palettes look best.
- Acrylic/gloss front layers can reduce apparent saturation; transcript notes improved perceived quality after removing acrylic.
- Boot time significantly impacts user experience and total energy per update cycle; faster Pi models improve both.

## Safety and Power Notes

- Battery chemistry and charge/discharge safety are your responsibility.
- Validate converter thermal behavior and inrush margins during e-ink refresh.
- The project measures voltage but does not implement a full BMS in software.

## Verification Checklist

After wiring and flashing:

1. Arduino LED on solid after power-up.
2. `i2cdetect -y 1` on Pi shows `0x12` and `0x68` when powered.
3. Running [Python/imagesd.py](Python/imagesd.py) updates display and logs a voltage-tagged request at CGI host.
4. After timeout, Pi halts and Arduino cuts power after delay.
5. RTC alarm or side button wakes and repeats cycle.
