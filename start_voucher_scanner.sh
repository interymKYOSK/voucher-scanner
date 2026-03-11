#!/usr/bin/env bash
cd "$(dirname "$0")"

# Initialise conda
source ~/miniconda3/etc/profile.d/conda.sh
conda activate voucher-scanner

# --- Optional: USB phone camera via scrcpy ---
# Automatically detected: only runs if an Android phone is connected via USB.
SCRCPY_PID=""
if adb devices 2>/dev/null | grep -q "device$"; then
    echo "Android phone detected — starting USB camera stream..."
    sudo -n modprobe -r v4l2loopback 2>/dev/null
    sudo -n modprobe v4l2loopback devices=1 video_nr=2 card_label="DroidCam" exclusive_caps=1 max_width=2560 max_height=1440
    scrcpy --v4l2-sink=/dev/video2 --no-playback --video-source=camera --camera-size=2560x1440 &
    SCRCPY_PID=$!
    sleep 3
else
    echo "No Android phone detected — skipping USB camera setup."
    echo "Using internal or IP camera mode."
fi

python voucher-scanner.py

# Stop scrcpy if it was started
if [ -n "$SCRCPY_PID" ]; then
    kill $SCRCPY_PID 2>/dev/null
fi