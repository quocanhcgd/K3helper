# Creality K3 Compatibility

K3 support targets board `CR0CUF039C13` running Tina 5.0 / OpenWrt 21.02. It is experimental and limited to paths and behavior confirmed on this firmware. K2 printer macros are blocked because K3's `printer.cfg`, pins, sensors, and print workflow have not been audited.

## Available in the K3 menu

- **Moonraker config check** verifies that `/mnt/UDISK/printer_data/config/moonraker.conf` includes `/usr/share/moonraker/moonraker.conf`. It does not patch startup scripts, rewrite the config, or offer removal because the firmware uses this UDISK config at runtime.
- **Fluidd update/repair** installs a writable copy under `/mnt/UDISK/helper-script/fluidd`, applies the K3 webcam API compatibility patch, displays the Creality `sys_version` from `system_version.json`, and points the port `4408` Nginx server at that copy. The sanitized version is also available at `/creality-firmware-version.json` on port `4408`.
- **K3 Camera (install/repair)** bridges the firmware camera endpoint on port `8000` through go2rtc on port `1984`. It requires the firmware overlay to be mounted on `/etc` so its procd service can persist. Select the same menu item after firmware updates to refresh the Fluidd patch and service.
- **K3 Firmware API** serves selected fields from `/mnt/UDISK/creality/userdata/config/system_version.json` at `http://<printer-ip>:8765/api/firmware`. It rereads the file for each request, starts at boot through `procd`, and returns only firmware, app, and hardware version fields. It requires the `/etc` overlay for its persistent service.
- **Cloud connection trace** captures printer-originated DNS and TCP/TLS metadata for five minutes and writes one local log under `/mnt/UDISK/helper-script/logs/`. It requires root and kernel packet-socket support, makes no network configuration changes, and stores no packet payload.
- **K3 Cloud region switch** stages the firmware-supported `Server.COM` or `Server.CN` request on removable USB storage. The touchscreen must confirm the change; the Helper Script does not alter the factory JSON or confirm the switch. See [K3 Cloud Region Switch](k3-cloud-region.md) for verification and cleanup.
- **Configuration backup and restore** archive `/mnt/UDISK/printer_data/config`.
- **Service and log tools** use known OpenWrt init-script candidates and report an error if no service script is present.

## Disabled until verified

KAMP, K2-specific macros and shaper calibration, Moonraker Timelapse, Mainsail installation, and Entware are not exposed in the K3 menu. KAMP currently writes K2-specific probe macro names and bed settings. The other features depend on firmware paths, pins, or service behavior that has not been confirmed on K3.

The K3 camera and Fluidd compatibility flow has been exercised with the reported firmware layout. Nginx edits still require `nginx -t` to pass before the service is restarted. Keep a backup of printer configuration before using restore, because restore replaces files in the config directory.
