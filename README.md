# Voucher Scanner

A Python-based barcode/QR code scanner with automatic shop detection and browser automation for checking gift card balances. Supports REWE, DM, ALDI, LIDL, and EDEKA gift cards.

## Features

- **Live barcode scanning** with automatic code detection
- **Dual camera modes**: Laptop webcam or IP phone camera
- **Automatic shop detection** based on card number format
- **Browser automation** to fill gift card balance check forms
- **Anti-detection measures** for bot protection bypass
- **Stability threshold** to avoid false detections

## Supported Shops

| Shop | Card Digits | Auto-Detection |
|------|-------------|----------------|
| REWE | 13 | ✅ Automatic |
| DM | 24 | ✅ Automatic |
| EDEKA | 16 | ✅ Automatic |
| ALDI | 20 (or 38→20) | ⚠️ Manual choice |
| LIDL | 20 (or 38→20) | ⚠️ Manual choice |

**Note**: ALDI and LIDL both use 20-digit codes, so you must manually select which shop after detection.

## Requirements

### System Requirements

- **Python 3.8+** (3.12 recommended)
- **Conda** (recommended) or **pip** for package management
- **Tesseract OCR** (optional, for OCR fallback - auto-installed with Conda)
- **Web Browser**: Firefox (recommended), Chrome, or Safari

### Python Dependencies

See `requirements.txt` for full list. Key dependencies:
- OpenCV (`cv2`)
- pyzbar (barcode decoding)
- Selenium (browser automation)
- Tkinter (GUI)
- PIL/Pillow (image processing)

## Installation

### 1. Install System Dependencies

#### Using Conda (Easiest - Recommended)

Conda handles most dependencies automatically. Just install:

```bash
# Install Miniconda or Anaconda
# Download from: https://docs.conda.io/en/latest/miniconda.html

# No additional system packages needed!
# Conda will install zbar, tesseract, etc. automatically
```

#### Using System Package Manager (Alternative)

If not using Conda, install these system packages:

##### Linux (Ubuntu/Debian)
```bash
# Install Tesseract OCR (optional)
sudo apt-get update
sudo apt-get install tesseract-ocr

# Install zbar library for pyzbar
sudo apt-get install libzbar0

# Install Firefox (recommended browser)
sudo apt-get install firefox
```

##### macOS
```bash
# Install Tesseract OCR (optional)
brew install tesseract

# Install zbar library
brew install zbar

# Firefox usually pre-installed, or:
brew install --cask firefox
```

