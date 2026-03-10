#!/usr/bin/env python3

"""
Picture-based Barcode/QR/OCR Reader (Tkinter + OpenCV + pyzbar) + Selenium shop buttons

Shops supported:
  - REWE, DM, ALDI, LIDL, EDEKA

Usage:
  1. Adjust camera view with live video
  2. Click "Take Picture" when ready
  3. Code scans the frozen image
  4. Click shop buttons to fill forms
  5. Click "New Scan" to take another picture

"""

import os, time
import platform
import subprocess
import sys
import threading
import time
import webbrowser
import tkinter as tk
from tkinter import messagebox, ttk
import tkinter.font as tkfont
import pytesseract
from pytesseract import Output

import cv2
import numpy as np
from PIL import Image, ImageTk
from dotenv import load_dotenv
import os

load_dotenv()


# ---- Font system (cross-platform) --------
def _detect_font_family():
    """Detect a safe font family available on this system."""
    available_fonts = tkfont.families()
    candidates = [
        "helvetica",
        "times",
        "clean",
        "courier",
        "TkDefaultFont",
    ]
    for font in candidates:
        if font in available_fonts:
            return font
    # Fallback to first available font
    return available_fonts[0] if available_fonts else "TkDefaultFont"


# Note: Font objects are created lazily in SetupWindow and VoucherScannerApp __init__
# to ensure a Tk window exists before calling tkfont.families()

# ---- Global configuration variables (will be set by setup window) --------
IP_phone = os.getenv("IP_PHONE", "192.168.1.102")
PORT = os.getenv("PORT", "8080")
# Camera mode: "laptop" (0), "usb" (2), or "ip" (phone webcam URL)
CAMERA_MODE = os.getenv("CAMERA_MODE", "ip")  # Default to IP webcam
SCANNING_FLAG = False  # Will be set based on camera mode
# TODO: make scanning possible for IP Webcam
SCANNING_MODE = os.getenv(
    "SCANNING_MODE", "Picture Mode"
)  # "Picture Mode" or "Live Auto-Scan"
# For USB mode, force picture mode; otherwise use SCANNING_MODE
if CAMERA_MODE == "usb":
    SCANNING_FLAG = False  # USB always uses picture mode
else:
    SCANNING_FLAG = True if SCANNING_MODE == "Live Auto-Scan" else False
OCR_SWITCH = False  # Fallback for linear barcodes if pyzbar fails

MAC = False  # Set to True if running on macOS, False for Linux
if platform.system() == "Darwin":  # macOS
    MAC = True

# QR Code decoder - set to False to disable QR/Data Matrix decoding
QR_DECODER_ENABLED = True

# Resolution preferences in order of preference (try highest first, fall back to lower)
SUPPORTED_RESOLUTIONS = [
    (1920, 1080),  # Full HD
    (1280, 720),  # HD (most USB cameras support this)
    (1024, 768),  # XGA (fallback for older USB cameras)
    (800, 600),  # SVGA (last resort)
    (640, 480),  # VGA (minimum acceptable)
]

RES_PHONE_WIDTH = 1920
RES_PHONE_HEIGHT = 1080


def create_capture(source: str) -> cv2.VideoCapture:
    """Create VideoCapture object from index or URL."""
    try:
        idx = int(source)
        return cv2.VideoCapture(idx)
    except ValueError:
        return cv2.VideoCapture(source)


def find_best_camera_device(base_index: int = 0) -> int:
    """
    On Linux, try to find the best camera device among /dev/video* entries.
    Tests resolution capabilities to find the one with highest quality.
    Returns the index of the best camera device.
    """
    import platform
    import time

    if platform.system() != "Linux":
        return base_index

    best_index = base_index
    best_resolution = (0, 0)

    # Try indices around the base (e.g., if base_index is 2, try 2, 3, 4, 5, 6)
    for idx in range(base_index, base_index + 8):
        try:
            test_cap = cv2.VideoCapture(idx)
            if not test_cap.isOpened():
                continue

            # Give camera time to initialize
            time.sleep(0.5)

            # Try multiple resolutions to find capability
            # Start with highest and work down
            test_resolutions = [(1920, 1080), (1280, 720), (1024, 768), (800, 600)]

            for test_w, test_h in test_resolutions:
                test_cap.set(cv2.CAP_PROP_FRAME_WIDTH, test_w)
                test_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, test_h)
                time.sleep(0.2)

                # Try to read a frame
                ret, frame = test_cap.read()
                if ret:
                    h, w = frame.shape[:2]
                    print(
                        f"[DEBUG] Camera {idx} (/dev/video{idx}) - requested {test_w}x{test_h}, got {w}x{h}"
                    )

                    # If we got a high resolution, prefer this camera
                    if w * h > best_resolution[0] * best_resolution[1]:
                        best_resolution = (w, h)
                        best_index = idx

                    # If we got Full HD or higher, stop testing other resolutions
                    if w >= 1280 or h >= 720:
                        break

            test_cap.release()

            # If we found a good camera (at least HD), don't test further
            if best_resolution[0] >= 1280:
                break

        except Exception as e:
            pass

    if best_resolution != (0, 0):
        print(
            f"[DEBUG] Selected camera index {best_index} with resolution {best_resolution[0]}x{best_resolution[1]}"
        )
    else:
        print(f"[DEBUG] No suitable camera found, using default index {base_index}")

    return best_index


def set_optimal_resolution(cap: cv2.VideoCapture) -> tuple:
    """
    Set the camera to best supported resolution.
    For Logitech C270: tries 1280x960, 1280x720, 1024x768, 800x600, 640x480
    Returns (width, height) tuple of the actual resolution achieved.
    """
    import time

    # Allow camera to initialize
    print("[DEBUG] Initializing camera...")
    time.sleep(1)

    # Read a few frames to warm up
    for _ in range(3):
        cap.read()

    # Try to set good resolutions (Logitech C270 supports 1280x960)
    resolutions_to_try = [
        (1280, 960),  # Logitech C270 native
        (1280, 720),  # HD
        (1024, 768),  # XGA
        (800, 600),  # SVGA
        (640, 480),  # VGA default
    ]

    for width, height in resolutions_to_try:
        print(f"[DEBUG] Trying to set resolution {width}x{height}...")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        time.sleep(0.3)

        # Read frame and check actual resolution
        ret, frame = cap.read()
        if ret:
            actual_h, actual_w = frame.shape[:2]
            print(f"[DEBUG] Requested {width}x{height}, got {actual_w}x{actual_h}")

            # If we got it or close to it, accept it
            if abs(actual_w - width) <= 5 and abs(actual_h - height) <= 5:
                print(f"[DEBUG] ✓ Resolution set to {actual_w}x{actual_h}")
                return (actual_w, actual_h)

    # Fallback: use whatever the camera is currently set to
    ret, frame = cap.read()
    if ret:
        actual_h, actual_w = frame.shape[:2]
        print(f"[DEBUG] Using default resolution: {actual_w}x{actual_h}")
        return (actual_w, actual_h)

    # Last resort
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[DEBUG] Fallback resolution: {actual_w}x{actual_h}")
    return (actual_w, actual_h)


# ---- Beep on success -----------------------------------------------------
try:
    # --- Windows ---

    import winsound

    def beep(freq=1500, dur=120):
        try:
            winsound.Beep(freq, dur)

        except Exception:
            pass  # Fail silently (e.g., no sound card)

except ImportError:
    # --- Not Windows ---

    if platform.system() == "Darwin":  # macOS

        def beep(*args, **kwargs):
            try:
                # Use 'afplay' on macOS. Non-blocking.

                subprocess.Popen(
                    ["afplay", "/System/Library/Sounds/Purr.aiff"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            except Exception:
                pass  # Fail silently

    else:
        # --- Linux or other ---

        def beep(*args, **kwargs):
            # No-op for other systems

            pass

except ImportError:
    if platform.system() == "Darwin":  # macOS

        def beep(*args, **kwargs):
            try:
                subprocess.Popen(
                    ["afplay", "/System/Library/Sounds/Purr.aiff"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

    else:

        def beep(*args, **kwargs):
            pass


# ---- Barcode backend -----------------------------------------------------
try:
    from pyzbar.pyzbar import ZBarSymbol, decode
except Exception as e:
    print("ERROR: pyzbar not available:", e)
    print("Install: conda install -c conda-forge pyzbar zbar")
    sys.exit(1)

# ---- ZXing backend (preferred for robust decoding) -------------------------
ZXING_AVAILABLE = False
try:
    import zxingcpp

    ZXING_AVAILABLE = True
except ImportError:
    print("WARNING: zxingcpp not available (install: pip install zxing-cpp)")
    ZXING_AVAILABLE = False


# ---- Optional OCR backend ------------------------------------------------
if OCR_SWITCH:
    try:
        import pytesseract

        TESSERACT_AVAILABLE = True
    except Exception:
        OCR_SWITCH = False
        print("WARNING: pytesseract not available, OCR fallback disabled.")


def zbar_symbols(names):
    """Return available ZBarSymbol members."""
    out = []

    for n in names:
        sym = getattr(ZBarSymbol, n, None)

        if sym is not None:
            out.append(sym)

    return out


LINEAR_SYMBOL_NAMES = [
    "EAN13",
    "EAN8",
    "UPCA",
    "UPCE",
    "CODE128",
    "CODE39",
    "CODE93",
    "I25",  # Interleaved 2 of 5
    "CODABAR",
    "CODE32",  # Italian Pharmacode
    "DATABAR",
    "DATABAR_EXP",
]
SYMBOLS = zbar_symbols(LINEAR_SYMBOL_NAMES + ["QRCODE", "PDF417"])

# ---- Shop configurations -------------------------------------------------
SHOPS = {
    "REWE": {
        "url": "https://kartenwelt.rewe.de/rewe-geschenkkarte.html",
        "card_selector": "#card_number",  # //*[@id="card_number"]
        "pin_selector": "#pin",
        "emoji": "[REWE]",
        "simulate_human": True,
    },
    "DM": {
        "url": "https://www.dm.de/services/services-im-markt/geschenkkarten",
        "card_selector": "#credit-checker-printedCreditKey-input",
        "pin_selector": "#credit-checker-verificationCode-input",
        "emoji": "[DM]",
        "simulate_human": False,
    },
    "ALDI": {
        "url": "https://www.helaba.com/de/aldi/",
        "iframe_selector": 'iframe[src*="balancechecks"]',
        "card_selector": ".cardnumberfield",
        "pin_selector": ".pin",
        "emoji": "[ALDI]",
        "simulate_human": False,
    },
    "LIDL": {
        "url": "https://www.lidl.de/c/lidl-geschenkkarten/s10007775",
        "iframe_selector": 'iframe[src*="balance.php?cid=79"]',
        "card_selector": ".AGiftyBalanceCheck__input-card-number input",
        "pin_selector": ".AGiftyBalanceCheck__input-pin input",
        "emoji": "[LIDL]",
        "simulate_human": False,
    },
    # "EDEKA": {
    #     "url": "https://evci.pin-host.com/evci/#/saldo",
    #     "card_selector": '#postform > div > div:nth-child(5) > div > div > input[type="text"]:nth-child(1)',
    #     "pin_selector": None,
    #     "emoji": "🍎",
    #     "simulate_human": False,
    # },
}


SELENIUM_AVAILABLE = True

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
except Exception:
    SELENIUM_AVAILABLE = False

import random
from selenium.webdriver.common.action_chains import ActionChains

# Try to import undetected-chromedriver
UNDETECTED_CHROME_AVAILABLE = False
try:
    import undetected_chromedriver as uc

    UNDETECTED_CHROME_AVAILABLE = True
except Exception:
    print(
        "WARNING: undetected-chromedriver not available. Install with: pip install undetected-chromedriver"
    )

# ---- Tuning parameters ---------------------------------------------------
MIN_OCR_DIGITS = 10
MAX_OCR_DIGITS = 24
PIN_DIGITS = 4
# Barcode mode ROI (rectangular)
ROI_HEIGHT_FRAC = 0.42
ROI_WIDTH_FRAC = 0.95
# QR Code mode ROI (square, larger for better detection at full resolution)
QR_ROI_SIZE_FRAC = 0.65  # 65% of the smaller dimension (square)
CLAHE_CLIP = 2.0
CLAHE_TILE = (8, 8)
UNSHARP_AMOUNT = 1.4
UNSHARP_SIGMA = 1.0
MORPH_KERNEL_W = 21
MORPH_KERNEL_H = 3
MORPH_ITER = 1
SCAN_EVERY_MS = 150  # scanning cadence (ms)
STABLE_THRESHOLD = 3  # consecutive frames to be "sure" (2 = one confirmation scan)
DRAW_DASH_GAP = 14
CORNER_LEN = 26
OVERLAY_COLOR = (0, 200, 255)  # BGR
BOX_COLOR = (0, 220, 0)
TEXT_COLOR = (20, 20, 20)
SUCCESS_COLOR = (0, 220, 0)


def human_typing(element, text):
    """Type with random delays between keystrokes to mimic human behavior (optimized for CPU)."""
    for char in text:
        element.send_keys(char)
        # Longer delays to reduce CPU usage while still appearing human
        time.sleep(random.uniform(0.08, 0.15))


def human_move_and_click(driver, element):
    """Move mouse naturally before clicking (optimized for CPU)."""
    actions = ActionChains(driver)
    # Reduced movement complexity to save CPU
    actions.move_to_element(element).pause(random.uniform(0.5, 1.0)).click().perform()


def fast_typing(element, text):
    """Type instantly without delays for speed (when simulate_human=False)."""
    element.send_keys(text)


def fast_click(driver, element):
    """Click instantly without human-like delays (when simulate_human=False).
    Falls back to JS click if an overlay intercepts the normal click."""
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)


def simulate_human_behavior(driver):
    """Simulate human browsing before filling form (lightweight, CPU-optimized)."""
    try:
        # Single scroll instead of multiple movements
        scroll_amount = random.randint(100, 300)
        driver.execute_script(f"window.scrollTo(0, {scroll_amount})")
        time.sleep(random.uniform(1.0, 2.0))

        # Minimal mouse movement to avoid excessive CPU usage
        actions = ActionChains(driver)
        # Just one small movement instead of 2-4 large ones
        try:
            actions.move_by_offset(
                random.randint(-100, 100), random.randint(-100, 100)
            ).perform()
        except Exception:
            pass
        time.sleep(random.uniform(0.5, 1.0))
    except Exception:
        pass


def wait_for_captcha(driver, timeout=180):
    """Wait for CAPTCHA/bot-detection to resolve (invisible reCAPTCHA, etc.)."""
    try:
        print(f"[DEBUG] Waiting for CAPTCHA with timeout {timeout}s...")
        wait = WebDriverWait(driver, timeout)

        # Check for reCAPTCHA iframe
        try:
            wait.until_not(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "iframe[src*='recaptcha']")
                )
            )
            print("[DEBUG] reCAPTCHA iframe resolved")
        except Exception:
            pass

        # Check for generic captcha iframes
        try:
            wait.until_not(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "iframe[src*='captcha']")
                )
            )
            print("[DEBUG] Captcha iframe resolved")
        except Exception:
            pass

        # Give browser time to complete any remaining background tasks
        time.sleep(2)
        print("[DEBUG] CAPTCHA check complete")

    except Exception as e:
        print(f"[DEBUG] CAPTCHA wait timed out or error: {e}")
        pass  # Timeout or no CAPTCHA present


