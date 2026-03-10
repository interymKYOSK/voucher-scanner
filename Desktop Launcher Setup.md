### Desktop Launcher Setup

To create a clickable desktop shortcut for launching the application with the correct
working directory and Conda environment, follow the steps below.

---

#### 1. Create a wrapper script

Create the file:

```
~/Nextcloud/Bezahlkarte_Gutscheine/voucher-scanner/start_voucher_scanner.sh
```

with the following content:

```bash
#!/usr/bin/env bash
cd "$(dirname "$0")"

# Initialise conda
source ~/miniconda3/etc/profile.d/conda.sh
conda activate voucher-scanner

# Start phone camera stream via USB (scrcpy → /dev/video2)
# Requires phone plugged in via USB with USB Debugging enabled.
# scrcpy runs in the background; it is killed automatically when the app exits.
scrcpy --v4l2-sink=/dev/video2 --no-playback --video-source=camera --camera-size=2560x1440 &
SCRCPY_PID=$!

# Give scrcpy a moment to initialise the video stream
sleep 3

python voucher-scanner.py

# Stop scrcpy when the app closes
kill $SCRCPY_PID 2>/dev/null
```

Make it executable:

```bash
chmod +x ~/Nextcloud/Bezahlkarte_Gutscheine/voucher-scanner/start_voucher_scanner.sh
```

> **Note:** If you are using a different camera mode (laptop or IP webcam), the scrcpy
> line will silently fail and the app will still start normally — it does no harm.

---

#### 2. Create a desktop entry

Create the file:

```
~/.local/share/applications/start_voucher_scanner.desktop
```

with the following content:

```ini
[Desktop Entry]
Type=Application
Name=Start Voucher Scanner
Exec=/home/<USER>/Nextcloud/Bezahlkarte_Gutscheine/voucher-scanner/start_voucher_scanner.sh
Icon=/home/<USER>/Nextcloud/Bezahlkarte_Gutscheine/voucher-scanner/icon.png
Terminal=true
```

Replace `<USER>` with your username.

Set permissions and update the desktop database:

```bash
chmod 755 ~/.local/share/applications/start_voucher_scanner.desktop
update-desktop-database ~/.local/share/applications/
```

---

#### 3. Create a desktop link (optional)

To place a clickable launcher on the desktop:

```bash
ln -s ~/.local/share/applications/start_voucher_scanner.desktop ~/Desktop/
```

or on German GNOME:

```bash
ln -s ~/.local/share/applications/start_voucher_scanner.desktop ~/Schreibtisch/
```

On GNOME, right-click the desktop entry and select **Allow Launching**.

---

#### Prerequisites for USB phone camera mode

Before the launcher works with the phone camera, the v4l2loopback kernel module must
be loaded. This happens automatically at boot if you followed the permanent setup in
`README_USB_from_phone.md`. To load it manually:

```bash
sudo modprobe v4l2loopback devices=1 video_nr=2 card_label="DroidCam" exclusive_caps=1 max_width=2560 max_height=1440
```

See `README_USB_from_phone.md` for the full installation and troubleshooting guide.
