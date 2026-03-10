# USB Camera from Android Phone (scrcpy + V4L2)

This setup streams your Android phone's camera over USB to a virtual V4L2 device (`/dev/video2`),
which the voucher scanner app reads like a regular webcam — at full resolution.

---

## How it works

```
Android phone camera
        ↓
scrcpy (via ADB over USB)
        ↓
/dev/video2  (v4l2loopback virtual device)
        ↓
voucher-scanner.py (OpenCV reads it as a normal camera)
```

---

## One-time Installation

### 1. Install v4l2loopback

```bash
sudo apt install v4l2loopback-dkms v4l2loopback-utils
```

### 2. Load the kernel module

```bash
sudo modprobe -r v4l2loopback
sudo modprobe v4l2loopback devices=1 video_nr=2 card_label="DroidCam" exclusive_caps=1 max_width=2560 max_height=1440
```

To make this permanent (load at boot):

```bash
echo "v4l2loopback" | sudo tee /etc/modules-load.d/v4l2loopback.conf
echo 'options v4l2loopback devices=1 video_nr=2 card_label="DroidCam" exclusive_caps=1 max_width=2560 max_height=1440' | sudo tee /etc/modprobe.d/v4l2loopback.conf
```

### 3. Install scrcpy (version 3.x required)

The system package is too old. Build from source:

```bash
sudo apt install -y git android-tools-adb ffmpeg libsdl2-dev libavcodec-dev \
  libavdevice-dev libavformat-dev libavutil-dev libswresample-dev \
  libusb-1.0-0-dev meson ninja-build pkg-config

git clone https://github.com/Genymobile/scrcpy /tmp/scrcpy
cd /tmp/scrcpy
./install_release.sh
hash -r
scrcpy --version  # should show 3.x
```

---

## Phone Setup

| Setting | Where | Value |
|---|---|---|
| USB Debugging | Settings → Developer Options | On |
| USB Connection Mode | Notification when plugging in | File Transfer (MTP) |
| Allow USB Debugging prompt | Popup on phone screen | Allow (tick "Always allow") |

No DroidCam app needed. No WiFi needed. Just plug in the USB cable.

---

## Running

Every time you want to use the phone as a camera, start scrcpy first in a terminal:

```bash
scrcpy --v4l2-sink=/dev/video2 --no-playback --video-source=camera --camera-size=2560x1440
```

Keep this terminal open. Then launch the voucher scanner app and select **USB** as the camera mode.

To verify the video feed is working before starting the app:

```bash
v4l2-ctl --device=/dev/video2 --all | grep "Width\|Height"
```

---

## Troubleshooting

**`can't open camera by index`**
scrcpy is not running. Start it first before launching the app.

**`ERROR: Failed to write header to /dev/video2`**
The v4l2loopback module needs reloading with correct max resolution:
```bash
sudo modprobe -r v4l2loopback
sudo modprobe v4l2loopback devices=1 video_nr=2 card_label="DroidCam" exclusive_caps=1 max_width=2560 max_height=1440
```

**`Key was rejected by service` when loading module**
Secure Boot is blocking unsigned kernel modules. Either disable Secure Boot in BIOS,
or sign the module with MOK (see your distro documentation).

**Phone not detected (`adb devices` shows nothing)**
```bash
adb kill-server
adb start-server
adb devices
```
Make sure USB mode on the phone is set to File Transfer, not Charging only.

**scrcpy uses old version (1.25)**
```bash
hash -r
which scrcpy  # should be /usr/local/bin/scrcpy
```
Add to `~/.bashrc` if needed: `export PATH=/usr/local/bin:$PATH`
