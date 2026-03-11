# Voucher Scanner

A Python barcode/QR scanner with automatic gift card detection and browser automation for REWE, DM, ALDI, LIDL, EDEKA.

---

## Features

- **Live & Picture barcode scanning** with automatic detection
- **Three camera modes**: Laptop webcam, IP phone camera (WiFi), or USB phone camera
- **Automatic shop detection** by card number format
- **Fast form filling**: DM instant, ALDI/EDEKA automated, REWE/LIDL manual
- **Multi-window layout**: Scanner left, Selenium browser middle, manual browser right
- **Anti-bot measures** for reliable automation

---

## Shops

| Shop | Digits | Method |
|------|--------|--------|
| REWE | 13 | Manual (slow Friendly Captcha) |
| DM | 24 | Auto (super fast) |
| ALDI | 20 | Manual select |
| LIDL | 20 | Manual select |

( EDEKA - deactivated - needs to be uncommented in code)

**ALDI & LIDL same format** → manually select after scan.

---

## Installation

You need **Python** installed on your computer. The easiest way to manage Python on Linux/Mac is with **Conda** (recommended), but a plain Python virtual environment works too. If you are not sure which to use, follow the Conda path.

### Option A — Conda (recommended)

If you don't have Conda yet, download Miniconda from https://docs.conda.io/en/latest/miniconda.html and follow the installer.

```bash
conda env create -f environment.yml
conda activate voucher-scanner
```

### Option B — pip with virtual environment

A virtual environment keeps the app's dependencies separate from the rest of your system. It is optional but strongly recommended — without it, packages install globally and may conflict with other Python apps.

```bash
python3 -m venv venv
source venv/bin/activate        # on Linux/Mac
# venv\Scripts\activate         # on Windows
pip install -r requirements.txt
```

### Option C — pip without virtual environment (simplest, not recommended)

Only do this if you just want to try the app quickly and don't mind installing packages globally:

```bash
pip install -r requirements.txt
```

---

## Camera Setup

The app supports three camera modes. Choose one — you do not need all three.

### Mode 1 — Laptop / built-in webcam (simplest, no extra setup)

No installation needed. Just select "Internal Laptop Camera" when the app starts.
Resolution is usually limited to 720p or 1080p depending on your hardware.

### Mode 2 — Phone camera over WiFi (IP Webcam)

Good balance of quality and simplicity. Phone and laptop must be on the same WiFi network.

1. Install the **IP Webcam** app on your Android phone (free on Play Store)
2. Open the app and tap **Start server**
3. Note the IP address shown on screen (e.g. `192.168.178.46`)
4. Enter that IP when the voucher scanner app starts

> **Tip:** If the connection is slow or laggy over WiFi, consider the USB mode below.

### Mode 3 — Phone camera over USB (best quality, lowest latency)

This streams directly from the phone camera over a USB cable — no WiFi needed,
no resolution limits, no lag. It requires more one-time setup.

**When to use this:**
- WiFi connection is unstable or too slow
- You want the highest possible resolution (up to 2560×1440)
- You want a reliable, cable-based connection

**Setup:** Follow the step-by-step guide in [`README_USB_from_phone.md`](README_USB_from_phone.md).
It covers installing v4l2loopback, building scrcpy 3.x, phone settings, and the passwordless sudo rule for the desktop launcher.

---

## Configure `.env` (optional)

Create a file called `.env` in the project folder. This stores your settings so you don't have to re-enter them every time:

```bash
# IP address of your phone (only needed for WiFi/IP Webcam mode)
IP_PHONE="192.168.178.46"
PORT="8080"

# Default camera mode: "ip", "laptop", or "usb"
CAMERA_MODE="ip"
```

You can leave `IP_PHONE` empty if you only use the laptop camera or USB mode.

---

## Usage

```bash
python voucher-scanner.py
```

A setup window opens first where you choose your camera mode and (if needed) enter the phone IP.

### Quick Workflow

1. **Choose camera** in the setup window → click **Start Video**
2. **Position barcode** in the frame → click **Take Picture** to freeze
3. **Shop auto-detects** (or select manually for ALDI/LIDL)
4. **Click the shop button** → auto-fills the form
   - **DM**: Instant
   - **ALDI/EDEKA**: Automated
   - **REWE/LIDL**: Manual browser opens on the right (fill manually)
5. **New Scan** to go back to camera

### Window Layout

