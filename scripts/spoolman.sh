#!/bin/sh
# Connect K3 Moonraker and Fluidd to an existing Spoolman server.

SCRIPT_DIR=/mnt/UDISK/helper-script
CONFIG_DIR=/mnt/UDISK/printer_data/config
MOONRAKER_CONF=
INSTALLED_FILE=$SCRIPT_DIR/.installed
. "$SCRIPT_DIR/scripts/system.sh"

CONFIG_HELPER=$SCRIPT_DIR/scripts/spoolman_config.py
CONFIG_PATH_HELPER=$SCRIPT_DIR/scripts/moonraker_config_path.py
STARTUP_HELPER=$SCRIPT_DIR/scripts/moonraker_startup_config.py
MOONRAKER_STOCK_CONF=/usr/share/moonraker/moonraker.conf
NEED_STARTUP_PATCH=0
CUSTOM_COMPONENT=$SCRIPT_DIR/scripts/spoolman_component.py
CUSTOM_COMPONENT_ENTRY=$SCRIPT_DIR/scripts/spoolman.py
CUSTOM_SITE=$SCRIPT_DIR/scripts/sitecustomize.py

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
    ACTIVE_MOONRAKER_CONF=$(python3 "$CONFIG_PATH_HELPER") || {
        log_error "Could not identify Moonraker's active config file."
        log_info "No configuration was changed."
        return 1
    }
    case "$ACTIVE_MOONRAKER_CONF" in
        /mnt/SDCARD/*|/mnt/UDISK/*)
            MOONRAKER_CONF=$ACTIVE_MOONRAKER_CONF
            ;;
        "$MOONRAKER_STOCK_CONF")
            MOONRAKER_CONF=$(python3 "$CONFIG_PATH_HELPER" wrapper) || {
                log_error "Could not find the writable K3 printer config directory."
                return 1
            }
            NEED_STARTUP_PATCH=1
            if ! awk '$2 == "/etc" && $3 == "overlay" && $4 ~ /(^|,)rw(,|$)/ { found=1 } END { exit !found }' /proc/mounts; then
                log_error "The /etc overlay is not mounted read-write; cannot persist the Moonraker startup change."
                return 1
            fi
            [ -f "$STARTUP_HELPER" ] || { log_error "Missing $STARTUP_HELPER"; return 1; }
            python3 "$STARTUP_HELPER" check >/dev/null || { log_error "Moonraker startup script cannot be safely patched."; return 1; }
            ;;
        *)
            log_error "Unsupported Moonraker config path: $ACTIVE_MOONRAKER_CONF"
            return 1
            ;;
    esac
    CUSTOM_COMPONENT_ENABLED=0
    if ! find /usr/share/moonraker -type f -name spoolman.py -print 2>/dev/null | grep -q .; then
        if [ ! -f "$CUSTOM_COMPONENT" ] || [ ! -f "$CUSTOM_COMPONENT_ENTRY" ] || [ ! -f "$CUSTOM_SITE" ]; then
            log_error "Moonraker has no Spoolman component and the K3 bridge files are missing."
            log_info "No configuration was changed."
            return 1
        fi
        log_info "Using the K3 Spoolman compatibility bridge."
        CUSTOM_COMPONENT_ENABLED=1
        NEED_STARTUP_PATCH=1
    fi
    if [ "$NEED_STARTUP_PATCH" = "1" ]; then
        [ -f "$STARTUP_HELPER" ] || { log_error "Missing $STARTUP_HELPER"; return 1; }
        python3 "$STARTUP_HELPER" check >/dev/null || { log_error "Moonraker startup script cannot be safely patched."; return 1; }
    fi
    if [ ! -e "$MOONRAKER_CONF" ] && [ "$NEED_STARTUP_PATCH" != "1" ]; then
        log_error "Moonraker's active config file was not found: $MOONRAKER_CONF"
        return 1
    fi
    if [ -L "$MOONRAKER_CONF" ]; then
        log_error "Moonraker config is a symbolic link; refusing to replace it atomically."
        return 1
    fi
    if [ -e "$MOONRAKER_CONF" ] && [ ! -w "$MOONRAKER_CONF" ]; then
        log_error "Moonraker's active config is not writable: $MOONRAKER_CONF"
        return 1
    fi
    if [ ! -w "$(dirname "$MOONRAKER_CONF")" ]; then
        log_error "Moonraker config directory is not writable: $(dirname "$MOONRAKER_CONF")"
        return 1
    fi
    [ -f "$CONFIG_HELPER" ] || { log_error "Missing $CONFIG_HELPER"; return 1; }
    log_info "Using active Moonraker config: $MOONRAKER_CONF"
}

config_status() {
    check_k3_config || return 1
    echo "[INFO] Resolved Moonraker config: $MOONRAKER_CONF"
    echo "[INFO] Config directory: $(dirname "$MOONRAKER_CONF")"
    if [ -f "$MOONRAKER_CONF" ]; then
        echo "[INFO] Config is readable: yes"
        grep -n -A4 -B1 '^\[spoolman\]' "$MOONRAKER_CONF" 2>/dev/null || true
    else
        echo "[INFO] Config is readable: no (wrapper will be created during install)"
    fi
    if [ -w "$(dirname "$MOONRAKER_CONF")" ]; then
        echo "[INFO] Config directory is writable: yes"
    else
        echo "[INFO] Config directory is writable: no"
    fi
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
if "://" not in raw:
    raw = "http://" + raw
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

diagnose_spoolman() {
    echo "[INFO] Moonraker config access:"
    config_status || true
    echo "[INFO] Moonraker component/config status:"
    python3 - <<'PY'
import json
import urllib.error
import urllib.request

def get(path):
    try:
        with urllib.request.urlopen("http://127.0.0.1:7125" + path, timeout=5) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")
    except Exception as error:
        return "ERROR", str(error)

for path in ("/server/info", "/server/config", "/server/spoolman/status", "/server/spoolman/spool_id"):
    status, body = get(path)
    print("%s [%s] %s" % (path, status, body[:1200]))
PY
    echo "[INFO] Recent Moonraker Spoolman/import log lines:"
    for log in /mnt/SDCARD/cxsw/printer_data/log/moonraker.log /mnt/SDCARD/cxsw/printer_data/logs/moonraker.log /mnt/UDISK/printer_data/logs/moonraker.log; do
        if [ -f "$log" ]; then
            grep -iE 'spoolman|component.*(fail|load)|import.*error|traceback' "$log" | tail -50
        fi
    done
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
    wrapper_created=0
    if [ -e "$MOONRAKER_CONF" ]; then
        cp -p "$MOONRAKER_CONF" "$backup" || { log_error "Could not back up Moonraker config."; return 1; }
    elif [ "$NEED_STARTUP_PATCH" = "1" ]; then
        wrapper_created=1
    fi
    if [ "$wrapper_created" = "1" ]; then
        python3 "$CONFIG_HELPER" init-wrapper "$MOONRAKER_CONF" "$MOONRAKER_STOCK_CONF" || return 1
    fi
    if [ -e "$MOONRAKER_CONF" ]; then
        cp -p "$MOONRAKER_CONF" "$backup" || { log_error "Could not back up Moonraker config."; return 1; }
    fi
    python3 "$CONFIG_HELPER" set "$MOONRAKER_CONF" "$server_url" || return 1
    startup_patched=0
    if [ "$NEED_STARTUP_PATCH" = "1" ]; then
        if ! python3 "$STARTUP_HELPER" patch "$MOONRAKER_CONF"; then
            if [ "$wrapper_created" = "1" ]; then rm -f "$MOONRAKER_CONF"; else cp -p "$backup" "$MOONRAKER_CONF"; fi
            log_error "Could not switch Moonraker to the persistent config; restored its config file."
            return 1
        fi
        startup_patched=1
    fi

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
    if [ "$wrapper_created" = "1" ]; then
        rm -f "$MOONRAKER_CONF"
    else
        cp -p "$backup" "$MOONRAKER_CONF" || { log_error "Automatic config rollback failed; restore $backup manually."; return 1; }
    fi
    if [ "$startup_patched" = "1" ]; then
        python3 "$STARTUP_HELPER" restore || log_error "Could not restore the original Moonraker startup script."
    fi
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
    if [ -f "$(dirname "$STARTUP_HELPER")/moonraker_startup_config.py" ]; then
        python3 "$STARTUP_HELPER" restore >/dev/null 2>&1 || true
    fi
    restart_moonraker
    mark_removed
    log_success "Spoolman disconnected from Moonraker."
    log_info "Backup: $backup"
}

case "$1" in
    install|configure) install_spoolman ;;
    remove) remove_spoolman ;;
    status|diagnose) diagnose_spoolman ;;
    config-status) config_status ;;
    *) echo "Usage: $0 [install|configure|remove|status]"; exit 2 ;;
esac
