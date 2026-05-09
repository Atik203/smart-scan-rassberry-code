# Raspberry Pi 5 Quick Setup Checklist

1. Install required tools

- sudo apt update
- sudo apt install -y android-tools-adb python3-opencv python3-pip

2. Enable USB debugging on both phones

- Settings > Developer options > USB debugging
- Connect USB and accept the RSA prompt when it appears

3. Verify adb sees devices

- adb devices
- Confirm the serials match DEVICE_PATHS in the script

4. Run the script

- python3 auto_capture_pi5.py

Notes

- If you use a virtual environment, install OpenCV in it: pip install opencv-python
- If adb is not in PATH, set ADB_PATH to /usr/bin/adb (or the actual adb path)
