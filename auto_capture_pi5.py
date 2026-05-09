import subprocess
import time
import os
import shutil
import sys
import cv2

# === CONFIGURATION (Raspberry Pi 5) ===
# Prefer adb in PATH on Linux. If needed, set a full path like /usr/bin/adb.
ADB_PATH = "adb"
# Local save directory on the Pi
PI_SAVE_PATH = "/home/simplex/SmartScan_Captures"
COUNTER_FILE = os.path.join(PI_SAVE_PATH, "page_counter.txt")

# Device Serials
DEVICE_PATHS = {
    "868130a1": "/storage/emulated/0/DCIM/Camera",  # Redmi Note 13 Pro
    "10AFBB2BKT00367": "/storage/emulated/0/DCIM/Camera",  # Vivo X300 Pro
}

DEVICE_LABELS = {"868130a1": "right", "10AFBB2BKT00367": "left"}

# Auto-capture settings
PREPROCESS_DELAY_SEC = 1
PAGE_FLIP_INTERVAL_SEC = 2
TOTAL_PAGES = 10

# Global dictionary to track the last pulled filename for duplicate prevention
last_filenames = {serial: "" for serial in DEVICE_PATHS}

os.makedirs(PI_SAVE_PATH, exist_ok=True)


# === UTILS ===
def run_adb_command(command, serial=None):
    cmd = [ADB_PATH]
    if serial:
        cmd += ["-s", serial]
    cmd += command
    try:
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        return result.stdout.strip()
    except Exception as e:
        print(f"Subprocess Error: {e}")
        return ""


def resolve_adb_path():
    if os.path.isabs(ADB_PATH) or "/" in ADB_PATH:
        return ADB_PATH if os.path.exists(ADB_PATH) else None
    return shutil.which(ADB_PATH)


def fail_fast(message):
    print(f"[ERROR] {message}")
    sys.exit(1)


def ensure_adb_ready():
    global ADB_PATH
    resolved = resolve_adb_path()
    if not resolved:
        fail_fast(
            "adb not found. Install android-tools-adb or set ADB_PATH to a full path."
        )
    ADB_PATH = resolved

    result = subprocess.run(
        [ADB_PATH, "devices"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip()
        fail_fast(f"adb devices failed. {details}")

    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    device_lines = [line for line in lines[1:] if "\tdevice" in line]
    if not device_lines:
        fail_fast(
            "No devices detected by adb. Check USB, enable USB debugging, and accept the RSA prompt."
        )

    detected = {line.split()[0] for line in device_lines}
    missing = [serial for serial in DEVICE_PATHS if serial not in detected]
    if missing:
        fail_fast(
            "Missing expected device(s): "
            f"{', '.join(missing)}. Detected: {', '.join(sorted(detected))}"
        )


def load_page_counter():
    if os.path.exists(COUNTER_FILE):
        with open(COUNTER_FILE, "r") as f:
            return int(f.read().strip())
    return 1


def save_page_counter(counter):
    with open(COUNTER_FILE, "w") as f:
        f.write(str(counter))


def take_photo(serial):
    print(f"[*] Triggering Shutter on: {serial}")
    # Force Camera App to front
    run_adb_command(["shell", "monkey", "-p", "com.android.camera", "1"], serial)
    time.sleep(0.5)
    # Use Keycode 66 (ENTER) to avoid mode-switching bugs on Redmi
    run_adb_command(["shell", "input", "keyevent", "66"], serial)


def get_latest_image(serial):
    phone_path = DEVICE_PATHS[serial]
    # 'ls -t' sorts by modification time (Newest at the top)
    output = run_adb_command(["shell", f"ls -t {phone_path}"], serial)

    # Filter for JPG files (case-insensitive)
    image_files = [f for f in output.splitlines() if f.lower().endswith(".jpg")]

    if not image_files:
        return None, None

    newest_file = image_files[0]

    # Duplicate Check: If the newest file is the same as last time, the phone didn't take a new photo
    if newest_file == last_filenames[serial]:
        print(f"[WARNING] {serial} is returning the same old file: {newest_file}")
        return "DUPLICATE", phone_path

    last_filenames[serial] = newest_file
    return newest_file, phone_path


def rotate_image(image_path, label):
    img = cv2.imread(image_path)
    if img is None:
        return

    # Adjust rotations for your V-Cradle 45-degree mounts
    if label == "left":
        rotated = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    else:
        rotated = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    cv2.imwrite(image_path, rotated)


def pull_image(serial, filename, remote_path, page_num, label):
    remote_full = f"{remote_path}/{filename}"
    local_name = f"page_{page_num:03d}_{label}.jpg"
    local_path = os.path.join(PI_SAVE_PATH, local_name)

    print(f"[+] Pulling {filename} -> {local_name}")
    run_adb_command(["pull", remote_full, local_path], serial)
    rotate_image(local_path, label)


# === MAIN ===
def capture_page(page_number):
    # 1. Trigger both shutters
    for serial in DEVICE_PATHS:
        take_photo(serial)

    # 2. WAIT for ISP (Vivo X300 Pro high-res needs time)
    print("Processing high-res images...")
    time.sleep(6)

    # 3. Pull and process
    for serial in DEVICE_PATHS:
        try:
            latest, path = get_latest_image(serial)
            if latest == "DUPLICATE":
                print(f"[!] {serial} failed to capture a new image. Skipping pull.")
            elif latest:
                label = DEVICE_LABELS[serial]
                pull_image(serial, latest, path, page_number, label)
            else:
                print(f"[!] No images found in {serial} path.")
        except Exception as e:
            print(f"[ERROR] {serial}: {e}")

    save_page_counter(page_number + 1)
    print(f"Page {page_number} sequence complete.\n")


def main():
    ensure_adb_ready()
    print("Starting SmartScan Capture Sequence...")
    page_number = load_page_counter()

    print(f"Preprocessing delay: {PREPROCESS_DELAY_SEC}s")
    time.sleep(PREPROCESS_DELAY_SEC)

    for i in range(TOTAL_PAGES):
        capture_page(page_number)
        page_number += 1
        if i < TOTAL_PAGES - 1:
            print(f"Waiting {PAGE_FLIP_INTERVAL_SEC}s for page flip...")
            time.sleep(PAGE_FLIP_INTERVAL_SEC)


if __name__ == "__main__":
    main()
