import subprocess
import time
import os
import cv2

# === CONFIGURATION ===
# Path to Minimal ADB
ADB_PATH = r"C:\Program Files (x86)\Minimal ADB and Fastboot\adb.exe"
# Local save directory
PI_SAVE_PATH = r"D:\SmartScan_Captures"
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
    if not os.path.exists(ADB_PATH):
        print(f"ERROR: adb.exe not found at: {ADB_PATH}")
        return ""
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
        print(f"[⚠️ WARNING] {serial} is returning the same old file: {newest_file}")
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
    print("⏳ Processing high-res images...")
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
    print(f"✅ Page {page_number} sequence complete.\n")


def main():
    print("🚀 Starting SmartScan Capture Sequence...")
    page_number = load_page_counter()

    print(f"⏳ Preprocessing delay: {PREPROCESS_DELAY_SEC}s")
    time.sleep(PREPROCESS_DELAY_SEC)

    for _ in range(TOTAL_PAGES):
        capture_page(page_number)
        page_number += 1
        if _ < TOTAL_PAGES - 1:
            print(f"🔁 Waiting {PAGE_FLIP_INTERVAL_SEC}s for page flip...")
            time.sleep(PAGE_FLIP_INTERVAL_SEC)


if __name__ == "__main__":
    main()
