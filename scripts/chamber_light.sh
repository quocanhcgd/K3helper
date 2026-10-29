#!/bin/sh
# Install or remove Fluidd macros backed by Creality's local light WebSocket.

SCRIPT_DIR=/mnt/UDISK/helper-script
PRINTER_CFG=/mnt/UDISK/printer_data/config/printer.cfg
MOONRAKER_STOCK_CONF=/usr/share/moonraker/moonraker.conf
MOONRAKER_PATH_HELPER=$SCRIPT_DIR/scripts/moonraker_config_path.py
MOONRAKER_CONFIG_HELPER=$SCRIPT_DIR/scripts/chamber_light_moonraker_config.py
STARTUP_HELPER=$SCRIPT_DIR/scripts/moonraker_startup_config.py
SPOOLMAN_CONFIG_HELPER=$SCRIPT_DIR/scripts/spoolman_config.py
INSTALLED_FILE=$SCRIPT_DIR/.installed
. "$SCRIPT_DIR/scripts/system.sh"

if ! is_k3; then
    log_error "The Creality chamber-light WebSocket integration targets K3 only."
    exit 1
fi

require_root() {
    [ "$(id -u)" = 0 ] || { log_error "Run this script as root."; return 1; }
}

resolve_moonraker_config() {
    active=$(python3 "$MOONRAKER_PATH_HELPER") || return 1
    case "$active" in
        "$MOONRAKER_STOCK_CONF")
            MOONRAKER_CONF=$(python3 "$MOONRAKER_PATH_HELPER" wrapper) || return 1
            if [ ! -e "$MOONRAKER_CONF" ]; then
                python3 "$SPOOLMAN_CONFIG_HELPER" init-wrapper "$MOONRAKER_CONF" "$MOONRAKER_STOCK_CONF" || return 1
            fi
            ;;
        /mnt/SDCARD/*|/mnt/UDISK/*)
            MOONRAKER_CONF=$active
            ;;
        *)
            log_error "Unsupported Moonraker config path: $active"
            return 1
            ;;
    esac
    [ -f "$MOONRAKER_CONF" ] || { log_error "Moonraker config not found: $MOONRAKER_CONF"; return 1; }
    [ -w "$MOONRAKER_CONF" ] && [ -w "$(dirname "$MOONRAKER_CONF")" ] || {
        log_error "Moonraker config is not writable: $MOONRAKER_CONF"
        return 1
    }
    python3 "$STARTUP_HELPER" check >/dev/null || {
        log_error "Moonraker startup cannot load Helper Script components safely."
        return 1
    }
}

component_loaded() {
    python3 - <<'PY'
import json
import urllib.request
with urllib.request.urlopen("http://127.0.0.1:7125/server/info", timeout=3) as response:
    info = json.loads(response.read().decode("utf-8")).get("result", {})
if "chamber_light_ws" not in info.get("components", []):
    raise SystemExit(1)
PY
}

macro_loaded() {
    python3 - <<'PY'
import json
import urllib.request
with urllib.request.urlopen("http://127.0.0.1:7125/printer/objects/list", timeout=5) as response:
    objects = json.loads(response.read().decode("utf-8")).get("result", {}).get("objects", [])
required = {"gcode_macro CHAMBER_LED_ON", "gcode_macro CHAMBER_LED_OFF"}
if not required.issubset(objects):
    raise SystemExit(1)
if "output_pin nozzle_light" in objects or "output_pin chamber_led" in objects:
    raise SystemExit("A Klipper output pin still owns the chamber-light GPIO")
PY
}

klipper_ready() {
    python3 - <<'PY'
import json
import urllib.request
with urllib.request.urlopen("http://127.0.0.1:7125/printer/info", timeout=3) as response:
    state = json.loads(response.read().decode("utf-8")).get("result", {}).get("state")
if state != "ready":
    raise SystemExit(1)
PY
}

mark_installed() {
    touch "$INSTALLED_FILE" 2>/dev/null
    grep -qx 'chamber_light' "$INSTALLED_FILE" 2>/dev/null || echo 'chamber_light' >> "$INSTALLED_FILE"
}

mark_removed() {
    [ -f "$INSTALLED_FILE" ] && sed -i '/^chamber_light$/d' "$INSTALLED_FILE"
}

install_light() {
    require_root || return 1
    [ -f "$MOONRAKER_CONFIG_HELPER" ] && [ -f "$SCRIPT_DIR/scripts/chamber_light_component.py" ] || {
        log_error "The chamber-light Moonraker bridge files are missing."
        return 1
    }
    resolve_moonraker_config || { log_error "Could not resolve a writable Moonraker config."; return 1; }

    moonraker_backup=$MOONRAKER_CONF.k3helper-chamber-light.bak
    if [ ! -e "$moonraker_backup" ]; then cp -p "$MOONRAKER_CONF" "$moonraker_backup" || return 1; fi
    python3 "$STARTUP_HELPER" patch "$MOONRAKER_CONF" >/dev/null || {
        log_error "Could not configure Moonraker to load the Helper bridge."
        return 1
    }
    python3 "$MOONRAKER_CONFIG_HELPER" install "$MOONRAKER_CONF" || return 1

    restart_moonraker || return 1
    attempt=0
    while [ "$attempt" -lt 30 ]; do
        component_loaded 2>/dev/null && break
        attempt=$((attempt + 1))
        sleep 1
    done
    if ! component_loaded 2>/dev/null; then
        log_error "Moonraker did not load the chamber-light WebSocket bridge; restoring its config."
        cp -p "$moonraker_backup" "$MOONRAKER_CONF"
        restart_moonraker >/dev/null 2>&1
        return 1
    fi

    if ! python3 "$SCRIPT_DIR/scripts/chamber_light_config.py" install "$PRINTER_CFG"; then
        log_error "Fluidd macros were not installed; leaving the working WebSocket bridge active."
        return 1
    fi
    if ! restart_klipper; then
        python3 "$SCRIPT_DIR/scripts/chamber_light_config.py" remove "$PRINTER_CFG" >/dev/null 2>&1
        restart_klipper >/dev/null 2>&1
        log_error "Klipper restart failed; removed the Fluidd macros."
        return 1
    fi
    attempt=0
    while [ "$attempt" -lt 30 ]; do
        klipper_ready 2>/dev/null && break
        attempt=$((attempt + 1))
        sleep 1
    done
    if ! klipper_ready || ! macro_loaded; then
        log_error "Klipper did not load both WebSocket macros; removing the macro include."
        python3 "$SCRIPT_DIR/scripts/chamber_light_config.py" remove "$PRINTER_CFG" || return 1
        restart_klipper || return 1
        return 1
    fi
    mark_installed
    log_success "Fluidd chamber-light macros now use Creality's WebSocket without claiming GPIO42."
    log_info "Moonraker config backup: $moonraker_backup"
}

remove_light() {
    require_root || return 1
    resolve_moonraker_config || { log_error "Could not resolve Moonraker config."; return 1; }
    python3 "$SCRIPT_DIR/scripts/chamber_light_config.py" remove "$PRINTER_CFG" || return 1
    restart_klipper || return 1
    python3 "$MOONRAKER_CONFIG_HELPER" remove "$MOONRAKER_CONF" || return 1
    restart_moonraker || return 1
    mark_removed
    log_success "Fluidd chamber-light macros and their Moonraker bridge were removed."
}

case "$1" in
    install|repair) install_light ;;
    remove) remove_light ;;
    *) echo "Usage: $0 [install|repair|remove]"; exit 2 ;;
esac