class SetupWindow:
    """Setup window to configure IP, PORT, and camera choice."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Voucher Scanner - Setup")
        self.root.geometry("600x600")
        self.result = None

        # Initialize fonts (after Tk window exists)
        ui_font_family = _detect_font_family()
        self.font_label = tkfont.Font(family=ui_font_family, size=10)
        self.font_bold = tkfont.Font(family=ui_font_family, size=10, weight="bold")
        self.font_button = tkfont.Font(family=ui_font_family, size=11, weight="bold")
        self.font_title = tkfont.Font(family=ui_font_family, size=11, weight="bold")
        self.font_status = tkfont.Font(family=ui_font_family, size=10)

        # Main frame
        main_frame = ttk.Frame(root, padding="20")
        main_frame.pack(fill="both", expand=True)

        # Title

        # Explanation
        explanation = tk.Text(
            main_frame, height=16, width=80, wrap="word", relief="flat"
        )
        explanation.pack(pady=(0, 15), padx=5)
        explanation.insert(
            "1.0",
            """### Instructions ###:
Make sure your laptop is in the same WiFi network as your phone.
Enter the IP address shown in the app below.
    → if you cannot connect, restart WLAN on both devices, your PC and your Phone
Android: Download and start "IP Webcam" app
    → Enable camera access and start the server
iOS: Download and start "DroidCam" app
    → Enable camera access and start the connection
→ set Video resolution to min 1280x720 (in app settings - even higher resolution slows down the connection)