##### Windows
- Download and install [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) (optional)
- zbar is bundled with pyzbar on Windows
- Install Firefox from [mozilla.org](https://www.mozilla.org/firefox/)

### 2. Install Python Dependencies

#### Option A: Using Conda (Recommended)

```bash
# Create conda environment from environment.yml
conda env create -f environment.yml

# Activate the environment
conda activate voucher-scanner
```

#### Option B: Using pip + virtualenv

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

**Note**: Conda automatically handles system dependencies like zbar and tesseract, making it easier to set up.

### 3. Configure Camera Settings

Create a `.env` file in the project directory:

```bash
# For IP Phone Camera (using IP Webcam app)
IP_PHONE="192.168.178.46"
LAPTOP_CAM=False

# OR for Laptop Webcam
LAPTOP_CAM=True
CAMERA_SOURCE=0
```

#### Using IP Phone Camera (IP Webcam App)

1. Install **IP Webcam** app on your Android phone ([Play Store](https://play.google.com/store/apps/details?id=com.pas.webcam))
2. Start the server in the app
3. Note the IP address shown (e.g., `192.168.178.46`)
4. Set `IP_PHONE` in `.env` to your phone's IP address
5. Set `LAPTOP_CAM=False`

#### Using Laptop Webcam

1. Set `LAPTOP_CAM=True` in `.env`
2. Optionally set `CAMERA_SOURCE=0` (or 1, 2 for other cameras)

## Usage

### Starting the Application

```bash
# If using Conda
conda activate voucher-scanner
python voucher-scanner.py

# If using virtualenv
source venv/bin/activate  # On Windows: venv\Scripts\activate
python voucher-scanner.py
```

### Workflow

#### 1. **Start Browser**
- Click **"Start Browser"** button first
- This opens all shop tabs in Firefox (REWE, DM, ALDI, LIDL, EDEKA)
- Browser stays open for the entire session

#### 2. **Capture/Scan Barcode**

**Picture Mode** (IP Phone Camera, `LAPTOP_CAM=False`):
- Position the gift card barcode in the scanning area
- Click **"Take Picture"** to freeze and scan
- The app will detect the code and display it

**Live Mode** (Laptop Camera, `LAPTOP_CAM=True`):
- Hold the gift card steady in the scanning area
- The app continuously scans until it detects a stable code
- After detection, click **"Take Picture"** to restart scanning for a new card

#### 3. **Select Shop**

- **Auto-detection**: For REWE (13 digits), DM (24 digits), and EDEKA (16 digits), the shop is automatically selected
- **Manual selection**: For ALDI/LIDL (20 digits), both buttons turn **orange** - you must click the correct shop
- Selected shop button turns **green**

#### 4. **Fill Form**

- Click **"Fill Selected"** to automatically fill the shop's balance check form
- The browser will:
  - Switch to the correct shop tab
  - Fill in the card number (and PIN if detected)
  - Wait for any CAPTCHA resolution

#### 5. **Reset Camera** (if needed)

- If camera disconnects or you exit IP Webcam temporarily
- Click **"Reset Camera"** to reconnect
- Especially useful when using phone camera and need phone for other tasks

### Tips

- **Good lighting** improves barcode detection
- **Hold card steady** for 1-2 seconds in live mode
- **38-digit codes** (ALDI/LIDL) are automatically trimmed to 20 digits
- **CAPTCHA handling**: The browser may wait for manual CAPTCHA solving
- **Multiple cards**: After filling one form, restart detection and repeat

## Troubleshooting

### Camera Issues

**"Could not open camera"**
- Check IP Webcam app is running (for phone camera)
- Verify IP address in `.env` matches phone's IP
- For laptop cam, try different `CAMERA_SOURCE` values (0, 1, 2)

**Camera disconnects frequently**
- Use **Reset Camera** button to reconnect
- Check WiFi stability for IP camera
- Consider using laptop webcam for more stability

### Barcode Detection Issues

**"No barcode found"**
- Ensure good lighting on the barcode
- Try different angles
- Clean camera lens
- Hold card closer or farther from camera
- Enable OCR fallback by setting `OCR_SWITCH=True` in the script

### Browser Issues

**"Could not start browser"**
- Ensure Firefox is installed: `firefox --version`
- Try Chrome if Firefox fails (script will auto-fallback)
- Check selenium webdriver is installed: `pip show selenium`

**Form not filling**
- Check internet connection
- Wait for page to fully load
- Some shops have CAPTCHA - solve it manually
- Try clicking the field manually first

### Performance Issues

**High CPU usage**
- Reduce camera resolution in IP Webcam app
- Close unnecessary browser tabs
- The script is optimized but continuous scanning uses CPU

## Configuration Options

Edit these constants in `voucher-scanner.py` to customize:

```python
# Detection tuning
STABLE_THRESHOLD = 3  # Frames needed for stable detection (live mode)
SCAN_EVERY_MS = 150   # Scanning frequency in milliseconds

# OCR settings
OCR_SWITCH = False    # Enable OCR fallback (requires Tesseract)
MIN_OCR_DIGITS = 10   # Minimum digits for OCR detection
MAX_OCR_DIGITS = 24   # Maximum digits for OCR detection

# Camera resolution
RES_PHONE_WIDTH = 800
RES_PHONE_HEIGHT = 480
```

## Development

### Project Structure
```
voucher-scanner/
├── voucher-scanner.py    # Main application
├── environment.yml       # Conda environment file
├── requirements.txt      # Pip requirements file
├── .env                  # Configuration (not in git)
├── .env.example          # Example configuration
├── icon.png              # Application icon (optional)
└── README.md            # This file
```

### Adding New Shops

Edit the `SHOPS` dictionary in `voucher-scanner.py`:

```python
SHOPS = {
    "NEW_SHOP": {
        "url": "https://shop.example.com/balance",
        "card_selector": "#card_number_field",
        "pin_selector": "#pin_field",  # Optional
        "iframe_selector": None,  # If form is in iframe
        "emoji": "🏪",
        "simulate_human": False,  # Enable anti-detection
    },
}
```

Then add validation logic in `_validate_for()` method.

## Security Notes

- **Browser automation** uses anti-detection measures (undetected-chromedriver, Firefox preferences)
- **No credentials stored** - only card numbers are temporarily in memory
- **HTTPS only** - all shop URLs use secure connections
- **.env file** should be added to `.gitignore` (not committed to git)

## License

This project is for educational and personal use. Respect the terms of service of each shop's website.

## Credits

Built with:
- [OpenCV](https://opencv.org/) - Image processing
- [pyzbar](https://github.com/NaturalHistoryMuseum/pyzbar) - Barcode decoding
- [Selenium](https://www.selenium.dev/) - Browser automation
- [undetected-chromedriver](https://github.com/ultrafunkamsterdam/undetected-chromedriver) - Anti-detection

## Support

For issues or questions:
1. Check the Troubleshooting section above
2. Verify all dependencies are installed correctly
3. Test camera connection independently first
4. Check Firefox/Chrome browser works manually