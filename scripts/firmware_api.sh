#!/bin/sh
# K3 firmware version API service.

SCRIPT_DIR=/mnt/UDISK/helper-script
API_SCRIPT=$SCRIPT_DIR/scripts/firmware_api.py
VERSION_FILE=/mnt/UDISK/creality/userdata/config/system_version.json
SERVICE=/etc/init.d/k3-firmware-api
INSTALLED_FILE=$SCRIPT_DIR/.installed

log_info() { printf '[INFO] %s\n' "$1"; }
log_error() { printf '[ERROR] %s\n' "$1" >&2; }
log_success() { printf '[OK] %s\n' "$1"; }

require_k3() {
    if [ -x /usr/bin/get_sn_mac.sh ]; then
        board=$(/usr/bin/get_sn_mac.sh board 2>/dev/null)
        case "$board" in
            CR0CUF039C13*) return 0 ;;
        esac
    fi
    log_error "This service targets Creality K3 board CR0CUF039C13."
    return 1
}

require_root() {
    [ "$(id -u)" = 0 ] || { log_error "Run this script as root."; return 1; }
}

require_overlay() {
    if ! awk '$2 == "/etc" && $3 == "overlay" { found=1 } END { exit !found }' /proc/mounts; then
        log_error "The firmware overlay is not active; cannot install the persistent service."
        echo "Enable the overlay and reboot before installing this feature."
        return 1
    fi
}

mark_installed() {
    touch "$INSTALLED_FILE"
    grep -qx 'k3_firmware_api' "$INSTALLED_FILE" 2>/dev/null || echo 'k3_firmware_api' >> "$INSTALLED_FILE"
}

mark_removed() {
    [ -f "$INSTALLED_FILE" ] && sed -i '/^k3_firmware_api$/d' "$INSTALLED_FILE"
}

write_service() {
    cat > "$SERVICE" <<'EOF'
#!/bin/sh /etc/rc.common

START=99
STOP=10
USE_PROCD=1

start_service() {
    procd_open_instance firmware_api
    procd_set_param command /usr/bin/python3 /mnt/UDISK/helper-script/scripts/firmware_api.py
    procd_set_param respawn 3600 5 0
    procd_close_instance
}
EOF
    chmod 755 "$SERVICE"
}

install_api() {
    require_root || return 1
    require_k3 || return 1
    require_overlay || return 1
    [ -f "$API_SCRIPT" ] || { log_error "Missing $API_SCRIPT"; return 1; }
    [ -r "$VERSION_FILE" ] || { log_error "Cannot read $VERSION_FILE"; return 1; }
    python3 - "$VERSION_FILE" <<'PY' || {
import json
import sys
with open(sys.argv[1], encoding="utf-8") as version_file:
    data = json.load(version_file)
if not isinstance(data, dict) or not data.get("sys_version"):
    raise SystemExit("No sys_version field found")
PY
        log_error "Firmware version JSON is invalid or has no sys_version."
        return 1
    }

    write_service || return 1
    "$SERVICE" enable || { log_error "Could not enable the firmware API service."; return 1; }
    "$SERVICE" restart || return 1
    attempt=0
    while [ "$attempt" -lt 10 ]; do
        if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/firmware', timeout=2).read()" 2>/dev/null; then
            mark_installed
            log_success "Firmware API running at http://<printer-ip>:8765/api/firmware"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
    log_error "Firmware API did not start; inspect the service log with logread."
    return 1
}

remove_api() {
    require_root || return 1
    require_overlay || return 1
    if [ -x "$SERVICE" ]; then
        "$SERVICE" stop >/dev/null 2>&1
        "$SERVICE" disable >/dev/null 2>&1
        rm -f "$SERVICE"
    fi
    rm -f /etc/rc.d/S99k3-firmware-api /etc/rc.d/K10k3-firmware-api
    mark_removed
    log_success "K3 firmware API removed."
}

case "$1" in
    install|repair|update) install_api ;;
    remove) remove_api ;;
    *) echo "Usage: $0 [install|repair|update|remove]"; exit 2 ;;
esac