Open REWE and LIDL in a seperate browser manually:
https://kartenwelt.rewe.de/rewe-geschenkkarte.html
https://www.lidl.de/c/lidl-geschenkkarten/s10007775
""",
        )
        # Get defaults from environment
        default_ip = os.getenv("IP_PHONE", "192.168.1.184")
        default_port = os.getenv("PORT", "8080")
        default_camera_mode = os.getenv("CAMERA_MODE", "ip")

        # Camera choice frame
        camera_frame = ttk.LabelFrame(main_frame, text="Camera Selection", padding="10")
        camera_frame.pack(fill="x", pady=(0, 20))

        self.camera_choice = tk.StringVar(value=default_camera_mode)
        ttk.Radiobutton(
            camera_frame,
            text="Phone Webcam (IP Webcam/DroidCam) - Default",
            variable=self.camera_choice,
            value="ip",
        ).pack(anchor="w", pady=5)
        ttk.Radiobutton(
            camera_frame,
            text="Internal Laptop Camera",
            variable=self.camera_choice,
            value="laptop",
        ).pack(anchor="w", pady=5)
        ttk.Radiobutton(
            camera_frame,
            text="USB Webcam",
            variable=self.camera_choice,
            value="usb",
        ).pack(anchor="w", pady=5)

        # Input frame
        input_frame = ttk.LabelFrame(
            main_frame, text="Phone Webcam Configuration", padding="10"
        )
        input_frame.pack(fill="x", pady=(0, 20))

        # IP address
        ttk.Label(
            input_frame, text=f"IP Address (from .env or default {default_ip}):"
        ).pack(anchor="w", pady=(0, 5))
        self.ip_entry = ttk.Entry(input_frame, width=40)
        self.ip_entry.insert(0, default_ip)
        self.ip_entry.pack(anchor="w", pady=(0, 15), fill="x")

        # Port
        ttk.Label(
            input_frame, text=f"Port (from .env or default {default_port}):"
        ).pack(anchor="w", pady=(0, 5))
        self.port_entry = ttk.Entry(input_frame, width=40)
        self.port_entry.insert(0, default_port)
        self.port_entry.pack(anchor="w", pady=(0, 5), fill="x")

        # Start button
        ttk.Button(
            main_frame, text="Start Video", command=self.validate_and_start
        ).pack(pady=(10, 0))

    def validate_and_start(self):
        """Validate inputs and start the app."""
        try:
            ip = self.ip_entry.get().strip()
            port = self.port_entry.get().strip()
            camera = self.camera_choice.get()

            # Validate IP format (basic check)
            if camera == "ip":
                if not ip:
                    messagebox.showwarning(
                        "Invalid Input", "IP address cannot be empty"
                    )
                    return

                # Basic IP validation
                parts = ip.split(".")
                if len(parts) != 4:
                    messagebox.showwarning(
                        "Invalid IP Format",
                        f"Invalid IP format: {ip}\nExpected format: XXX.XXX.XXX.XXX",
                    )
                    return

                try:
                    for part in parts:
                        num = int(part)
                        if num < 0 or num > 255:
                            raise ValueError
                except ValueError:
                    messagebox.showwarning(
                        "Invalid IP Format",
                        f"Invalid IP format: {ip}\nEach part must be 0-255",
                    )
                    return

            # Validate port
            try:
                port_num = int(port)
                if port_num < 1 or port_num > 65535:
                    raise ValueError
            except ValueError:
                messagebox.showwarning(
                    "Invalid Port", f"Invalid port: {port}\nPort must be 1-65535"
                )
                return

            # Store result and close
            self.result = {
                "ip": ip,
                "port": port,
                "camera_mode": camera,  # "ip", "laptop", or "usb"
            }
            self.root.destroy()

        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {e}")


class VoucherScannerApp:

    def __init__(self, root: tk.Tk, camera_source: str):
        self.root = root
        self.camera_source = camera_source  # Store for reconnection

        # Initialize fonts (after Tk window exists)
        ui_font_family = _detect_font_family()
        self.font_label = tkfont.Font(family=ui_font_family, size=9, weight="bold")
        self.font_bold = tkfont.Font(family=ui_font_family, size=9, weight="bold")
        self.font_button = tkfont.Font(family=ui_font_family, size=10, weight="bold")
        self.font_title = tkfont.Font(family=ui_font_family, size=10, weight="bold")
        self.font_status = tkfont.Font(family=ui_font_family, size=9, weight="bold")

        # Get screen dimensions and position TK window in left quarter
        root.update_idletasks()  # Ensure window info is available
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()

        # Calculate left quarter dimensions
        quarter_width = screen_width // 4
        window_height = screen_height

        root.title(f"Voucher Scanner - {SCANNING_MODE}")
        root.resizable(True, True)
        root.geometry(
            f"{quarter_width}x{window_height}+0+0"
        )  # Left quarter, full height
        root.minsize(240, 300)

        # Store screen dimensions for later use (browser positioning)
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.middle_third_x = quarter_width
        self.middle_third_width = quarter_width

        # Camera setup
        self.cap = create_capture(camera_source)
        if not self.cap.isOpened():
            messagebox.showerror(
                "Camera Error",
                "Could not open the camera. If webcam App is running, reconnect WLAN on PC and Phone.",
            )

            root.destroy()

            sys.exit(1)

        # Camera hints
        # Use smart resolution detection - try to set optimal resolution
        actual_w, actual_h = set_optimal_resolution(self.cap)

        # Store the actual resolution for later use
        self.actual_width = actual_w
        self.actual_height = actual_h

        # Set FPS and autofocus
        self.cap.set(cv2.CAP_PROP_FPS, 20)
        # Autofocus settings for better focus performance
        self.cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)
        # Reduce buffer size for lower latency
        try:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass  # Not all cameras support buffer size setting

        # Try to enable autofocus via V4L2 on Linux
        self._enable_v4l2_autofocus(camera_source)

        print(f"[DEBUG] Final camera resolution: {actual_w}x{actual_h}")

        # Configure grid for vertical responsive layout
        root.columnconfigure(0, weight=1)  # Single column, full width

        # Row 0: Status label (full width)
        # Row 1: Camera feed (expands vertically)
        # Row 2: Controls panel (below camera)

        # Status label at top (full width)
        self.status = ttk.Label(
            root,
            text="Live video - Ready to capture",
            foreground="blue",
            anchor="w",
            font=self.font_status,
        )
        self.status.grid(row=0, column=0, sticky="ew", padx=12, pady=5)
        try:
            root.grid_rowconfigure(0, minsize=24)
        except Exception:
            pass

        # Camera row (expands to fill available space)
        root.grid_rowconfigure(1, weight=1)

        # ===== Camera Feed (top) =====
        self.label = ttk.Label(root)
        self.label.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")

        # ===== Controls Panel (below camera) =====
        controls_panel = ttk.Frame(root)
        controls_panel.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        controls_panel.columnconfigure(
            0, weight=1
        )  # Make controls stretch horizontally

        control_row = 0

        # --- Card Number and PIN Input ---
        controls_frame = ttk.LabelFrame(controls_panel, text="")
        controls_frame.grid(row=control_row, column=0, sticky="ew", padx=12, pady=5)
        controls_frame.columnconfigure(1, weight=1)
        control_row += 1

        ttk.Label(controls_frame, text="Card Number:", font=self.font_label).grid(
            row=0, column=0, sticky="w", padx=5, pady=2
        )
        self.code = tk.StringVar()
        ttk.Entry(
            controls_frame, textvariable=self.code, width=25, font=self.font_label
        ).grid(row=0, column=1, sticky="ew", padx=5, pady=2)

        ttk.Label(controls_frame, text="PIN:", font=self.font_label).grid(
            row=1, column=0, sticky="w", padx=5, pady=2
        )
        self.pin = tk.StringVar()
        ttk.Entry(
            controls_frame, textvariable=self.pin, width=6, font=self.font_label
        ).grid(row=1, column=1, sticky="w", padx=5, pady=2)

        # --- Start Browser ---
        start_hint = ttk.Label(
            controls_panel,
            text="Start browser first (open shop tabs if needed)",
            font=self.font_label,
        )
        start_hint.grid(row=control_row, column=0, sticky="ew", padx=12, pady=(8, 0))
        control_row += 1

        start_frame = ttk.Frame(controls_panel)
        start_frame.grid(row=control_row, column=0, sticky="ew", padx=12, pady=(0, 6))
        start_frame.columnconfigure(0, weight=1)
        control_row += 1

        self.start_browser_btn = ttk.Button(
            start_frame,
            text="Start Browser",
            command=lambda: (
                self._flash_button(self.start_browser_btn),
                self._manual_open_browser(),
            ),
        )
        self.start_browser_btn.grid(row=0, column=0, sticky="ew", padx=2)

        # --- Take Picture ---
        take_hint = ttk.Label(
            controls_panel,
            text="Take picture to freeze frame for scanning",
            font=self.font_label,
        )
        take_hint.grid(row=control_row, column=0, sticky="ew", padx=12, pady=(4, 0))
        if SCANNING_FLAG:
            take_hint.config(text="Take picture to restart detection")
        control_row += 1

        take_frame = ttk.Frame(controls_panel)
        take_frame.grid(row=control_row, column=0, sticky="ew", padx=12, pady=(0, 6))
        take_frame.columnconfigure(0, weight=1)
        control_row += 1

        if not SCANNING_FLAG:
            # Picture mode: show Take Picture button
            self.take_picture_btn = ttk.Button(
                take_frame,
                text="Take Picture",
                command=lambda: (
                    self._flash_button(self.take_picture_btn),
                    self._take_picture(),
                ),
            )
            self.take_picture_btn.grid(row=0, column=0, sticky="ew", padx=2)
        else:
            # Live mode: Take Picture button restarts detection
            self.take_picture_btn = ttk.Button(
                take_frame,
                text="Take Picture",
                command=lambda: (
                    self._flash_button(self.take_picture_btn),
                    self.reset_scan(),
                ),
            )
            self.take_picture_btn.grid(row=0, column=0, sticky="ew", padx=2)
            self.take_picture_btn.state(["disabled"])

        # QR Mode toggle button (if enabled)
        if QR_DECODER_ENABLED:
            self.qr_mode_btn = ttk.Button(
                take_frame,
                text="[1D] Barcode",
                command=lambda: self._toggle_qr_mode(),
            )
            self.qr_mode_btn.grid(row=0, column=1, sticky="ew", padx=2)
            take_frame.columnconfigure(1, weight=1)

        # --- Shop Buttons ---
        shop_hint = ttk.Label(
            controls_panel,
            text="Choose the Shop (choose ALDI or LIDL if ambiguous)",
            font=self.font_label,
        )
        shop_hint.grid(row=control_row, column=0, sticky="ew", padx=12, pady=(6, 0))
        control_row += 1

        # Detected shop status label
        self.detected_shop_label = ttk.Label(
            controls_panel, text="", foreground="green", font=self.font_bold
        )
        self.detected_shop_label.grid(
            row=control_row, column=0, sticky="ew", padx=12, pady=(0, 2)
        )
        control_row += 1

        # Shop buttons frame
        shop_frame = ttk.LabelFrame(controls_panel, text="")
        shop_frame.grid(row=control_row, column=0, sticky="ew", padx=12, pady=5)
        shop_frame.columnconfigure(0, weight=1)
        control_row += 1

        # --- Action Buttons ---
        action_hint = ttk.Label(
            controls_panel,
            text="After scan: press 'Fill Selected' to fill the selected shop",
            font=self.font_label,
        )
        action_hint.grid(row=control_row, column=0, sticky="ew", padx=12, pady=(6, 0))
        control_row += 1

        action_frame = ttk.LabelFrame(controls_panel, text="")
        action_frame.grid(row=control_row, column=0, sticky="ew", padx=12, pady=5)
        action_frame.columnconfigure(0, weight=1)
        action_frame.columnconfigure(1, weight=1)
        action_frame.columnconfigure(2, weight=1)
        control_row += 1

        # Style for selected/pressed buttons
        # Use tk.Button on macOS, ttk.Button on Linux
        self._style = ttk.Style()
        self._use_tk_buttons = MAC  # Use the MAC flag instead of platform detection
        if not self._use_tk_buttons:
            # Configure fonts for ttk on Linux using font objects
            try:
                self._style.configure("TButton", font=self.font_button)
                self._style.configure("TLabel", font=self.font_label)
                self._style.configure("TLabelFrame", font=self.font_label)
                self._style.configure("TRadiobutton", font=self.font_label)
                self._style.configure("TEntry", font=self.font_label)
                self._style.configure("TFrame", font=self.font_label)
                self._style.configure(
                    "Selected.TButton", background="#b7ebc6", font=self.font_button
                )
                self._style.configure(
                    "Pressed.TButton", background="#d6f0ff", font=self.font_button
                )
                self._style.configure(
                    "Ambiguous.TButton", background="#ffd59e", font=self.font_button
                )
            except Exception:
                pass

        # Action buttons (Fill Selected, Copy Card, Reset Camera)
        self.fill_selected_btn = ttk.Button(
            action_frame,
            text="Fill Selected",
            command=lambda: (
                self._flash_button(self.fill_selected_btn),
                self._fill_selected_shop(),
            ),
        )
        self.fill_selected_btn.grid(row=0, column=0, sticky="ew", padx=2)

        self.copy_card_btn = ttk.Button(
            action_frame,
            text="Copy Card #",
            command=lambda: (
                self._flash_button(self.copy_card_btn),
                self._copy_card_number(),
            ),
            state="disabled",
        )
        self.copy_card_btn.grid(row=0, column=1, sticky="ew", padx=2)

        self.reset_camera_btn = ttk.Button(
            action_frame,
            text="Reset Camera",
            command=lambda: (
                self._flash_button(self.reset_camera_btn),
                self._reset_camera(),
            ),
        )
        self.reset_camera_btn.grid(row=0, column=2, sticky="ew", padx=2)

        # --- Shop Buttons Creation ---
        self.shop_buttons = []
        self.shop_button_frames = {}  # Store frames for styling

        shop_button_row = 0
        for name, config in SHOPS.items():
            text = f"{name}"
            frame = None  # Initialize for later reference
            if self._use_tk_buttons:
                # macOS: Use frame as background indicator + button inside
                frame = tk.Frame(
                    shop_frame,
                    bg="#E8E8E8",  # Normal gray background
                    relief="flat",
                    highlightthickness=2,
                    highlightbackground="#999999",
                )
                btn = tk.Button(
                    frame,
                    text=text,
                    bg="#E8E8E8",
                    fg="black",
                    activebackground="#D0D0D0",
                    relief="flat",
                    bd=0,
                    state="disabled",
                    font=self.font_button,
                    padx=8,
                    pady=4,
                    highlightthickness=0,
                )
                btn.pack(fill="both", expand=True, padx=2, pady=2)
                frame.grid(
                    row=shop_button_row // 2,
                    column=shop_button_row % 2,
                    sticky="ew",
                    padx=2,
                    pady=2,
                )
            else:
                # Linux: Use ttk.Button
                btn = ttk.Button(shop_frame, text=text, style="TButton")
                btn.grid(
                    row=shop_button_row // 2,
                    column=shop_button_row % 2,
                    sticky="ew",
                    padx=2,
                    pady=2,
                )
                btn.state(["disabled"])

            shop_button_row += 1

            btn._orig_text = text
            btn._shop_name = name
            btn._frame = frame if self._use_tk_buttons else None
            # Selecting a shop (does not open browser yet)
            btn.config(command=lambda n=name, b=btn: self._select_shop(n, b))
            self.shop_buttons.append(btn)
            if self._use_tk_buttons:
                self.shop_button_frames[name] = (frame, btn)

        # Configure shop buttons grid
        shop_frame.columnconfigure(0, weight=1)
        shop_frame.columnconfigure(1, weight=1)

        # Store main_frame for compatibility (no longer used but kept for reference)
        self.main_frame = controls_panel

        # State
        self.picture_mode = False  # Will be set to True only when actively frozen
        self.frozen_frame = None
        self.last_boxes = []
        self.last_label = ""
        self._driver = None
        self._shop_windows = {}

        # Trace card number changes to enable/disable copy button and shop buttons
        def _on_code_change(*args):
            has_code = bool(self.code.get().strip())
            if has_code:
                self._enable_button(self.copy_card_btn)
                for btn in self.shop_buttons:
                    self._enable_button(btn)
            else:
                self._disable_button(self.copy_card_btn)
                for btn in self.shop_buttons:
                    self._disable_button(btn)

        self.code.trace_add("write", _on_code_change)

        # Scanning mode
        self.qr_mode = False  # False = Barcode mode, True = QR code mode

        # Live scanning state (for SCANNING_FLAG mode)
        self._last_scan_t = 0.0
        self._potential_code = ""
        self._potential_code_type = ""
        self._potential_code_count = 0
        self._stable_code = ""
        self._potential_pin = ""
        self._potential_pin_count = 0
        self._stable_pin = ""
        self.STABLE_THRESHOLD = STABLE_THRESHOLD
        self.scanning = True
        self._code_locked = (
            False  # True when code is detected and waiting for user action
        )
        self._frozen_frame = None  # Stores frozen frame when code is locked
        self._lock_time = 0.0  # Time when code was locked
        if SCANNING_FLAG:
            self.update_frame()
        else:
            self.update_live_video()

    def _validate_and_correct_code(self, shop: str, digits: str) -> tuple:
        """Validate and correct code digits for a specific shop.

        Returns: (is_valid, corrected_digits, original_length)
        """
        n = len(digits)
        if shop == "REWE":
            if n == 13:
                return (True, digits, n)
            if n == 39:
                # to get 13 first digits
                corrected = digits[:13]
                return (True, corrected, n)
            return (False, digits, n)
        if shop == "DM":
            if n == 24:
                return (True, digits, n)
            if n == 32:
                return (True, digits, n)
            return (False, digits, n)
        if shop in ("ALDI", "LIDL"):
            if n == 18:
                return (True, digits, n)
            if n == 20:
                return (True, digits, n)
            if n == 38:
                # drop first 18 digits to get 20
                corrected = digits[18:]
                return (True, corrected, n)
            if n == 36:
                # drop first 18 digits to get 18
                corrected = digits[18:]
                return (True, corrected, n)
            return (False, digits, n)
        if shop == "EDEKA":
            if n == 32:
                corrected = digits[11:16] + digits[18:]
                return (True, corrected, n)
            return (n == 19, digits, n)
        return (True, digits, n)

    def _apply_code_correction(self, shop: str):
        """Apply code correction for the given shop."""
        code_raw = self.code.get() or ""
        digits = "".join(ch for ch in code_raw if ch.isdigit())

        ok, corrected, _ = self._validate_and_correct_code(shop, digits)
        if ok and corrected != digits:
            self.code.set(corrected)

    def _select_shop(self, name, button):
        """Mark a shop as selected. Visual toggle on the button."""
        # Deselect previous (remove selected style)
        try:
            prev = getattr(self, "selected_shop_button", None)
            if prev and prev is not button:
                self._set_button_style(prev, "normal")
        except Exception:
            pass

        # Toggle selection
        if getattr(self, "selected_shop", None) == name:
            # Deselect: clear selection and reset styles for all shop buttons
            self.selected_shop = None
            try:
                for b in self.shop_buttons:
                    self._set_button_style(b, "normal")
            except Exception:
                pass
            self.selected_shop_button = None
            self._safe_status("Shop deselected", "blue")
        else:
            # Select this shop and set style green; reset others to default
            self.selected_shop = name
            self.selected_shop_button = button
            try:
                for b in self.shop_buttons:
                    try:
                        if getattr(b, "_shop_name", None) == name:
                            self._set_button_style(b, "selected")
                        else:
                            self._set_button_style(b, "normal")
                    except Exception:
                        pass
            except Exception:
                pass
            self._safe_status(f"Selected shop: {name}", "blue")
            # Apply code correction for this shop
            self._apply_code_correction(name)

    def _toggle_qr_mode(self):
        """Toggle between 1D Barcode and 2D Code (QR/Data Matrix) detection modes."""
        self.qr_mode = not self.qr_mode
        mode_name = "2D Code (QR/DM)" if self.qr_mode else "Barcode (1D)"
        mode_text = "[2D]" if self.qr_mode else "[1D]"

        # Update button appearance
        self.qr_mode_btn.config(text=f"{mode_text} {mode_name}")
        self._flash_button(self.qr_mode_btn, ms=200)

        # Update status
        self._safe_status(f"Switched to {mode_name} Mode", "blue")

        # Reset scan state
        if SCANNING_FLAG:
            self.reset_scan()

    def _set_button_style(self, button, style_type):
        """Set button style: 'normal', 'selected', or 'ambiguous'."""
        if self._use_tk_buttons:
            # macOS: Style the frame around the button for visibility
            frame = button._frame
            if style_type == "selected":
                # Green for selected
                frame.config(
                    bg="#00CC00",
                    highlightbackground="#009900",
                    highlightcolor="#009900",
                )
                button.config(bg="#00CC00", font=self.font_button)
            elif style_type == "ambiguous":
                # Orange for ambiguous (needs manual choice)
                frame.config(
                    bg="#FF9900",
                    highlightbackground="#CC6600",
                    highlightcolor="#CC6600",
                )
                button.config(bg="#FF9900", font=self.font_button)
            else:  # normal
                # Gray for normal/disabled
                frame.config(
                    bg="#E8E8E8",
                    highlightbackground="#999999",
                    highlightcolor="#999999",
                )
                button.config(bg="#E8E8E8", font=self.font_button)
        else:
            # ttk styling for Linux/Windows
            if style_type == "selected":
                button.config(style="Selected.TButton")
            elif style_type == "ambiguous":
                button.config(style="Ambiguous.TButton")
            else:
                button.config(style="TButton")

    def _enable_button(self, button):
        """Enable a button (works for both tk.Button and ttk.Button)."""
        if self._use_tk_buttons:
            button.config(state="normal")
        else:
            button.state(["!disabled"])

    def _disable_button(self, button):
        """Disable a button (works for both tk.Button and ttk.Button)."""
        if self._use_tk_buttons:
            button.config(state="disabled")
        else:
            button.state(["disabled"])

    def _copy_card_number(self):
        """Copy the card number to clipboard and show brief confirmation."""
        card_num = self.code.get().strip()
        if not card_num:
            messagebox.showwarning("No card number", "No card number to copy.")
            return

        self.root.clipboard_clear()
        self.root.clipboard_append(card_num)
        self.root.update()  # Ensure clipboard is updated

        # Change button text to confirmation and restore after 1.5 seconds
        orig_text = self.copy_card_btn.cget("text")
        self.copy_card_btn.config(text="[OK] Copied!")
        self.root.after(1500, lambda: self.copy_card_btn.config(text=orig_text))

    def _flash_button(self, button, ms: int = 300):
        """Temporarily apply Pressed style to a button then revert."""
        try:
            if self._use_tk_buttons:
                orig_bg = button.cget("bg")
                button.config(bg="#d6f0ff")
                self.root.after(ms, lambda: button.config(bg=orig_bg))
            else:
                orig_style = (
                    button.cget("style") if "style" in button.keys() else "TButton"
                )
                button.config(style="Pressed.TButton")
                self.root.after(ms, lambda: button.config(style=orig_style))
        except Exception:
            pass

    def _show_lidl_warning(self):
        """Show LIDL warning dialog with copyable URL."""
        url = "https://www.lidl.de/c/lidl-geschenkkarten/s10007775"
        dialog = tk.Toplevel(self.root)
        dialog.title("LIDL not supported")
        dialog.geometry("500x250")
        dialog.resizable(False, False)

        # Make dialog modal
        dialog.transient(self.root)
        dialog.grab_set()

        # Message text
        message_frame = ttk.Frame(dialog, padding="10")
        message_frame.pack(fill="both", expand=False)

        ttk.Label(
            message_frame,
            text="LIDL's Friendly Captcha is blocking this code. The 'Open in Browser' will open another normal browser. Copy number on 'Copy Card' button. Later refresh window to paste another number",
            justify="left",
            font=self.font_label,
            wraplength=450,
        ).pack(anchor="w", fill="x", pady=(0, 10))

        # URL frame with copyable text
        url_frame = ttk.LabelFrame(
            dialog, text="LIDL URL (click to select, Ctrl+C to copy)", padding="5"
        )
        url_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        url_text = tk.Text(
            url_frame, height=2, width=60, wrap="word", font=self.font_label
        )
        url_text.pack(fill="both", expand=True)
        url_text.insert("1.0", url)
        url_text.config(state="disabled")  # Read-only but selectable

        # Button frame with two buttons
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill="x", padx=10, pady=10)

        ttk.Button(
            button_frame,
            text="Open in Browser",
            command=lambda: self._open_in_browser_right_third(url),
            width=15,
        ).pack(side="left", padx=5)

        ttk.Button(button_frame, text="OK", command=dialog.destroy, width=15).pack(
            side="left", padx=5
        )

    def _open_in_browser_right_third(self, url):
        """Open URL in default browser."""
        webbrowser.open(url)

    def _show_rewe_warning(self):
        """Show REWE warning dialog with copyable URL, mentioning slow Friendly Captcha."""
        url = "https://kartenwelt.rewe.de/rewe-geschenkkarte.html"
        dialog = tk.Toplevel(self.root)
        dialog.title("REWE - Manual Entry Required")
        dialog.geometry("500x300")
        dialog.resizable(False, False)

        # Make dialog modal
        dialog.transient(self.root)
        dialog.grab_set()

        # Message text
        message_frame = ttk.Frame(dialog, padding="10")
        message_frame.pack(fill="both", expand=False)

        ttk.Label(
            message_frame,
            text="REWE's Friendly Captcha is very slow. The 'Open in Browser' will open another normal browser. Copy number on 'Copy Card' button. Later refresh window to paste another number",
            justify="left",
            font=self.font_label,
            wraplength=450,
        ).pack(anchor="w", fill="x", pady=(0, 10))

        # URL frame with copyable text
        url_frame = ttk.LabelFrame(
            dialog, text="REWE URL (click to select, Ctrl+C to copy)", padding="5"
        )
        url_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        url_text = tk.Text(
            url_frame, height=2, width=60, wrap="word", font=self.font_label
        )
        url_text.pack(fill="both", expand=True)
        url_text.insert("1.0", url)
        url_text.config(state="disabled")  # Read-only but selectable

        # Button frame with two buttons
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill="x", padx=10, pady=10)

        ttk.Button(
            button_frame,
            text="Open in Browser",
            command=lambda: webbrowser.open(url),
            width=15,
        ).pack(side="left", padx=5)

        ttk.Button(button_frame, text="OK", command=dialog.destroy, width=15).pack(
            side="left", padx=5
        )

    def _fill_selected_shop(self):
        """Fill the selected shop's form in the browser using captured IDs."""
        if not getattr(self, "selected_shop", None):
            messagebox.showinfo("No shop selected", "Please select a shop first.")
            return

        # LIDL warning
        if self.selected_shop == "LIDL":
            self._show_lidl_warning()
            return

        # REWE warning (due to slow Friendly Captcha)
        if self.selected_shop == "REWE":
            self._show_rewe_warning()
            return

        cfg = SHOPS.get(self.selected_shop)
        if not cfg:
            messagebox.showerror("Shop Error", "Selected shop config not found.")
            return

        # Validate card number length according to shop rules
        code_raw = self.code.get() or ""
        digits = "".join(ch for ch in code_raw if ch.isdigit())

        ok, corrected_code, count = self._validate_and_correct_code(
            self.selected_shop, digits
        )
        if not ok:
            messagebox.showwarning(
                "Invalid code length",
                f"Detected {count} digits for {self.selected_shop}. Try again.",
            )
            return
        # If corrected (e.g., ALDI/LIDL 38->20), update the field
        if corrected_code != digits:
            self.code.set(corrected_code)
            digits = corrected_code

        # Ensure browser is started
        try:
            driver = self._ensure_driver()
        except Exception:
            # try to start browser manually
            self._manual_open_browser()
            # mark start button as active if driver available
            try:
                self.start_browser_btn.config(style="Selected.TButton")
            except Exception:
                pass

        # Now fill the form for the selected shop
        # call in background so GUI doesn't block
        threading.Thread(
            target=self._open_shop,
            args=(
                self.selected_shop,
                cfg["url"],
                cfg["card_selector"],
                cfg.get("pin_selector"),
                cfg.get("iframe_selector"),
            ),
            daemon=True,
        ).start()

    # ==================== Camera Control Methods ====================

    def _enable_v4l2_autofocus(self, camera_source: str):
        """
        Try to configure V4L2 focus for macro mode.
        Some cameras (like Logitech C270) have fixed focus and cannot be adjusted.
        """
        import platform
        import subprocess

        if platform.system() != "Linux":
            return

        try:
            # Convert camera_source to /dev/videoX path
            if camera_source.isdigit():
                device = f"/dev/video{camera_source}"
            else:
                print(
                    "[DEBUG] Not a USB device (likely IP camera), skipping V4L2 config"
                )
                return

            print(f"[DEBUG] Checking focus controls on {device}...")

            try:
                # List all available controls
                result = subprocess.run(
                    ["v4l2-ctl", "-d", device, "--list-ctrls"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )

                controls_output = result.stdout.lower()

                # Check if any focus controls exist
                focus_keywords = ["focus", "auto_focus", "af_"]
                has_focus_control = any(
                    keyword in controls_output for keyword in focus_keywords
                )

                if not has_focus_control:
                    print(
                        f"[DEBUG] ✓ Camera has fixed focus (no adjustable focus controls)"
                    )
                    print(f"[DEBUG] Position camera ~10cm from barcode for best focus")
                    return

                print(
                    "[DEBUG] Found focus controls, attempting to enable macro mode..."
                )

                # Try different focus control names
                focus_commands = [
                    ("focus_absolute", "10"),
                    ("focus_distance", "0"),
                    ("focus_mode", "0"),
                ]

                for control_name, value in focus_commands:
                    if control_name.lower() in controls_output:
                        try:
                            ret = subprocess.run(
                                [
                                    "v4l2-ctl",
                                    "-d",
                                    device,
                                    "-c",
                                    f"{control_name}={value}",
                                ],
                                capture_output=True,
                                timeout=2,
                            )
                            if ret.returncode == 0:
                                print(
                                    f"[DEBUG] ✓ Set {control_name}={value} (macro mode)"
                                )
                                return
                        except Exception:
                            pass

            except FileNotFoundError:
                print("[DEBUG] v4l2-ctl not found. Install: sudo apt install v4l-utils")
            except subprocess.TimeoutExpired:
                pass
            except Exception as e:
                print(f"[DEBUG] Error checking focus controls: {e}")

        except Exception as e:
            print(f"[DEBUG] V4L2 focus configuration failed: {e}")

    def _reset_camera(self):
        """Reset/reconnect the camera connection."""
        self._safe_status("[...] Resetting camera...", "orange")
        try:
            self.root.update()
        except Exception:
            pass

        try:
            # Release current connection
            if hasattr(self, "cap") and self.cap:
                try:
                    self.cap.release()
                except Exception as e:
                    print(f"Warning: Could not release camera: {e}")

            # Small delay before reconnecting
            time.sleep(0.5)

            # Reconnect
            self.cap = create_capture(self.camera_source)
            if not self.cap.isOpened():
                try:
                    messagebox.showerror(
                        "Camera Error", "Could not reconnect to camera."
                    )
                except Exception:
                    pass
                self._safe_status("[ERR] Camera connection failed", "red")
                return

            # Set camera properties again
            try:
                actual_w, actual_h = set_optimal_resolution(self.cap)
                self.actual_width = actual_w
                self.actual_height = actual_h
                self.cap.set(cv2.CAP_PROP_FPS, 20)
                self.cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)
                # Re-enable V4L2 autofocus on reconnect
                self._enable_v4l2_autofocus(self.camera_source)
            except Exception as e:
                print(f"Warning: Could not set camera properties: {e}")

            self._safe_status("[OK] Camera reconnected - Ready to capture", "green")

            # For LAPTOP_CAM, also reset scanning state
            if LAPTOP_CAM:
                try:
                    self.reset_scan()
                except Exception as e:
                    print(f"Warning: Could not reset scan: {e}")

            # Enable Take Picture button if it exists
            try:
                if hasattr(self, "take_picture_btn") and self.take_picture_btn:
                    self.take_picture_btn.state(["!disabled"])
            except Exception:
                pass

        except Exception as e:
            try:
                messagebox.showerror("Camera Error", f"Failed to reset camera: {e}")
            except Exception:
                pass
            self._safe_status("[ERR] Camera reset failed", "red")

    # ==================== Picture Capture Methods ====================

    def _take_picture(self):
        """Capture current frame and process it."""
        try:
            ok, frame = self.cap.read()
            if not ok:
                self._safe_status("[ERR] Failed to capture picture", "red")
                return
        except Exception as e:
            print(f"Error reading from camera: {e}")
            self._safe_status("[ERR] Camera read error", "red")
            return

        # Scale frame to half size for Barcode mode, keep full resolution for QR mode
        if not self.qr_mode:
            frame = cv2.resize(frame, (frame.shape[1] // 2, frame.shape[0] // 2))

        # Store frozen frame
        self.frozen_frame = frame.copy()
        self.picture_mode = True

        # Update button states
        try:
            if hasattr(self, "take_picture_btn") and self.take_picture_btn:
                self.take_picture_btn.state(["disabled"])
        except Exception:
            pass

        self._safe_status("[...] Processing image...", "orange")

        # Process the image asynchronously so the GUI remains responsive
        threading.Thread(target=self._process_frozen_frame, daemon=True).start()
        # Ensure the UI doesn't stay frozen longer than 2 seconds
        try:
            self.root.after(2000, self._auto_unfreeze)
        except Exception:
            pass

    def _new_scan(self):
        """Clear results and return to live video mode."""
        self.picture_mode = False
        self.frozen_frame = None
        self.last_boxes = []
        self.last_label = ""

        # Clear text fields
        self.code.set("")
        self.pin.set("")

        # Clear detected shop label
        try:
            self.detected_shop_label.config(text="", foreground="blue")
        except Exception:
            pass

        # Update button states
        try:
            if (
                hasattr(self, "take_picture_btn")
                and self.take_picture_btn.winfo_exists()
            ):
                self.take_picture_btn.state(["!disabled"])
        except Exception:
            pass
        for btn in self.shop_buttons:
            try:
                if hasattr(btn, "winfo_exists") and btn.winfo_exists():
                    self._disable_button(btn)
            except Exception:
                pass

        self._safe_status("Live video - Ready to capture", "blue")

        # Resume live video
        self.update_live_video()

    def _auto_unfreeze(self):
        """Automatically exit picture mode after a short timeout.

        If the user didn't resume or processing hasn't finished, force return
        to live preview to avoid a permanent freeze.
        """
        if not getattr(self, "picture_mode", False):
            return

        # Reset state and UI
        self.picture_mode = False
        self.frozen_frame = None
        try:
            self.take_picture_btn.state(["!disabled"])
        except Exception:
            pass

        self._safe_status("Live video - Ready to capture", "blue")
        try:
            self.update_live_video()
        except Exception:
            pass

    def _process_frozen_frame(self):
        """Scan and extract codes from the frozen frame."""
        if self.frozen_frame is None:
            return

        h, w = self.frozen_frame.shape[:2]
        roi = self._compute_roi_rect(w, h)
        x0, y0, x1, y1 = roi
        crop = self.frozen_frame[y0:y1, x0:x1]

        # Scan the cropped region
        decoded_dict = self._scan_1d(crop)
        card_info = decoded_dict.get("card")
        pin_info = decoded_dict.get("pin")

        # Try rotated if card not found
        if not card_info:
            crop_rot = cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE)
            if self.qr_mode and QR_DECODER_ENABLED:
                # Try QR code detection on rotated image
                decoded_dict_rot = self._scan_1d_qr(crop_rot)
                card_info = decoded_dict_rot.get("card")
            else:
                # Try barcode detection on rotated image
                decoded_rot = self._scan_barcodes_only(crop_rot)
                if decoded_rot:
                    txt, sym, poly = decoded_rot[0]
                    H, W = crop_rot.shape[:2]
                    poly = np.array(poly, dtype=np.int32)
                    poly_back = np.stack([poly[:, 1], W - 1 - poly[:, 0]], axis=1)
                    card_info = (txt, sym, poly_back.tolist())

        # Update UI with results
        if card_info:
            txt, sym, poly = card_info
            self.code.set(txt)

            poly_np = np.array(poly, dtype=np.int32)
            if poly_np.ndim == 2 and poly_np.shape[1] == 2:
                poly_np[:, 0] += x0
                poly_np[:, 1] += y0
                self.last_boxes = [(poly_np, BOX_COLOR, f"{sym}")]

            status_text = f"[OK] Found {sym}: {txt}"

            if pin_info:
                pin_txt, _, _ = pin_info
                self.pin.set(pin_txt)
                status_text += f" | PIN: {pin_txt}"
                self.last_label = f"{txt} | PIN: {pin_txt}"
            else:
                self.last_label = txt

            self._safe_status(status_text, "green")

            # Enable shop buttons
            for btn in self.shop_buttons:
                self._enable_button(btn)
            # Auto-select shop when unambiguous (except ALDI/LIDL require manual choice)
            try:
                # extract digits from code text
                digits_only = "".join(ch for ch in txt if ch.isdigit())
                n = len(digits_only)
                candidates = []
                if n == 13 or n == 39:
                    candidates = ["REWE"]
                elif n == 24 or n == 32:
                    candidates = ["DM"]
                elif n == 16:
                    candidates = ["EDEKA"]
                elif n == 18:
                    candidates = ["LIDL"]
                elif n == 20 or n == 36 or n == 38:
                    # ALDI and LIDL both accept 20 (or 38 -> drop first 18)
                    candidates = ["ALDI", "LIDL"]
                if len(candidates) == 1:
                    shop_to_select = candidates[0]
                    # set selection and style
                    self.selected_shop = shop_to_select
                    # update previous selection style
                    try:
                        prev = getattr(self, "selected_shop_button", None)
                        if prev and prev._shop_name != shop_to_select:
                            self._set_button_style(prev, "normal")
                    except Exception:
                        pass
                    for b in self.shop_buttons:
                        try:
                            if getattr(b, "_shop_name", None) == shop_to_select:
                                self._set_button_style(b, "selected")
                                self.selected_shop_button = b
                            else:
                                self._set_button_style(b, "normal")
                        except Exception:
                            pass
                    self.status.config(
                        text=f"Auto-selected shop: {shop_to_select}", foreground="green"
                    )
                    # Update detected shop label
                    try:
                        self.detected_shop_label.config(
                            text=f"✅ Detected: {shop_to_select}", foreground="green"
                        )
                    except Exception:
                        pass
                    # Apply code correction for auto-detected shop
                    self._apply_code_correction(shop_to_select)
                elif len(candidates) > 1:
                    # ambiguous ALDI/LIDL - require manual choice
                    # mark both ALDI and LIDL buttons as ambiguous (orange)
                    try:
                        for b in self.shop_buttons:
                            if getattr(b, "_shop_name", None) in ("ALDI", "LIDL"):
                                self._set_button_style(b, "ambiguous")
                            else:
                                self._set_button_style(b, "normal")
                    except Exception:
                        pass
                    self.status.config(
                        text=f"Ambiguous shop (ALDI/LIDL). Please choose.",
                        foreground="orange",
                    )
                    # Update detected shop label
                    try:
                        self.detected_shop_label.config(
                            text="⚠️ Ambiguous: ALDI or LIDL - Please choose",
                            foreground="orange",
                        )
                    except Exception:
                        pass
                else:
                    # no match
                    self.status.config(
                        text=f"Detected {n} digits — no matching shop. Try again.",
                        foreground="red",
                    )
                    # Update detected shop label
                    try:
                        self.detected_shop_label.config(
                            text=f"❌ No shop found for {n} digits", foreground="red"
                        )
                    except Exception:
                        pass
            except Exception:
                pass
            beep()
        else:
            self.status.config(
                text="❌ No barcode/code found in picture", foreground="red"
            )
            self.last_boxes = []
            self.last_label = ""

        # Display the processed frozen frame
        self._display_frozen_frame()

    def _display_frozen_frame(self):
        """Display the frozen frame with overlays."""
        if self.frozen_frame is None:
            return

        vis = self.frozen_frame.copy()

        # Compute ROI on ORIGINAL frame dimensions before scaling
        h_orig, w_orig = vis.shape[:2]
        roi = self._compute_roi_rect(w_orig, h_orig)

        # Scale frame to fit display
        vis = self._scale_frame_to_display(vis)

        # Scale ROI coordinates if frame was scaled for display
        if self._last_scale_factor != 1.0:
            roi = tuple(int(c * self._last_scale_factor) for c in roi)

        # Scale box coordinates if frame was scaled
        scaled_boxes = []
        if self._last_scale_factor != 1.0:
            for box, color, label in self.last_boxes:
                scaled_box = (box * self._last_scale_factor).astype(np.int32)
                scaled_boxes.append((scaled_box, color, label))
        else:
            scaled_boxes = self.last_boxes

        # Draw overlays
        success = bool(self.code.get())
        self._draw_scanner_overlay(vis, roi, success=success)
        self._draw_boxes(vis, scaled_boxes, self.last_label)

        # Convert and display
        rgb = cv2.cvtColor(vis, cv2.COLOR_BGR2RGB)
        img = ImageTk.PhotoImage(Image.fromarray(rgb))
        self.label.configure(image=img)
        self.label.image = img

    # ==================== Live Video Methods ====================

    def update_live_video(self):
        """Update live video feed (no processing)."""
        if self.picture_mode:
            return

        ok, frame = self.cap.read()
        if not ok:
            self.root.after(30, self.update_live_video)
            return

        # Scale frame to half size for Barcode mode, keep full resolution for QR mode
        if not self.qr_mode:
            frame = cv2.resize(frame, (frame.shape[1] // 2, frame.shape[0] // 2))

        # Compute ROI on ORIGINAL frame dimensions before scaling
        h_orig, w_orig = frame.shape[:2]
        roi = self._compute_roi_rect(w_orig, h_orig)

        # Scale frame to fit display
        frame = self._scale_frame_to_display(frame)

        # Scale ROI coordinates if frame was scaled for display
        if self._last_scale_factor != 1.0:
            roi = tuple(int(c * self._last_scale_factor) for c in roi)

        # Draw overlay (no scanning)
        vis = frame.copy()
        self._draw_scanner_overlay(vis, roi, success=False)

        # Display
        rgb = cv2.cvtColor(vis, cv2.COLOR_BGR2RGB)
        img = ImageTk.PhotoImage(Image.fromarray(rgb))
        self.label.configure(image=img)
        self.label.image = img

        self.root.after(30, self.update_live_video)

    # ==================== Scanning Methods ====================
    def _scan_1d(self, bgr):
        """Wrapper to call appropriate scan method based on mode."""
        if self.qr_mode and QR_DECODER_ENABLED:
            return self._scan_1d_qr(bgr)
        else:
            return self._scan_1d_barcode(bgr)

    def _scan_1d_qr(self, bgr):
        """2D barcode scanning: supports QR codes and Data Matrix.

        Uses ZXing (primary), OpenCV QRCodeDetector, and pylibdmtx as fallback.
        """
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # Upscale if too small for reliable QR detection
        MIN_SIZE = 200
        if w < MIN_SIZE or h < MIN_SIZE:
            scale = max(MIN_SIZE / w, MIN_SIZE / h)
            bgr = cv2.resize(bgr, (int(w * scale), int(h * scale)), cv2.INTER_CUBIC)
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)), cv2.INTER_CUBIC)
            print(f"[UPSCALE] {w}x{h} -> {bgr.shape[1]}x{bgr.shape[0]}")

        # METHOD 0: ZXing (most robust, try first on original)
        if ZXING_AVAILABLE:
            try:
                print("[ZXing] Trying ZXing detector...")
                res = zxingcpp.read_barcodes(bgr)
                if res:
                    r = res[0]
                    text = r.text.strip() if hasattr(r, "text") else None
                    format_name = r.format.name if hasattr(r, "format") else "UNKNOWN"
                    if text and len(text) > 0:
                        print(f"[ZXing SUCCESS] {format_name}: {text[:50]}")
                        return {"card": (text, format_name, []), "pin": None}
            except Exception as e:
                print(f"[ZXing] Error: {type(e).__name__}")

        def _try_decode(img, name=""):
            """Try QR and Data Matrix decoding."""
            # METHOD 1: OpenCV QR Code
            try:
                detector = cv2.QRCodeDetector()
                data, points, _ = detector.detectAndDecode(img)

                if data and len(data) > 0:
                    print(f"[CV_QR SUCCESS] {name}: {data[:50]}")
                    poly = (
                        [(int(p[0]), int(p[1])) for p in points[0]]
                        if points is not None and len(points) > 0
                        else []
                    )
                    return (data.strip(), "QRCODE", poly)
            except Exception:
                pass

            # METHOD 2: Data Matrix (pylibdmtx)
            try:
                from pylibdmtx.pylibdmtx import decode as dm_decode
                from PIL import Image as PILImage

                if len(img.shape) == 2:
                    pil_img = PILImage.fromarray(img)
                else:
                    pil_img = PILImage.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

                results = dm_decode(pil_img)

                if results and len(results) > 0:
                    for r in results:
                        txt = r.data.decode("utf-8", errors="replace").strip()
                        if txt and len(txt) > 0:
                            print(f"[DATA MATRIX SUCCESS] {name}: {txt[:50]}")
                            rect = r.rect
                            poly = [
                                (rect.left, rect.top),
                                (rect.left + rect.width, rect.top),
                                (rect.left + rect.width, rect.top + rect.height),
                                (rect.left, rect.top + rect.height),
                            ]
                            return (txt, "DATAMATRIX", poly)

            except ImportError:
                if not hasattr(_try_decode, "_warned_dmtx"):
                    print(
                        "[WARNING] pylibdmtx not installed - Data Matrix codes won't work"
                    )
                    _try_decode._warned_dmtx = True
            except Exception as e:
                pass

            return None

        # Try preprocessing variants
        # 1) ORIGINAL GRAYSCALE
        result = _try_decode(gray, "02_grayscale")
        if result:
            return {"card": result, "pin": None}

        # 2) MEDIAN BLUR
        median = cv2.medianBlur(gray, 3)
        result = _try_decode(median, "03_median")
        if result:
            return {"card": result, "pin": None}

        # 3) GENTLE CLAHE
        clahe = cv2.createCLAHE(clipLimit=1.2, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        result = _try_decode(enhanced, "04_CLAHE")
        if result:
            return {"card": result, "pin": None}

        # 4) BINARY OTSU THRESHOLD
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        result = _try_decode(binary, "05_binary")
        if result:
            return {"card": result, "pin": None}

        # 5) ADAPTIVE GAUSSIAN THRESHOLD (handles variable lighting)
        adaptive = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
        result = _try_decode(adaptive, "06_adaptive")
        if result:
            return {"card": result, "pin": None}

        # 6) MULTIPLE SCALES (upscaling for better QR resolution)
        h, w = gray.shape
        for scale in [1.5, 2.0]:
            resized = cv2.resize(gray, (int(w * scale), int(h * scale)))
            result = _try_decode(resized, f"07_scale_{scale}x")
            if result:
                return {"card": result, "pin": None}

        # 7) MEDIAN + CLAHE COMBINATION (for difficult lighting)
        median_enhanced = clahe.apply(median)
        result = _try_decode(median_enhanced, "08_median_CLAHE")
        if result:
            return {"card": result, "pin": None}

        # 8) ROTATIONS (QR codes might be sideways/upside-down)
        for angle in [90, 180, 270]:
            if angle == 90:
                rotated = cv2.rotate(gray, cv2.ROTATE_90_CLOCKWISE)
            elif angle == 180:
                rotated = cv2.rotate(gray, cv2.ROTATE_180)
            else:
                rotated = cv2.rotate(gray, cv2.ROTATE_90_COUNTERCLOCKWISE)

            result = _try_decode(rotated, f"09_rotation_{angle}")
            if result:
                return {"card": result, "pin": None}

        print(f"[DEBUG] No QR codes found. Check images in {debug_dir}")
        return {"card": None, "pin": None}

    def _scan_1d_barcode(self, bgr):
        """Optimized scanning for barcodes (with preprocessing)."""
        import cv2, numpy as np
        from pyzbar.pyzbar import decode
        import pytesseract

        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

        # -----------------------
        # 1) BARCODE - Build preprocessing candidates
        # -----------------------
        blurred = cv2.GaussianBlur(gray, (0, 0), 1.0)
        enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        sharp = cv2.addWeighted(enhanced, 1.0 + 1.4, blurred, -1.4, 0)

        kx = max(3, 21 | 1)
        ky = max(1, 3 | 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kx, ky))
        closed = cv2.morphologyEx(sharp, cv2.MORPH_CLOSE, kernel, iterations=1)

        # Build candidate list
        candidates = []
        candidates.append(("gray", gray))
        candidates.append(("enhanced", enhanced))
        candidates.append(("sharp", sharp))
        candidates.append(("closed", closed))

        # Binary thresholding variants
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        candidates.append(("binary", binary))

        _, inv_binary = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )
        candidates.append(("inv_binary", inv_binary))

        adaptive = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
        candidates.append(("adaptive", adaptive))

        # FIRST PASS: Try all candidates normally (catches QR codes in binary)
        for name, img in candidates:
            results = decode(img, symbols=SYMBOLS)
            if results:
                r = results[0]
                txt = r.data.decode("utf-8", errors="replace").strip()
                poly = [(p.x, p.y) for p in getattr(r, "polygon", [])] or []
                return {"card": (txt, r.type, poly), "pin": None}

        # SECOND PASS: Try scaling on best candidates
        best_for_scaling = ["binary", "sharp", "closed"]
        for name, img in candidates:
            if name in best_for_scaling:
                results = self._try_multiple_scales(img)
                if results:
                    r = results[0]
                    txt = r.data.decode("utf-8", errors="replace").strip()
                    poly = [(p.x, p.y) for p in getattr(r, "polygon", [])] or []
                    return {"card": (txt, r.type, poly), "pin": None}

        # THIRD PASS: Try rotation on binary variants
        best_for_rotation = ["binary", "inv_binary"]
        for name, img in candidates:
            if name in best_for_rotation:
                results = self._try_rotations(img)
                if results:
                    r = results[0]
                    txt = r.data.decode("utf-8", errors="replace").strip()
                    poly = [(p.x, p.y) for p in getattr(r, "polygon", [])] or []
                    return {"card": (txt, r.type, poly), "pin": None}

        # -----------------------
        # 3) OCR fallback for multi-line numeric ID
        # -----------------------
        if OCR_SWITCH:
            h, w = gray.shape
            # Large crop because number layouts vary
            roi = gray[int(0.30 * h) : int(0.98 * h), int(0.03 * w) : int(0.97 * w)]

            # --- candidates for iterative OCR ---
            transforms = [
                lambda x: x,
                lambda x: cv2.bilateralFilter(x, 9, 40, 40),
                lambda x: cv2.GaussianBlur(x, (5, 5), 0),
                lambda x: cv2.adaptiveThreshold(
                    x, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 35, 10
                ),
                lambda x: cv2.adaptiveThreshold(
                    x, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, 8
                ),
                lambda x: cv2.threshold(x, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[
                    1
                ],
                lambda x: cv2.medianBlur(x, 3),
                lambda x: cv2.resize(
                    x, None, fx=2.2, fy=2.2, interpolation=cv2.INTER_CUBIC
                ),
            ]

            def run_ocr(img):
                txt = pytesseract.image_to_string(
                    img, config="--psm 6 --oem 3 -c tessedit_char_whitelist=0123456789"
                )
                lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
                nums = ["".join(ch for ch in ln if ch.isdigit()) for ln in lines]
                nums = [n for n in nums if MIN_OCR_DIGITS <= len(n) <= MAX_OCR_DIGITS]
                if nums:
                    return max(nums, key=len)
                return None

            # Try sequential transforms until one produces a valid ID
            best = None
            img = roi.copy()
            for t in transforms:
                try:
                    mod = t(img)
                    if mod.ndim == 3:
                        mod = cv2.cvtColor(mod, cv2.COLOR_BGR2GRAY)
                    n = run_ocr(mod)
                    if n:
                        best = n
                        break
                except:
                    continue

            if best:
                poly = [(0, 0), (w, 0), (w, h), (0, h)]
                return {"card": (best, "OCR", poly), "pin": None}

        return {"card": None, "pin": None}

    def _scan_1d_and_PIN(self, bgr):
        # ---------------------
        # 1) BARCODE BRANCH
        # ---------------------
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

        clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP, tileGridSize=CLAHE_TILE)
        enhanced = clahe.apply(gray)
        blurred = cv2.GaussianBlur(enhanced, (0, 0), UNSHARP_SIGMA)
        sharp = cv2.addWeighted(
            enhanced, 1.0 + UNSHARP_AMOUNT, blurred, -UNSHARP_AMOUNT, 0
        )

        kx = max(3, MORPH_KERNEL_W | 1)
        ky = max(1, MORPH_KERNEL_H | 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kx, ky))
        closed = cv2.morphologyEx(sharp, cv2.MORPH_CLOSE, kernel, iterations=MORPH_ITER)

        results = decode(closed, symbols=SYMBOLS)
        if not results:
            results = decode(sharp, symbols=SYMBOLS)

        barcode_result = None
        if results:
            r = results[0]
            txt = r.data.decode("utf-8", errors="replace").strip()
            poly = [(p.x, p.y) for p in getattr(r, "polygon", [])] or []
            barcode_result = (txt, r.type, poly)

        # ---------------------
        # 2) OCR BRANCH
        # ---------------------
        # Crop lower half (numbers often below barcode, but layout varies)
        h, w = gray.shape
        roi = gray[int(0.45 * h) : int(0.98 * h), int(0.02 * w) : int(0.98 * w)]

        # Mild denoise + adaptive threshold
        roi_f = cv2.bilateralFilter(roi, 9, 40, 40)
        thr = cv2.adaptiveThreshold(
            roi_f, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 35, 10
        )

        raw = pytesseract.image_to_string(
            thr, config="--psm 6 --oem 3 -c tessedit_char_whitelist=0123456789"
        )

        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]

        # ---------------------
        # Extract PIN (exact length)
        # ---------------------
        pin = None
        for ln in lines:
            tokens = ln.split()
            hits = [t for t in tokens if len(t) == PIN_DIGITS and t.isdigit()]
            if hits:
                pin = (hits[0], "PIN", [(0, 0), (w, 0), (w, h), (0, h)])
                break

        # ---------------------
        # Extract Card/ID number (multi-line)
        # ---------------------
        # Strategy: find all numeric tokens >= MIN_OCR_DIGITS
        # If spread across several lines, join contiguous lines.
        candidates = []

        for ln in lines:
            tokens = [t for t in ln.split() if t.isdigit()]
            longtok = [t for t in tokens if len(t) >= MIN_OCR_DIGITS]
            candidates.extend(longtok)

        # Additional rule: join adjacent lines if each line contains numeric blocks
        if not candidates:
            numlines = []
            for ln in lines:
                numeric = "".join(ch for ch in ln if ch.isdigit())
                if numeric:
                    numlines.append(numeric)
            if len(numlines) >= 2:
                joined = "".join(numlines)
                if MIN_OCR_DIGITS <= len(joined) <= MAX_OCR_DIGITS:
                    candidates.append(joined)

        card = None
        if candidates:
            best = max(candidates, key=len)
            card = (best, "OCR", [(0, 0), (w, 0), (w, h), (0, h)])

        # If barcode succeeded, prefer barcode result for card ID
        final_card = barcode_result if barcode_result else card

        return {"card": final_card, "pin": pin}

    # ==================== Selenium Methods ====================

    def _manual_open_browser(self):
        """Manually open browser with all shop tabs."""

        def worker():
            try:
                self._status_async("Opening browser with all shop tabs…", "blue")
                driver = self._ensure_driver()
                # if successful, mark start button
                try:
                    self.start_browser_btn.config(style="Selected.TButton")
                except Exception:
                    pass
            except Exception as e:
                self._status_async(f"Error opening browser: {e}", "red")

        threading.Thread(target=worker, daemon=True).start()

    def _safe_status(self, text, color="blue"):
        """Safely update status label with error handling."""
        try:
            if hasattr(self, "status") and self.status and self.status.winfo_exists():
                txt = text if text is not None else ""
                if len(txt) > 120:
                    txt = txt[:117] + "..."
                self.status.config(text=txt, foreground=color)
        except Exception as e:
            print(f"Warning: Could not update status: {e}")

    def _status_async(self, text, color="blue"):
        def _apply():
            self._safe_status(text, color)

        try:
            if hasattr(self, "root") and self.root:
                self.root.after(0, _apply)
        except Exception as e:
            print(f"Warning: Could not schedule status update: {e}")

    def _ensure_driver(self):
        """Create/reuse WebDriver with anti-detection measures."""
        if not SELENIUM_AVAILABLE:
            raise RuntimeError("Selenium not installed")

        if self._driver is not None:
            try:
                _ = self._driver.current_url
                return self._driver
            except Exception:
                self._driver = None

        # Try Firefox first
        try:
            from selenium.webdriver.firefox.service import Service
            import os

            firefox_opts = webdriver.FirefoxOptions()

            # Auto-detect Firefox binary location (Snap vs apt)
            firefox_binary_paths = [
                "/snap/firefox/current/usr/lib/firefox/firefox",  # Snap
                "/usr/bin/firefox",  # apt/deb
                "/usr/lib/firefox/firefox",  # Alternative apt location
            ]

            firefox_binary = None
            for path in firefox_binary_paths:
                if os.path.exists(path):
                    firefox_binary = path
                    print(f"[DEBUG] Found Firefox at: {path}")
                    break

            if firefox_binary:
                firefox_opts.binary_location = firefox_binary

            # Anti-detection: hide webdriver
            firefox_opts.set_preference("dom.webdriver.enabled", False)
            firefox_opts.set_preference("media.peerconnection.enabled", False)
            firefox_opts.set_preference("privacy.trackingprotection.enabled", True)

            # Reduce CPU usage: disable unnecessary features
            firefox_opts.set_preference("browser.cache.disk.enable", False)
            firefox_opts.set_preference("browser.sessionstore.max_tabs_undo", 0)
            firefox_opts.set_preference("dom.max_script_run_time", 30)
            firefox_opts.set_preference("dom.disable_beforeunload", True)
            firefox_opts.set_preference("browser.tabs.drawInTitlebar", False)

            # Mimic real user agent
            if MAC:
                firefox_opts.set_preference(
                    "general.useragent.override",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                )
            else:  # linux
                firefox_opts.set_preference(
                    "general.useragent.override",
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                )

            # Disable WebGL and plugins that increase CPU load
            firefox_opts.set_preference("webgl.disabled", True)
            firefox_opts.set_preference("plugin.state.java", 0)
            firefox_opts.set_preference(
                "extensions.activeThemeID", "firefox-compact-light@mozilla.org"
            )

            # Create service with explicit geckodriver path
            geckodriver_paths = [
                "/usr/local/bin/geckodriver",
                "/usr/bin/geckodriver",
            ]

            geckodriver_path = None
            for path in geckodriver_paths:
                if os.path.exists(path):
                    geckodriver_path = path
                    print(f"[DEBUG] Found geckodriver at: {path}")
                    break

            if geckodriver_path:
                firefox_service = Service(executable_path=geckodriver_path)
                self._driver = webdriver.Firefox(
                    service=firefox_service, options=firefox_opts
                )
            else:
                # Fallback: let Selenium find geckodriver automatically
                self._driver = webdriver.Firefox(options=firefox_opts)

            # Set window width to one third of screen
            import time

            time.sleep(0.5)
            self._driver.set_window_size(
                self.middle_third_width, self._driver.get_window_size()["height"]
            )
            print(f"[DEBUG] Firefox window width set to: {self.middle_third_width}")

            # Execute stealth script to hide Selenium detection
            self._driver.execute_script(
                """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                """
            )

            self._status_async("✅ Started Firefox (anti-detection enabled)", "green")
            print("[DEBUG] Firefox driver created with anti-detection measures")

            # Open all shop tabs immediately after Firefox starts
            self._open_all_shop_tabs()
            try:
                self.start_browser_btn.config(style="Selected.TButton")
            except Exception:
                pass
            return self._driver

        except Exception as e:
            print(f"Firefox failed: {e}")
            import traceback

            traceback.print_exc()
            self._driver = None

        # If Firefox failed, try Chrome fallbacks
        # Try undetected-chromedriver first (best anti-detection)
        if self._driver is None and UNDETECTED_CHROME_AVAILABLE:
            try:
                options = uc.ChromeOptions()
                options.add_argument("--disable-blink-features=AutomationControlled")
                options.add_argument("--start-maximized")
                self._driver = uc.Chrome(options=options, version_main=None)

                # Set window width to one third of screen
                import time

                time.sleep(0.5)
                self._driver.set_window_size(
                    self.middle_third_width, self._driver.get_window_size()["height"]
                )
                print(
                    f"[DEBUG] Undetected Chrome window width set to: {self.middle_third_width}"
                )
                self._status_async(
                    "✅ Started undetected Chrome (anti-detection enabled)", "green"
                )
                print("[DEBUG] Undetected Chrome driver created")
                self._open_all_shop_tabs()
                try:
                    self.start_browser_btn.config(style="Selected.TButton")
                except Exception:
                    pass
                return self._driver
            except Exception as e:
                print(f"Undetected Chrome failed: {e}")
                self._driver = None

        # Fallback to regular Chrome with stealth config
        if self._driver is None:
            try:
                chrome_opts = webdriver.ChromeOptions()

                # Remove automation flags
                chrome_opts.add_experimental_option(
                    "excludeSwitches", ["enable-automation"]
                )
                chrome_opts.add_experimental_option("useAutomationExtension", False)
                chrome_opts.add_argument(
                    "--disable-blink-features=AutomationControlled"
                )

                # Mimic real user
                chrome_opts.add_argument("--start-maximized")
                chrome_opts.add_argument("--disable-dev-shm-usage")
                chrome_opts.add_argument("--no-sandbox")
                chrome_opts.add_argument(
                    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )

                self._driver = webdriver.Chrome(options=chrome_opts)

                # Set window width to one third of screen
                import time

                time.sleep(0.5)
                self._driver.set_window_size(
                    self.middle_third_width, self._driver.get_window_size()["height"]
                )
                print(f"[DEBUG] Chrome window width set to: {self.middle_third_width}")

                # Remove webdriver property
                self._driver.execute_cdp_cmd(
                    "Network.setUserAgentOverride",
                    {
                        "userAgent": self._driver.execute_script(
                            "return navigator.userAgent"
                        ).replace("Headless", "")
                    },
                )
                self._driver.execute_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )

                self._status_async("✅ Started Chrome with stealth config", "green")
                print("[DEBUG] Chrome driver created with stealth config")
                self._open_all_shop_tabs()
                try:
                    self.start_browser_btn.config(style="Selected.TButton")
                except Exception:
                    pass
                return self._driver
            except Exception as e:
                print(f"Chrome failed: {e}")
                self._driver = None

        # Try Safari as last resort
        if self._driver is None:
            try:
                self._driver = webdriver.Safari()
                self._status_async("✅ Started Safari", "green")
                print("[DEBUG] Safari driver created")
                self._open_all_shop_tabs()
                try:
                    self.start_browser_btn.config(style="Selected.TButton")
                except Exception:
                    pass
                return self._driver
            except Exception as e:
                print(f"Safari failed: {e}")
                raise RuntimeError("Could not start any browser") from e

    def _open_all_shop_tabs(self):
        """Open all shop URLs in separate tabs."""
        if not self._driver:
            print("[DEBUG] No driver available for opening tabs")
            return

        self._shop_windows = {}
        try:
            # Exclude LIDL and REWE (require manual handling)
            shops_list = [
                (name, cfg)
                for name, cfg in SHOPS.items()
                if name not in ("LIDL", "REWE")
            ]
            print(f"[DEBUG] Opening {len(shops_list)} shop tabs...")

            # Load first shop in main window
            first_shop_name, first_config = shops_list[0]
            print(
                f"[DEBUG] Loading first shop {first_shop_name} in main window: {first_config['url']}"
            )
            self._driver.get(first_config["url"])
            self._shop_windows[first_shop_name] = self._driver.current_window_handle
            print(
                f"[DEBUG] {first_shop_name} loaded, handle: {self._driver.current_window_handle}"
            )

            # Open remaining shops in new tabs
            for shop_name, config in shops_list[1:]:
                time.sleep(0.5)
                print(f"[DEBUG] Opening new tab for {shop_name}: {config['url']}")

                # On macOS/Firefox, use a more reliable method:
                # Execute script in current context, create new tab via window.open('')
                # then navigate it to the URL
                self._driver.execute_script("window.open('');")
                time.sleep(0.5)

                # Switch to the new tab (the last one)
                self._driver.switch_to.window(self._driver.window_handles[-1])
                time.sleep(0.3)

                # Now navigate this tab to the shop URL
                self._driver.get(config["url"])
                self._shop_windows[shop_name] = self._driver.current_window_handle
                print(
                    f"[DEBUG] {shop_name} opened, handle: {self._driver.current_window_handle}"
                )
                time.sleep(0.3)

            # Switch back to first tab
            self._driver.switch_to.window(self._driver.window_handles[0])
            self._status_async(f"✅ Opened {len(SHOPS)} shop tabs", "green")
            print(
                f"[DEBUG] Successfully opened all {len(self._shop_windows)} shop tabs: {list(self._shop_windows.keys())}"
            )
        except Exception as e:
            import traceback

            print(f"[DEBUG] Tab opening error: {e}")
            print(traceback.format_exc())
            self._status_async(f"Error opening tabs: {e}", "red")

    def _open_shop(
        self, site_name, url, card_selector, pin_selector=None, iframe_selector=None
    ):
        """Switch to shop tab and fill form."""
        code_text = self.code.get().strip()
        pin_text = self.pin.get().strip()

        if not code_text:
            self._safe_status("❌ No code to send", "red")
            return

        if pin_selector and not pin_text:
            pin_selector = None

        self._open_and_fill(
            url,
            card_selector,
            code_text,
            pin_selector,
            pin_text,
            site_name,
            iframe_selector,
        )

    def _open_and_fill(
        self,
        url,
        card_selector,
        code_text,
        pin_selector,
        pin_text,
        site_name,
        iframe_selector=None,
    ):
        """Fill form with anti-detection measures."""

        def worker():
            driver = None
            switched_to_iframe = False

            try:
                driver = self._ensure_driver()

                # Switch to shop tab
                if site_name in self._shop_windows:
                    try:
                        driver.switch_to.window(self._shop_windows[site_name])
                        # Refresh only for REWE (which uses simulate_human)
                        if site_name == "REWE":
                            driver.refresh()
                    except Exception:
                        driver.execute_script("window.open('');")
                        driver.switch_to.window(driver.window_handles[-1])
                        driver.get(url)
                        self._shop_windows[site_name] = driver.current_window_handle
                else:
                    driver.execute_script("window.open('');")
                    driver.switch_to.window(driver.window_handles[-1])
                    driver.get(url)
                    self._shop_windows[site_name] = driver.current_window_handle

                # Simulate human behavior only for shops that need it (e.g., REWE)
                shop_cfg = SHOPS.get(site_name, {})
                # DM doesn't need delays, other shops might need human-like delays
                if shop_cfg.get("simulate_human", False):
                    time.sleep(random.uniform(1.5, 3))
                    simulate_human_behavior(driver)
                else:
                    time.sleep(0.5)  # Brief delay for page load

                # Wait for potential CAPTCHA only for shops that need it (skip for DM)
                if site_name != "DM":
                    try:
                        wait_for_captcha(driver, timeout=10)
                    except Exception:
                        pass

                wait = WebDriverWait(driver, 30)

                # Switch to iframe if needed
                if iframe_selector:
                    try:
                        # Scroll down gradually to trigger lazy-loaded iframes (e.g. LIDL)
                        for scroll_y in [300, 600, 900, 1200]:
                            driver.execute_script(f"window.scrollTo(0, {scroll_y});")
                            time.sleep(0.4)
                        iframe = wait.until(
                            EC.visibility_of_element_located(
                                (By.CSS_SELECTOR, iframe_selector)
                            )
                        )
                        driver.execute_script(
                            "arguments[0].scrollIntoView(true);", iframe
                        )
                        time.sleep(0.5)
                        driver.switch_to.frame(iframe)
                        switched_to_iframe = True
                        time.sleep(random.uniform(0.5, 1))
                        # Dismiss any overlay inside the iframe (e.g. pca-the-messages cookie/consent banner)
                        try:
                            driver.execute_script(
                                """
                                var el = document.querySelector('pca-the-messages');
                                if (el) el.remove();
                            """
                            )
                        except Exception:
                            pass
                    except Exception as e:
                        self._status_async(
                            f"⚠️ Could not switch to iframe: {e}", "orange"
                        )

                # Fill card number with human-like typing or fast typing
                try:
                    field_card = wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, card_selector))
                    )

                    # Scroll element into view
                    driver.execute_script(
                        "arguments[0].scrollIntoView(true);", field_card
                    )

                    simulate_human = shop_cfg.get("simulate_human", False)

                    if simulate_human:
                        time.sleep(random.uniform(0.3, 0.6))
                        # Human-like interaction
                        human_move_and_click(driver, field_card)
                        time.sleep(random.uniform(0.2, 0.5))
                    else:
                        # Fast interaction for speed
                        fast_click(driver, field_card)

                    try:
                        field_card.clear()
                    except Exception:
                        pass

                    if simulate_human:
                        time.sleep(random.uniform(0.1, 0.3))
                        human_typing(field_card, code_text)
                    else:
                        fast_typing(field_card, code_text)

                    self._status_async(f"✓ Filled card number for {site_name}", "blue")

                except Exception as e:
                    self._status_async(f"❌ Could not fill card field: {e}", "red")
                    raise

                # Fill PIN if available
                if pin_selector and pin_text:
                    try:
                        simulate_human = shop_cfg.get("simulate_human", False)

                        if simulate_human:
                            time.sleep(random.uniform(0.5, 1.2))

                        field_pin = wait.until(
                            EC.presence_of_element_located(
                                (By.CSS_SELECTOR, pin_selector)
                            )
                        )

                        # Scroll into view
                        driver.execute_script(
                            "arguments[0].scrollIntoView(true);", field_pin
                        )

                        if simulate_human:
                            time.sleep(random.uniform(0.2, 0.5))
                            human_move_and_click(driver, field_pin)
                            time.sleep(random.uniform(0.2, 0.5))
                        else:
                            # Fast interaction for speed
                            fast_click(driver, field_pin)

                        try:
                            field_pin.clear()
                        except Exception:
                            pass

                        if simulate_human:
                            time.sleep(random.uniform(0.1, 0.3))
                            human_typing(field_pin, pin_text)
                        else:
                            fast_typing(field_pin, pin_text)

                        self._status_async(f"✓ Filled PIN for {site_name}", "blue")

                    except Exception as e:
                        self._status_async(f"⚠️ Could not fill PIN field: {e}", "orange")

                self._status_async(f"✅ Filled {site_name} form", "green")

            except Exception as e:
                self._status_async(f"❌ Error with {site_name}: {e}", "red")
                import traceback

                print(traceback.format_exc())

            finally:
                if switched_to_iframe and driver:
                    try:
                        driver.switch_to.default_content()
                    except Exception as e:
                        print(f"Warning: could not switch back from iframe: {e}")

        threading.Thread(target=worker, daemon=True).start()

    # ==================== Drawing Methods ====================

    def _compute_roi_rect(self, w, h):
        """Compute ROI rectangle. Square for QR mode (larger), rectangular for barcode mode."""
        if self.qr_mode:
            # QR mode: use larger square ROI (75%) for better QR detection at full resolution
            size = int(min(w, h) * QR_ROI_SIZE_FRAC)
            x0 = (w - size) // 2
            y0 = (h - size) // 2
            return x0, y0, x0 + size, y0 + size
        else:
            # Barcode mode: use rectangular ROI
            roi_h = int(h * ROI_HEIGHT_FRAC)
            roi_w = int(w * ROI_WIDTH_FRAC)
            x0 = (w - roi_w) // 2
            y0 = (h - roi_h) // 2
            return x0, y0, x0 + roi_w, y0 + roi_h

    def _scale_frame_to_display(self, frame):
        """Scale frame to fit the actual label widget dimensions (both width and height)."""
        h, w = frame.shape[:2]

        # Get actual label widget dimensions (or use minimums)
        try:
            label_width = self.label.winfo_width()
            label_height = self.label.winfo_height()
            if label_width <= 1:  # Widget not yet rendered
                label_width = 420
            if label_height <= 1:
                label_height = 400
        except Exception:
            label_width = 420
            label_height = 400

        # Calculate scale factors for both dimensions
        scale_w = label_width / w if w > label_width else 1.0
        scale_h = label_height / h if h > label_height else 1.0

        # Use the smaller scale factor to fit both dimensions
        scale = min(scale_w, scale_h)

        # Only resize if scaling down is needed
        if scale < 1.0:
            new_w = int(w * scale)
            new_h = int(h * scale)
            frame = cv2.resize(frame, (new_w, new_h))
            self._last_scale_factor = scale  # Store for coordinate scaling
        else:
            self._last_scale_factor = 1.0

        return frame

    def _draw_scanner_overlay(self, img, roi, success=False):
        x0, y0, x1, y1 = roi

        if success:
            cv2.rectangle(img, (x0, y0), (x1, y1), SUCCESS_COLOR, 4)
            overlay = img.copy()
            cv2.rectangle(overlay, (x0, y0), (x1, y1), SUCCESS_COLOR, -1)
            alpha = 0.25
            img[y0:y1, x0:x1] = cv2.addWeighted(
                overlay[y0:y1, x0:x1], alpha, img[y0:y1, x0:x1], 1 - alpha, 0
            )
        else:
            self._draw_dashed_rect(
                img, (x0, y0), (x1, y1), OVERLAY_COLOR, 2, DRAW_DASH_GAP
            )
            c, L, th = OVERLAY_COLOR, CORNER_LEN, 3
            cv2.line(img, (x0, y0), (x0 + L, y0), c, th)
            cv2.line(img, (x0, y0), (x0, y0 + L), c, th)
            cv2.line(img, (x1, y0), (x1 - L, y0), c, th)
            cv2.line(img, (x1, y0), (x1, y0 + L), c, th)
            cv2.line(img, (x0, y1), (x0 + L, y1), c, th)
            cv2.line(img, (x0, y1), (x0, y1 - L), c, th)
            cv2.line(img, (x1, y1), (x1 - L, y1), c, th)
            cv2.line(img, (x1, y1), (x1, y1 - L), c, th)

        overlay = img.copy()
        cv2.rectangle(overlay, (0, 0), (img.shape[1], img.shape[0]), (0, 0, 0), -1)

        cv2.rectangle(overlay, (x0, y0), (x1, y1), (0, 0, 0), -1)  # "punch hole"

        alpha = 0.20
        img[:] = cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0)

    def _draw_dashed_rect(self, img, p0, p1, color, thickness, gap):
        (x0, y0), (x1, y1) = p0, p1
        for x in range(x0, x1, gap * 2):
            cv2.line(img, (x, y0), (min(x + gap, x1), y0), color, thickness)
        for x in range(x0, x1, gap * 2):
            cv2.line(img, (x, y1), (min(x + gap, x1), y1), color, thickness)
        for y in range(y0, y1, gap * 2):
            cv2.line(img, (x0, y), (x0, min(y + gap, y1)), color, thickness)
        for y in range(y0, y1, gap * 2):
            cv2.line(img, (x1, y), (x1, min(y + gap, y1)), color, thickness)

    def _draw_boxes(self, img, items, label):
        for poly, color, typ in items:
            if poly is not None and len(poly) >= 4:
                pts = poly.reshape((-1, 1, 2))
                cv2.polylines(img, [pts], isClosed=True, color=color, thickness=2)
        if label:
            pad = 8
            txt = f"{label}"
            (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            cv2.rectangle(
                img,
                (10, 10),
                (10 + tw + 2 * pad, 10 + th + 2 * pad),
                (230, 255, 230),
                -1,
            )
            cv2.putText(
                img,
                txt,
                (10 + pad, 10 + th + pad - 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                TEXT_COLOR,
                2,
                cv2.LINE_AA,
            )

    # ---------------------- Live Scanning (SCANNING mode) ----------------------

    def update_frame(self):
        """Live scanning with stability threshold (SCANNING mode only)."""
        if not SCANNING_FLAG or not self.scanning:
            return

        ok, frame = self.cap.read()
        if not ok:
            self._safe_status("Camera read failed - retrying...", "red")
            self.root.after(20, self.update_frame)
            return

        # Scale frame to half size for Barcode mode, keep full resolution for QR mode
        if not self.qr_mode:
            frame = cv2.resize(frame, (frame.shape[1] // 2, frame.shape[0] // 2))

        h, w = frame.shape[:2]
        roi = self._compute_roi_rect(w, h)
        x0, y0, x1, y1 = roi
        vis = frame.copy()
        now = time.time()

        if (now - self._last_scan_t) * 1000.0 >= SCAN_EVERY_MS:
            self._last_scan_t = now
            crop = frame[y0:y1, x0:x1]

            # DEBUG: Check crop size
            crop_h, crop_w = crop.shape[:2]
            print(
                f"[DEBUG] Crop size: {crop_w}x{crop_h} | ROI: ({x0},{y0})-({x1},{y1})"
            )
            if crop_w < 50 or crop_h < 50:
                print(f"[WARNING] Crop too small for code detection!")

            decoded_dict = self._scan_1d(crop)
            card_info = decoded_dict.get("card")
            pin_info = decoded_dict.get("pin")

            # Rotated pass if *card* not found
            if not card_info:
                crop_rot = cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE)
                if self.qr_mode and QR_DECODER_ENABLED:
                    # Try QR code detection on rotated image
                    decoded_dict_rot = self._scan_1d_qr(crop_rot)
                    card_info = decoded_dict_rot.get("card")
                else:
                    # Try barcode detection on rotated image
                    decoded_rot = self._scan_barcodes_only(crop_rot)
                    if decoded_rot:
                        txt, sym, poly = decoded_rot[0]
                        H, W = crop_rot.shape[:2]
                        poly = np.array(poly, dtype=np.int32)
                        poly_back = np.stack([poly[:, 1], W - 1 - poly[:, 0]], axis=1)
                        card_info = (txt, sym, poly_back.tolist())

            # --- *** STABILITY LOGIC *** ---

            # --- 1. Handle Card Stability ---
            if card_info:
                txt, sym, poly = card_info
                if txt == self._potential_code:
                    self._potential_code_count += 1
                else:
                    self._potential_code = txt
                    self._potential_code_type = sym
                    self._potential_code_count = 1

                poly_np = np.array(poly, dtype=np.int32)
                if poly_np.ndim == 2 and poly_np.shape[1] == 2:
                    poly_np[:, 0] += x0
                    poly_np[:, 1] += y0
                    self.last_boxes = [(poly_np, BOX_COLOR, f"{sym}")]
                else:
                    self.last_boxes = []
            else:
                self._potential_code = ""
                self._potential_code_count = 0
                self.last_boxes = []

            # --- 2. Handle PIN Stability ---
            if pin_info:
                pin_txt, _, _ = pin_info
                if pin_txt == self._potential_pin:
                    self._potential_pin_count += 1
                else:
                    self._potential_pin = pin_txt
                    self._potential_pin_count = 1
            else:
                self._potential_pin = ""
                self._potential_pin_count = 0

            # --- 3. Check for Lock-in ---
            if self._potential_code_count >= self.STABLE_THRESHOLD:
                is_new_lock = self._potential_code != self._stable_code
                self._stable_code = self._potential_code

                # Extract digits and apply trimming for ALDI/LIDL
                digits_only = "".join(ch for ch in self._stable_code if ch.isdigit())
                n = len(digits_only)

                # Trim ALDI/LIDL 38-digit codes to 20 digits
                if n == 38:
                    digits_only = digits_only[18:]  # Drop first 18 digits to get 20
                if n == 36:
                    digits_only = digits_only[14:]  # Drop first 14 digits to get 18

                self.code.set(digits_only)
                self.last_label = digits_only

                status_text = f"✓ Locked: {self._potential_code_type}: {digits_only}"
                if self._potential_pin_count >= self.STABLE_THRESHOLD:
                    self._stable_pin = self._potential_pin
                    self.pin.set(self._stable_pin)
                    status_text += f" | PIN: {self._stable_pin}"
                    self.last_label += f" | PIN: {self._stable_pin}"

                self._safe_status(status_text, "green")

                if is_new_lock:
                    # Auto-select shop based on digit count
                    try:
                        candidates = []
                        if n == 13:
                            candidates = ["REWE"]
                        elif n == 24 or n == 32:
                            candidates = ["DM"]
                        elif n == 20 or n == 36 or n == 38:  # 38 gets trimmed to 20
                            candidates = ["ALDI", "LIDL"]
                        elif n == 16:
                            candidates = ["EDEKA"]

                        if len(candidates) == 1:
                            # Unambiguous: auto-select
                            shop_to_select = candidates[0]
                            self.selected_shop = shop_to_select
                            try:
                                prev = getattr(self, "selected_shop_button", None)
                                if prev and prev._shop_name != shop_to_select:
                                    self._set_button_style(prev, "normal")
                            except Exception:
                                pass
                            for b in self.shop_buttons:
                                try:
                                    if getattr(b, "_shop_name", None) == shop_to_select:
                                        self._set_button_style(b, "selected")
                                        self.selected_shop_button = b
                                    else:
                                        self._set_button_style(b, "normal")
                                except Exception:
                                    pass
                            self._safe_status(
                                f"✓ Auto-selected: {shop_to_select}", "green"
                            )
                        elif len(candidates) > 1:
                            # Ambiguous ALDI/LIDL: mark as ambiguous orange
                            try:
                                for b in self.shop_buttons:
                                    if getattr(b, "_shop_name", None) in (
                                        "ALDI",
                                        "LIDL",
                                    ):
                                        self._set_button_style(b, "ambiguous")
                                    else:
                                        self._set_button_style(b, "normal")
                            except Exception:
                                pass
                            self._safe_status(
                                "⚠️ Ambiguous (ALDI/LIDL) - Please choose", "orange"
                            )
                    except Exception:
                        pass

                    # Enable shop buttons and Restart Detection button
                    for btn in self.shop_buttons:
                        if self._use_tk_buttons:
                            btn.config(state="normal")
                        else:
                            btn.state(["!disabled"])
                    try:
                        self.take_picture_btn.state(["!disabled"])
                    except Exception:
                        pass
                    beep()

            elif self._potential_code_count > 0:
                status_text = f"Tracking ({self._potential_code_count}/{self.STABLE_THRESHOLD}): {self._potential_code}"
                self.last_label = self._potential_code

                if self._potential_pin_count > 0:
                    status_text += f" | PIN Tracking: {self._potential_pin}"
                    self.last_label += f" | PIN: {self._potential_pin}"
                self._safe_status(status_text, "orange")

            else:
                self.last_label = ""
                if not self._stable_code:
                    self._safe_status("Scanning...", "blue")

        self._draw_scanner_overlay(vis, roi, success=(bool(self._stable_code)))
        self._draw_boxes(vis, self.last_boxes, self.last_label)

        # Scale frame to fit display
        vis = self._scale_frame_to_display(vis)

        rgb = cv2.cvtColor(vis, cv2.COLOR_BGR2RGB)
        img = ImageTk.PhotoImage(Image.fromarray(rgb))
        self.label.configure(image=img)
        self.label.image = img

        if self.scanning:
            self.root.after(20, self.update_frame)

    def reset_scan(self):
        """Resets the scanner to its initial state but keeps the detected code."""
        # Keep the detected code/PIN so they stay visible in text fields!
        # self.code stays set, self.pin stays set

        # Clear stable code/pin so scanning resets properly
        self._stable_code = ""
        self._stable_pin = ""

        # Clear detection state (counters, potential values)
        self._potential_code = ""
        self._potential_code_count = 0
        self._potential_pin = ""
        self._potential_pin_count = 0

        # Disable Restart Detection button
        try:
            self.take_picture_btn.state(["disabled"])
        except Exception:
            pass

        # Disable and reset all shop buttons
        for btn in self.shop_buttons:
            if self._use_tk_buttons:
                btn.config(state="disabled", bg="#f0f0f0")
            else:
                btn.state(["disabled"])

        # Clear selected shop
        self.selected_shop = None
        self.selected_shop_button = None

        self.last_boxes = []
        self.last_label = ""
        self._safe_status("Scanning...", "blue")
        self.scanning = True

    def _scan_barcodes_only(self, bgr):
        """Performs only the pyzbar scan on a pre-processed image."""
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP, tileGridSize=CLAHE_TILE)
        enhanced = clahe.apply(gray)
        blurred = cv2.GaussianBlur(enhanced, (0, 0), UNSHARP_SIGMA)
        sharp = cv2.addWeighted(
            enhanced, 1.0 + UNSHARP_AMOUNT, blurred, -UNSHARP_AMOUNT, 0
        )
        kx = max(3, MORPH_KERNEL_W | 1)
        ky = max(1, MORPH_KERNEL_H | 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kx, ky))
        closed = cv2.morphologyEx(sharp, cv2.MORPH_CLOSE, kernel, iterations=MORPH_ITER)
        results = decode(closed, symbols=SYMBOLS)

        if not results:
            results = decode(sharp, symbols=SYMBOLS)

        out = []
        for r in results or []:
            txt = r.data.decode("utf-8", errors="replace").strip()
            poly = [(p.x, p.y) for p in getattr(r, "polygon", [])] or []
            out.append((txt, r.type, poly))

        return out

    def _try_multiple_scales(self, img):
        """Try decoding barcode at different scales."""
        scales = [0.8, 1.0, 1.2, 1.5, 2.0]
        for scale in scales:
            h, w = img.shape[:2]
            scaled = cv2.resize(img, (int(w * scale), int(h * scale)))
            results = decode(scaled, symbols=SYMBOLS)
            if results:
                return results
        return None

    def _try_rotations(self, img):
        """Try decoding barcode at different rotations."""
        angles = [0, 90, 180, 270]
        for angle in angles:
            if angle == 0:
                rotated = img
            else:
                rotated = cv2.rotate(
                    img,
                    (
                        cv2.ROTATE_90_CLOCKWISE
                        if angle == 90
                        else (
                            cv2.ROTATE_180
                            if angle == 180
                            else cv2.ROTATE_90_COUNTERCLOCKWISE
                        )
                    ),
                )
            results = decode(rotated, symbols=SYMBOLS)
            if results:
                return results
        return None

    # ---------------------- Cleanup ------------------------------------------
    def close(self):
        try:
            self.scanning = False
            if self.cap:
                self.cap.release()
        finally:
            # keep any browser open so you can finish PIN/CAPTCHA
            self.root.destroy()


def main():
    global IP_phone, PORT, CAMERA_MODE, CAMERA_SOURCE, SCANNING_FLAG

    # Show setup window
    setup_root = tk.Tk()
    setup_window = SetupWindow(setup_root)
    setup_root.mainloop()

    if setup_window.result is None:
        print("Setup cancelled")
        return

    # Extract configuration from setup
    IP_phone = setup_window.result["ip"]
    PORT = setup_window.result["port"]
    CAMERA_MODE = setup_window.result["camera_mode"]

    # Set camera source and scanning flag based on camera mode
    if CAMERA_MODE == "laptop":
        CAMERA_SOURCE = "0"
        SCANNING_FLAG = False  # Picture mode
    elif CAMERA_MODE == "usb":
        # For USB cameras, try to find the best device
        best_usb_index = find_best_camera_device(2)  # Start checking from /dev/video2
        CAMERA_SOURCE = str(best_usb_index)
        SCANNING_FLAG = False  # USB always uses picture mode
    else:  # CAMERA_MODE == "ip"
        CAMERA_SOURCE = f"http://{IP_phone}:{PORT}/video"
        SCANNING_FLAG = False  # Picture mode

    # Create main app
    root = tk.Tk()
    app = VoucherScannerApp(root, camera_source=CAMERA_SOURCE)
    try:
        root.mainloop()
    finally:
        try:
            app.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
