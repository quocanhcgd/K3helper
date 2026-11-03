#!/usr/bin/env python3
"""Restore K3 Helper integrations after Creality firmware boot/update."""

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


INSTALL_ROOT = Path("/mnt/UDISK/helper-script")
SERVICE_PATH = Path("/etc/init.d/k3helper-boot-recovery")
MOONRAKER_INIT = Path("/etc/init.d/moonraker")
VERSION_SOURCE = Path("/mnt/UDISK/creality/userdata/config/system_version.json")
FLUIDD_ROOT = INSTALL_ROOT / "fluidd"
INSTALLED_FILE = INSTALL_ROOT / ".installed"

BOOT_SERVICE = """#!/bin/sh /etc/rc.common

START=99
USE_PROCD=1

start_service() {
    procd_open_instance recovery
    procd_set_param command /bin/sh -c 'attempt=0; while [ "$attempt" -lt 120 ]; do if [ -f /mnt/UDISK/helper-script/scripts/k3_boot_recovery.py ]; then exec /usr/bin/python3 /mnt/UDISK/helper-script/scripts/k3_boot_recovery.py run; fi; attempt=$((attempt + 1)); sleep 2; done; exit 0'
    procd_close_instance
}
"""


def _path(root, path):
    return root / str(path).lstrip("/\\")


def restore_missing_moonraker_config(root=Path("/")):
    service = _path(root, MOONRAKER_INIT)
    configured = None
    try:
        content = service.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"(?m)^\s*CONF\s*=\s*['\"]?([^\s'\"]+)", content)
        if match:
            configured = match.group(1)
    except OSError:
        pass

    candidates = []
    if configured:
        candidates.append(Path(configured))
    candidates.extend((
        Path("/mnt/SDCARD/cxsw/printer_data/config/moonraker.conf"),
        Path("/mnt/UDISK/printer_data/config/moonraker.conf"),
        Path("/mnt/UDISK/moonraker.conf"),
    ))

    for target in candidates:
        actual_target = _path(root, target)
        if actual_target.exists():
            continue
        backup = actual_target.with_name("." + actual_target.name + ".bkp")
        if not backup.is_file():
            continue
        actual_target.parent.mkdir(parents=True, exist_ok=True)
        temporary = actual_target.with_name(actual_target.name + ".k3helper.tmp")
        shutil.copy2(str(backup), str(temporary))
        os.replace(str(temporary), str(actual_target))
        return target, True
    return None, False


def ensure_comms_directory(root=Path("/"), config_path=None):
    if config_path:
        paths = [Path(config_path).parent.parent / "comms"]
    else:
        paths = [
            Path("/mnt/SDCARD/cxsw/printer_data/comms"),
            Path("/mnt/UDISK/printer_data/comms"),
        ]
    created = []
    for path in paths:
        actual = _path(root, path)
        if not actual.exists():
            actual.mkdir(parents=True, exist_ok=True)
            created.append(path)
    return created


