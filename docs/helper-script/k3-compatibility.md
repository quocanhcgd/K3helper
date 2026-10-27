# Creality K3 Compatibility

K3 support targets board `CR0CUF039C13` running Tina 5.0 / OpenWrt 21.02. It is experimental and limited to paths and behavior confirmed on this firmware. K2 printer macros are blocked because K3's `printer.cfg`, pins, sensors, and print workflow have not been audited.

## Available in the K3 menu

- **Moonraker config check** verifies that `/mnt/UDISK/printer_data/config/moonraker.conf` includes `/usr/share/moonraker/moonraker.conf`. It does not patch startup scripts, rewrite the config, or offer removal because the firmware uses this UDISK config at runtime.
- **Update Helper Script** (menu option 15) downloads `helper.sh` and the runtime files in `scripts/` directly from the public K3helper GitHub repository, verifies each Git blob checksum, and replaces files only after all downloads pass verification. It does not fetch a large ZIP archive or remove the installed Fluidd copy, printer configuration, or local data. Run this before installing recent Helper Script fixes.
- **Fluidd update/repair** installs a writable copy under `/mnt/UDISK/helper-script/fluidd` and reapplies the K3 webcam, file-download, and thumbnail compatibility patches. It also displays the Creality `sys_version` from `system_version.json` and points the port `4408` Nginx server at that copy. Thumbnail previews are added to the Jobs file list and RE-PRINT history when the G-code has an embedded preview. The sanitized firmware version is also available at `/creality-firmware-version.json` on port `4408`.
- **Fluidd Custom UI** remains enabled. Fluidd `1.37.7` loads custom styling and backgrounds from `.fluidd-theme` inside Moonraker's active `config` root. On the reported K3 layout this is `/mnt/SDCARD/cxsw/printer_data/config/.fluidd-theme`; the installer falls back to `/mnt/UDISK/printer_data/config/.fluidd-theme` on layouts without that mount. Upload `custom.css` and optionally one `background.png`, `.jpg`, `.jpeg`, or `.gif` through **Configuration → config**. The K3 installer creates this directory if it is missing and does not overwrite existing files. Use **Settings → Theme** for the built-in presets, primary color, and dark/light mode.
- **K3 Camera (install/repair)** bridges the firmware camera endpoint on port `8000` through go2rtc on port `1984`. Its Fluidd compatibility patch also adds a read-only CFS status card backed by Moonraker's Klipper `box` object. The card uses Fluidd's native card classes, appears in the existing dashboard column immediately before **Macros**, and follows the active light/dark theme. It requires the firmware overlay to be mounted on `/etc` so its procd service can persist. Select the same menu item after firmware updates to refresh the Fluidd patch and service. The card does not provide print slot selection.
- **K3 Firmware API** serves selected fields from `/mnt/UDISK/creality/userdata/config/system_version.json` at `http://<printer-ip>:8765/api/firmware`. It rereads the file for each request, starts at boot through `procd`, and returns only firmware, app, and hardware version fields. It requires the `/etc` overlay for its persistent service.
- **Cloud connection trace** captures printer-originated DNS and TCP/TLS metadata for five minutes and writes one local log under `/mnt/UDISK/helper-script/logs/`. It requires root and kernel packet-socket support, makes no network configuration changes, and stores no packet payload.
- **K3 Cloud region switch** stages the firmware-supported `Server.COM` or `Server.CN` request on removable USB storage. The touchscreen must confirm the change; the Helper Script does not alter the factory JSON or confirm the switch. See [K3 Cloud Region Switch](k3-cloud-region.md) for verification and cleanup.
- **Configuration backup and restore** archive `/mnt/UDISK/printer_data/config`.
- **Service and log tools** use known OpenWrt init-script candidates and report an error if no service script is present.

### Existing installations

To add menu option 15 to an older installation, bootstrap the updater files once over SSH:

```sh
python3 - <<'PY'
import os
import urllib.request
from pathlib import Path

base = "https://raw.githubusercontent.com/quocanhcgd/K3helper/main/"
root = Path("/mnt/UDISK/helper-script")
for relative in ("helper.sh", "scripts/update_helper.sh", "scripts/update_helper.py"):
    target = root / relative
    temporary = target.with_name(target.name + ".tmp")
    request = urllib.request.Request(base + relative, headers={"User-Agent": "K3helper-bootstrap/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response, open(temporary, "wb") as output:
        output.write(response.read())
    os.chmod(temporary, 0o755)
    os.replace(temporary, target)
print("Bootstrap complete. Restart Helper Script and select option 15.")
PY
```

## Disabled until verified

KAMP, K2-specific macros and shaper calibration, Moonraker Timelapse, Mainsail installation, and Entware are not exposed in the K3 menu. KAMP currently writes K2-specific probe macro names and bed settings. The other features depend on firmware paths, pins, or service behavior that has not been confirmed on K3.

The K3 camera and Fluidd compatibility flow has been exercised with the reported firmware layout. Nginx edits still require `nginx -t` to pass before the service is restarted. Keep a backup of printer configuration before using restore, because restore replaces files in the config directory.
