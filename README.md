# Voucher Scanner

A Python barcode/QR scanner with automatic gift card detection and browser automation for REWE, DM, ALDI, LIDL, EDEKA.

## Features

- **Live & Picture barcode scanning** with automatic detection
- **Dual camera modes**: Laptop webcam or IP phone camera
- **Automatic shop detection** by card number format
- **Fast form filling**: DM instant, ALDI/EDEKA automated, REWE/LIDL manual
- **Multi-window layout**: Scanner left, Selenium browser middle, manual browser right
- **Anti-bot measures** for reliable automation

## Shops

| Shop | Digits | Method |
|------|--------|--------|
| REWE | 13 | Manual (slow Friendly Captcha) |
| DM | 24 | Auto (super fast) |
| EDEKA | 16 | Auto |
| ALDI | 20 | Manual select |
| LIDL | 20 | Manual select |

**ALDI & LIDL same format** → manually select after scan.

## Installation

### Setup (Conda recommended)

```bash
conda env create -f environment.yml
conda activate voucher-scanner
```

### Setup (pip)

```bash
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Configure `.env`

```bash
# IP Phone (IP Webcam app)
IP_PHONE="192.168.178.46"
LAPTOP_CAM=False

# OR Laptop Camera
LAPTOP_CAM=True
```

**IP Webcam**: Install app on Android, start server, use phone's IP.

## Usage

```bash
python voucher-scanner.py
```

### Quick Workflow

1. **Start Browser** → Opens shop tabs in Firefox
2. **Position barcode** → "Take Picture" to freeze
3. **Shop auto-detects** (or select manually for ALDI/LIDL)
4. **Fill Selected** → Auto-fills form
   - **DM**: Instant
   - **ALDI/EDEKA**: Automated
   - **REWE/LIDL**: Manual browser opens right (fill manually)
5. **Reset Camera** if needed

### Window Layout

```
┌─────────────────────────────────────────┐
│  Scanner (left)  │ Browser (middle) │ Browser (right) │
│   TK window      │ Selenium 1/3 w   │ Manual 1/3 w    │
│   Full height    │   Full height    │   Full height   │
└─────────────────────────────────────────┘
```

### Tips

- **Good lighting** = better detection
- **Hold steady** 1-2 seconds in live mode
- **38-digit codes** auto-trim to 20 digits (ALDI/LIDL)
- **CAPTCHA**: Solve manually if appears
- **Restart camera** if connection drops

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Camera won't open | Check IP Webcam running, verify IP in `.env`, try `CAMERA_SOURCE=0` |
| No barcode | Improve lighting, try different angle, hold steady |
| Browser error | Ensure Firefox installed: `firefox --version` |
| Form not filling | Check internet, wait for page load, solve CAPTCHA manually |

## Creating Desktop Icon

### Linux

1. **Create wrapper script** `start_voucher_scanner.sh`:

```bash
#!/usr/bin/env bash
cd "$(dirname "$0")"
source ~/miniconda3/etc/profile.d/conda.sh
conda activate voucher-scanner
python voucher-scanner.py
```

Make it executable:
```bash
chmod +x start_voucher_scanner.sh
```

2. **Create desktop entry** `~/.local/share/applications/voucher-scanner.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=Voucher Scanner
Comment=Gift Card Barcode Scanner
Exec=/home/madsee/Nextcloud3/Bezahlkarte_Gutscheine/voucher-scanner/start_voucher_scanner.sh
Icon=/home/madsee/Nextcloud3/Bezahlkarte_Gutscheine/voucher-scanner/icon.png
Terminal=false
Categories=Utility;
```

3. **Update desktop database**:

```bash
chmod 755 ~/.local/share/applications/voucher-scanner.desktop
update-desktop-database ~/.local/share/applications/
```

4. **Optional**: Create desktop link:

```bash
ln -s ~/.local/share/applications/voucher-scanner.desktop ~/Desktop/
```

Right-click the desktop icon → Allow Launching (for GNOME).

**See also**: [Desktop Launcher Setup.md](Desktop%20Launcher%20Setup.md)

### macOS

Create `~/voucher-scanner.command`:

```bash
#!/bin/bash
cd /path/to/voucher-scanner
conda run -n voucher-scanner python voucher-scanner.py
```

Then:
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

Create shortcut to `.bat` on Desktop → Properties → Advanced → Change Icon.

## License & Credits

Built for personal use. See `voucher-scanner.py` for library credits.

**Built with**: OpenCV, pyzbar, Selenium, undetected-chromedriver
