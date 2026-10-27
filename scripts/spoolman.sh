#!/bin/sh
# Connect K3 Moonraker and Fluidd to an existing Spoolman server.

SCRIPT_DIR=/mnt/UDISK/helper-script
CONFIG_DIR=/mnt/UDISK/printer_data/config
MOONRAKER_CONF=
INSTALLED_FILE=$SCRIPT_DIR/.installed
. "$SCRIPT_DIR/scripts/system.sh"

CONFIG_HELPER=$SCRIPT_DIR/scripts/spoolman_config.py
CONFIG_PATH_HELPER=$SCRIPT_DIR/scripts/moonraker_config_path.py

require_root() {
    [ "$(id -u)" = 0 ] || { log_error "Run this script as root."; return 1; }
}

check_k3_config() {
    if ! is_k3; then
        log_error "This integration is currently enabled for K3 only."
        return 1
    fi
    if [ ! -f "$CONFIG_PATH_HELPER" ]; then
        log_error "Missing $CONFIG_PATH_HELPER"
        return 1
    fi
    MOONRAKER_CONF=$(python3 "$CONFIG_PATH_HELPER") || {
        log_error "Could not identify Moonraker's active writable config file."
        log_info "No configuration was changed."
        return 1
    }
    case "$MOONRAKER_CONF" in
        /mnt/SDCARD/*|/mnt/UDISK/*) ;;
        *)
            log_error "Moonraker config is outside the persistent K3 data mounts: $MOONRAKER_CONF"
            return 1
            ;;
    esac
    if [ ! -f "$MOONRAKER_CONF" ]; then
        log_error "Moonraker's active config file was not found: $MOONRAKER_CONF"
        return 1
    fi
    if ! find /usr/share/moonraker -type f -name spoolman.py -print 2>/dev/null | grep -q .; then
        log_error "This Moonraker firmware does not include its Spoolman component."
        log_info "No configuration was changed."
        return 1
    fi
    if [ -L "$MOONRAKER_CONF" ]; then
        log_error "Moonraker config is a symbolic link; refusing to replace it atomically."
        return 1
    fi
    if [ ! -w "$MOONRAKER_CONF" ]; then
        log_error "Moonraker's active config is not writable: $MOONRAKER_CONF"
        return 1
    fi
    [ -f "$CONFIG_HELPER" ] || { log_error "Missing $CONFIG_HELPER"; return 1; }
    log_info "Using active Moonraker config: $MOONRAKER_CONF"
}

check_moonraker() {
    python3 - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:7125/server/info", timeout=5) as response:
    info = json.loads(response.read().decode("utf-8"))
if "result" not in info or "components" not in info["result"]:
    raise SystemExit("Moonraker returned an unexpected /server/info response")
PY
}

normalize_and_check_server() {
    python3 - "$1" <<'PY'
import json
import sys
import urllib.parse
import urllib.request

raw = sys.argv[1].strip()
parsed = urllib.parse.urlsplit(raw)
if any(character.isspace() for character in raw):
    raise SystemExit("The Spoolman URL cannot contain whitespace")
if parsed.scheme not in ("http", "https") or not parsed.hostname:
    raise SystemExit("Enter a full URL such as http://192.168.0.20:7912")
if parsed.username or parsed.password or parsed.query or parsed.fragment:
    raise SystemExit("The URL cannot contain credentials, a query, or a fragment")
try:
    parsed.port
except ValueError as error:
    raise SystemExit("Invalid Spoolman port: %s" % error)
server = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
request = urllib.request.Request(server + "/api/v1/info", headers={"Accept": "application/json"})
try:
    with urllib.request.urlopen(request, timeout=8) as response:
        if response.status < 200 or response.status >= 300:
            raise SystemExit("Spoolman API returned HTTP %s" % response.status)
        json.loads(response.read().decode("utf-8"))
except Exception as error:
    raise SystemExit("Cannot reach Spoolman API at %s: %s" % (server, error))
print(server)
PY
}

component_loaded() {
    python3 - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:7125/server/info", timeout=3) as response:
    info = json.loads(response.read().decode("utf-8"))["result"]
if "spoolman" not in info.get("components", []):
    raise SystemExit(1)
PY
}

mark_installed() {
    touch "$INSTALLED_FILE" 2>/dev/null
    grep -qx 'spoolman' "$INSTALLED_FILE" 2>/dev/null || echo 'spoolman' >> "$INSTALLED_FILE"
}

mark_removed() {
    [ -f "$INSTALLED_FILE" ] && sed -i '/^spoolman$/d' "$INSTALLED_FILE"
}

install_spoolman() {
    require_root || return 1
    check_k3_config || return 1
    check_moonraker || { log_error "Moonraker is not responding; config was not changed."; return 1; }

    echo "Spoolman runs on a separate host; this connects K3 to that service."
    printf "Spoolman URL [http://<host-or-ip>:7912]: "
    IFS= read -r input_url
    [ -n "$input_url" ] || { log_info "Cancelled; no configuration changed."; return 0; }
    server_url=$(normalize_and_check_server "$input_url") || { log_error "Spoolman endpoint check failed; config was not changed."; return 1; }

    backup="$MOONRAKER_CONF.spoolman.bak.$(date +%Y%m%d-%H%M%S)"
    [ ! -e "$backup" ] || backup="$backup.$$"
    cp -p "$MOONRAKER_CONF" "$backup" || { log_error "Could not back up Moonraker config."; return 1; }
    python3 "$CONFIG_HELPER" set "$MOONRAKER_CONF" "$server_url" || return 1

    restart_moonraker
    attempt=0
    while [ "$attempt" -lt 30 ]; do
        if component_loaded 2>/dev/null; then
            mark_installed
            log_success "Moonraker Spoolman integration is active."
            log_info "Open Fluidd on port 4408 and refresh it; Spoolman tools are now available."
            log_info "Backup: $backup"
            log_info "This tracks filament usage; it does not select a physical K3 CFS slot."
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done

    log_error "Moonraker did not load its spoolman component; restoring the previous config."
    cp -p "$backup" "$MOONRAKER_CONF" || { log_error "Automatic config rollback failed; restore $backup manually."; return 1; }
    restart_moonraker
    return 1
}

remove_spoolman() {
    require_root || return 1
    check_k3_config || return 1
    if ! grep -q '^\[spoolman\]' "$MOONRAKER_CONF"; then
        log_info "No local [spoolman] section found; nothing to remove."
        mark_removed
        return 0
    fi

    backup="$MOONRAKER_CONF.spoolman.bak.$(date +%Y%m%d-%H%M%S)"
    [ ! -e "$backup" ] || backup="$backup.$$"
    cp -p "$MOONRAKER_CONF" "$backup" || { log_error "Could not back up Moonraker config."; return 1; }
    python3 "$CONFIG_HELPER" remove "$MOONRAKER_CONF" || return 1
    restart_moonraker
    mark_removed
    log_success "Spoolman disconnected from Moonraker."
    log_info "Backup: $backup"
}

case "$1" in
    install|configure) install_spoolman ;;
    remove) remove_spoolman ;;
    *) echo "Usage: $0 [install|configure|remove]"; exit 2 ;;
esac
