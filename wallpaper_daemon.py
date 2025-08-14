import random
import time
import subprocess
from pathlib import Path
from config_loader import STATIC_DIR, STEAM_PROTOCOL, DEPLOY_SCRIPT_NAME

CHECK_INTERVAL = 5  # seconds

def set_static_wallpaper(image_path: Path):
    subprocess.run([
        "powershell", "-command",
        (
            '[System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms") | Out-Null;'
            f'[System.Windows.Forms.SystemParametersInfo]::SetDesktopWallpaper("{image_path.resolve()}", 1, 0)'
        )
    ], check=False)

def restore_wallpaper_engine():
    subprocess.Popen(["start", "", STEAM_PROTOCOL], shell=True)

def is_deploy_running():
    try:
        tasks = subprocess.check_output(['tasklist'], shell=True).decode(errors="ignore").lower()
        return DEPLOY_SCRIPT_NAME.lower() in tasks or ("python" in tasks and "deploy-wallpaper.py" in tasks)
    except Exception:
        return False

def pick_random_static():
    choices = list(STATIC_DIR.glob("*.jpg")) + list(STATIC_DIR.glob("*.png"))
    return random.choice(choices) if choices else None

def daemon_loop():
    last_state = None  # None | "static" | "satellite"
    print("[DAEMON] Running. Watching for deploy activity...")
    while True:
        deploy_active = is_deploy_running()

        if deploy_active and last_state != "static":
            print("[DAEMON] Detected deploy activity. Switching to static image.")
            img = pick_random_static()
            if img:
                set_static_wallpaper(img)
                last_state = "static"
            else:
                print("[WARN] No static images found in:", STATIC_DIR)

        elif not deploy_active and last_state != "satellite":
            print("[DAEMON] Deploy complete. Restoring satellite wallpaper.")
            restore_wallpaper_engine()
            last_state = "satellite"

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    daemon_loop()