```
┌───────────────────────────────────────────────────────────┐
│  Scanner (left)  │  Browser (middle)  │  Browser (right)  │
│   TK window      │  Selenium 1/3 w    │  Manual 1/3 w     │
│   Full height    │    Full height     │    Full height    │
└───────────────────────────────────────────────────────────┘
```

### Tips

- **Good lighting** = better detection
- **Hold steady** 1–2 seconds in live mode
- **38-digit codes** auto-trim to 20 digits (ALDI/LIDL)
- **CAPTCHA**: Solve manually if it appears
- **Restart camera** if the connection drops

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Camera won't open | Check IP Webcam is running on phone, verify IP address, try a different camera mode |
| No barcode detected | Improve lighting, try a different angle, hold the barcode steady |
| Browser error | Make sure Firefox is installed: `firefox --version` |
| Form not filling | Check internet connection, wait for page to fully load, solve CAPTCHA manually |
| USB camera not found | Make sure scrcpy is running before starting the app — see `README_USB_from_phone.md` |

---

## Creating a Desktop Launcher

Instead of opening a terminal every time, you can create a clickable desktop icon.
Full instructions including the automatic USB camera startup are in [`Desktop_Launcher_Setup.md`](Desktop_Launcher_Setup.md).

### Linux (quick version)

1. Create wrapper script `start_voucher_scanner.sh` in the project folder:

```bash
#!/usr/bin/env bash
cd "$(dirname "$0")"
source ~/miniconda3/etc/profile.d/conda.sh
conda activate voucher-scanner

# If Android phone is connected via USB, start the camera stream automatically
SCRCPY_PID=""
if adb devices 2>/dev/null | grep -q "device$"; then
    sudo -n modprobe -r v4l2loopback 2>/dev/null
    sudo -n modprobe v4l2loopback devices=1 video_nr=2 card_label="DroidCam" exclusive_caps=1 max_width=2560 max_height=1440
    scrcpy --v4l2-sink=/dev/video2 --no-playback --video-source=camera --camera-size=2560x1440 &
    SCRCPY_PID=$!
    sleep 3
fi

python voucher-scanner.py

[ -n "$SCRCPY_PID" ] && kill $SCRCPY_PID 2>/dev/null
```

Make it executable:
```bash
chmod +x start_voucher_scanner.sh
```

2. Create desktop entry `~/.local/share/applications/voucher-scanner.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=Voucher Scanner
Exec=/home/<USER>/Nextcloud/Bezahlkarte_Gutscheine/voucher-scanner/start_voucher_scanner.sh
Icon=/home/<USER>/Nextcloud/Bezahlkarte_Gutscheine/voucher-scanner/icon.png
Terminal=true
```

Replace `<USER>` with your username (run `whoami` in a terminal if unsure).

3. Set permissions:

```bash
chmod 755 ~/.local/share/applications/voucher-scanner.desktop
update-desktop-database ~/.local/share/applications/
```

4. Optional — place on desktop:

```bash
ln -s ~/.local/share/applications/voucher-scanner.desktop ~/Schreibtisch/
# or ~/Desktop/ on English systems
```

Right-click the icon → **Allow Launching** (GNOME).

**For full details including the passwordless sudo setup**, see [`Desktop_Launcher_Setup.md`](Desktop_Launcher_Setup.md).

### macOS

Create `~/voucher-scanner.command`:

```bash
#!/bin/bash
cd /path/to/voucher-scanner
conda run -n voucher-scanner python voucher-scanner.py
```

```bash
chmod +x ~/voucher-scanner.command
# Drag to Applications or Desktop
```

### Windows

Create `voucher-scanner.bat`:

```batch
@echo off
cd C:\path\to\voucher-scanner
conda activate voucher-scanner
python voucher-scanner.py
```

Create a shortcut to the `.bat` file on your Desktop → right-click → Properties → Change Icon.

---

## Related Documentation

| File | Contents |
|------|----------|
| [`README_USB_from_phone.md`](README_USB_from_phone.md) | Full USB camera setup: v4l2loopback, scrcpy, phone settings, passwordless sudo |
| [`Desktop_Launcher_Setup.md`](Desktop_Launcher_Setup.md) | Desktop icon setup with automatic USB camera detection |
| `environment.yml` | Conda environment definition |
| `requirements.txt` | pip package list |

---

## License & Credits

Built for personal use. See `voucher-scanner.py` for library credits.

**Built with**: OpenCV, pyzbar, Selenium, undetected-chromedriver