def sync_firmware_version(root=Path("/")):
    source_path = _path(root, VERSION_SOURCE)
    if not source_path.is_file():
        return False
    try:
        data = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    version = data.get("sys_version") if isinstance(data, dict) else None
    if not isinstance(version, (str, int, float)) or not str(version).strip():
        return False
    target = _path(root, FLUIDD_ROOT / "creality-firmware-version.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps({"sys_version": str(version).strip()}, ensure_ascii=True) + "\n"
    if target.exists() and target.read_text(encoding="utf-8") == content:
        return False
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(str(temporary), str(target))
    return True


def write_service(root=Path("/")):
    target = _path(root, SERVICE_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_text(encoding="utf-8") == BOOT_SERVICE:
        return False
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(BOOT_SERVICE, encoding="utf-8")
    os.chmod(str(temporary), 0o755)
    os.replace(str(temporary), str(target))
    return True


def _installed_features(root):
    try:
        return set(_path(root, INSTALLED_FILE).read_text(encoding="utf-8").splitlines())
    except OSError:
        return set()


def _http_ready(url):
    try:
        with urllib.request.urlopen(url, timeout=2):
            return True
    except Exception:
        return False


def _start_service(root, name, health_url):
    init_script = _path(root, Path("/etc/init.d") / name)
    if _http_ready(health_url) or not init_script.exists():
        return False
    subprocess.run([str(init_script), "start"], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def _wait_for(url, attempts=20):
    for _ in range(attempts):
        if _http_ready(url):
            return True
        time.sleep(1)
    return False


def repair_chamber_light(root=Path("/"), features=None):
    """Restore the Helper LED include lost when firmware rewrites printer.cfg."""
    features = _installed_features(root) if features is None else features
    if "chamber_light" not in features:
        return False
    script = _path(root, INSTALL_ROOT / "scripts/chamber_light_config.py")
    if not script.is_file():
        return False
    configs = (
        Path("/mnt/SDCARD/cxsw/printer_data/config/printer.cfg"),
        Path("/mnt/UDISK/printer_data/config/printer.cfg"),
    )
    config = next((_path(root, path) for path in configs if _path(root, path).is_file()), None)
    if config is None:
        return False
    result = subprocess.run(
        ["/usr/bin/python3", str(script), "install", str(config)],
        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        return False
    restart = _path(root, Path("/etc/init.d/klipper"))
    if not restart.exists():
        restart = _path(root, Path("/etc/rc.d/S55klipper"))
    if restart.exists():
        subprocess.run([str(restart), "restart"], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def recover(root=Path("/"), wait=True):
    restored_path, restored = restore_missing_moonraker_config(root)
    created_comms = ensure_comms_directory(root, restored_path)
    version_synced = sync_firmware_version(root)

    features = _installed_features(root)
    led_repaired = repair_chamber_light(root, features)
    if "camera_support_k3" in features:
        _start_service(root, "go2rtc-k3", "http://127.0.0.1:1984/api/streams")
    if "k3_firmware_api" in features:
        _start_service(root, "k3-firmware-api", "http://127.0.0.1:8765/api/firmware")
    if "k3_screen_apps" in features:
        _start_service(root, "k3-screen-apps", "http://127.0.0.1:18092/")

    moonraker_url = "http://127.0.0.1:7125/server/info"
    if restored and _path(root, MOONRAKER_INIT).exists():
        subprocess.run([str(_path(root, MOONRAKER_INIT)), "restart"], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if wait and features.intersection(("camera_support_k3", "k3_screen_apps")):
        if restored:
            _wait_for(moonraker_url)
        if _http_ready(moonraker_url):
            if "camera_support_k3" in features and _http_ready("http://127.0.0.1:1984/api/streams"):
                watchdog = _path(root, INSTALL_ROOT / "camera_watchdog.py")
                if watchdog.is_file():
                    subprocess.run(["/usr/bin/python3", str(watchdog), "--register",
                                    _printer_ip(root)], check=False,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if "k3_screen_apps" in features and _http_ready("http://127.0.0.1:18092/"):
                register = _path(root, INSTALL_ROOT / "screen-apps/moonraker_webcam.py")
                if register.is_file():
                    subprocess.run(["/usr/bin/python3", str(register), "register"],
                                   check=False, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)

    return {
        "config_restored": restored,
        "config_path": str(restored_path) if restored_path else None,
        "comms_created": [str(path) for path in created_comms],
        "firmware_version_synced": version_synced,
        "features": sorted(features),
        "chamber_light_repaired": led_repaired,
    }


def _printer_ip(root):
    ip_file = _path(root, INSTALL_ROOT / "go2rtc-k3.ip")
    try:
        value = ip_file.read_text(encoding="utf-8").strip()
        if value:
            return value
    except OSError:
        pass
    try:
        output = subprocess.check_output(["ip", "route", "get", "1"],
                                         stderr=subprocess.DEVNULL, text=True)
        match = re.search(r"\bsrc\s+(\d+(?:\.\d+){3})", output)
        if match:
            return match.group(1)
    except (OSError, subprocess.CalledProcessError):
        pass
    return "127.0.0.1"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["install"]:
        write_service()
        subprocess.run([str(SERVICE_PATH), "enable"], check=True)
        print("K3 boot recovery service installed and enabled.")
        return 0
    if argv == ["run"]:
        print(json.dumps(recover(), ensure_ascii=True), flush=True)
        return 0
    if argv == ["repair-config"]:
        restored_path, restored = restore_missing_moonraker_config()
        created = ensure_comms_directory(config_path=restored_path)
        if restored:
            subprocess.run([str(MOONRAKER_INIT), "restart"], check=False)
        print(json.dumps({
            "config_restored": restored,
            "config_path": str(restored_path) if restored_path else None,
            "comms_created": [str(path) for path in created],
        }, ensure_ascii=True))
        return 0
    print("Usage: k3_boot_recovery.py [install|run|repair-config]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
