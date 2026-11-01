#!/bin/sh
# Install or remove Fluidd macros backed by Creality's local light WebSocket.

PACKAGE_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PACKAGE_SCRIPTS=$PACKAGE_ROOT/scripts
SCRIPT_DIR=/mnt/UDISK/helper-script
PRINTER_CFG=
MOONRAKER_STOCK_CONF=/usr/share/moonraker/moonraker.conf
MOONRAKER_PATH_HELPER=$PACKAGE_SCRIPTS/moonraker_config_path.py
MOONRAKER_CONFIG_HELPER=$PACKAGE_SCRIPTS/chamber_light_moonraker_config.py
STARTUP_HELPER=$PACKAGE_SCRIPTS/moonraker_startup_config.py
SPOOLMAN_CONFIG_HELPER=$PACKAGE_SCRIPTS/spoolman_config.py
CHAMBER_CONFIG_HELPER=$PACKAGE_SCRIPTS/chamber_light_config.py
COMPONENT_SOURCE=$PACKAGE_SCRIPTS/chamber_light_component.py
COMPONENT_LOADER_SOURCE=$PACKAGE_SCRIPTS/components/chamber_light_ws.py
INSTALLED_FILE=$SCRIPT_DIR/.installed
SYSTEM_HELPER=$PACKAGE_SCRIPTS/system.sh
if [ ! -r "$SYSTEM_HELPER" ]; then
    printf '[ERROR] The signed LED bundle is missing %s.\n' "$SYSTEM_HELPER" >&2
    exit 1
fi
. "$SYSTEM_HELPER" || {
    printf '[ERROR] Could not load %s.\n' "$SYSTEM_HELPER" >&2
    exit 1
}

if ! is_k3; then
    log_error "The Creality chamber-light WebSocket integration targets K3 only."
    exit 1
fi

require_root() {
    [ "$(id -u)" = 0 ] || { log_error "Run this script as root."; return 1; }
}

require_storage() {
    if ! awk '$2 == "/mnt/UDISK" { found=1 } END { exit !found }' /proc/mounts; then
        log_error "Printer storage at /mnt/UDISK is not mounted."
        return 1
    fi
    mkdir -p "$SCRIPT_DIR/scripts/components" || {
        log_error "Could not prepare persistent Moonraker component storage."
        return 1
    }
}

require_feature_helpers() {
    for helper in \
        "$MOONRAKER_PATH_HELPER" \
        "$MOONRAKER_CONFIG_HELPER" \
        "$STARTUP_HELPER" \
        "$SPOOLMAN_CONFIG_HELPER" \
        "$CHAMBER_CONFIG_HELPER" \
        "$COMPONENT_SOURCE" \
        "$COMPONENT_LOADER_SOURCE"; do
        [ -r "$helper" ] || {
            log_error "Required file is missing from the signed LED bundle: $helper"
            return 1
        }
    done
}

resolve_printer_config() {
    candidate=
    if [ "$active" != "$MOONRAKER_STOCK_CONF" ]; then
        candidate=$(dirname "$active")/printer.cfg
        if [ -f "$candidate" ]; then
            PRINTER_CFG=$candidate
            return 0
        fi
    fi
    case "$active" in
        /mnt/UDISK/*)
            candidates="/mnt/UDISK/printer_data/config/printer.cfg /mnt/SDCARD/cxsw/printer_data/config/printer.cfg"
            ;;
        *)
            candidates="/mnt/SDCARD/cxsw/printer_data/config/printer.cfg /mnt/UDISK/printer_data/config/printer.cfg"
            ;;
    esac
    for candidate in $candidates; do
        if [ -f "$candidate" ]; then
            PRINTER_CFG=$candidate
            return 0
        fi
    done
    log_error "Could not find printer.cfg next to the active Moonraker configuration."
    return 1
}

install_bridge_file() {
    source_file=$1
    target_file=$2
    expected_marker=$3
    if [ -e "$target_file" ] && ! grep -Fq "$expected_marker" "$target_file"; then
        log_error "Refusing to replace an unmanaged file: $target_file"
        return 1
    fi
    temporary=$target_file.tmp.$$
    cp "$source_file" "$temporary" || { rm -f "$temporary"; return 1; }
    chmod 644 "$temporary" || { rm -f "$temporary"; return 1; }
    mv -f "$temporary" "$target_file" || { rm -f "$temporary"; return 1; }
}

install_bridge_files() {
    install_bridge_file "$COMPONENT_SOURCE" \
        "$SCRIPT_DIR/scripts/chamber_light_component.py" "class ChamberLightBridge" || return 1
    install_bridge_file "$COMPONENT_LOADER_SOURCE" \
        "$SCRIPT_DIR/scripts/components/chamber_light_ws.py" "chamber_light_component import"
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
    touch "$INSTALLED_FILE" || return 1
    grep -qx 'chamber_light' "$INSTALLED_FILE" 2>/dev/null ||
        printf '%s\n' 'chamber_light' >> "$INSTALLED_FILE"
}

mark_removed() {
    if [ -f "$INSTALLED_FILE" ]; then
        sed -i '/^chamber_light$/d' "$INSTALLED_FILE" || return 1
    fi
}

install_light() {
    require_root || return 1
    require_storage || return 1
    require_feature_helpers || return 1
    resolve_moonraker_config || { log_error "Could not resolve a writable Moonraker config."; return 1; }
    resolve_printer_config || return 1
    install_bridge_files || { log_error "Could not install the Moonraker runtime bridge files."; return 1; }

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

    if ! python3 "$CHAMBER_CONFIG_HELPER" install "$PRINTER_CFG"; then
        log_error "Fluidd macros were not installed; leaving the working WebSocket bridge active."
        return 1
    fi
    if ! restart_klipper; then
        python3 "$CHAMBER_CONFIG_HELPER" remove "$PRINTER_CFG" >/dev/null 2>&1
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
        python3 "$CHAMBER_CONFIG_HELPER" remove "$PRINTER_CFG" || return 1
        restart_klipper || return 1
        return 1
    fi
    mark_installed || { log_error "Could not record chamber-light installation state."; return 1; }
    log_success "Fluidd chamber-light macros now use Creality's WebSocket without claiming GPIO42."
    log_info "Moonraker config backup: $moonraker_backup"
}

remove_light() {
    require_root || return 1
    require_storage || return 1
    require_feature_helpers || return 1
    resolve_moonraker_config || { log_error "Could not resolve Moonraker config."; return 1; }
    resolve_printer_config || return 1
    python3 "$CHAMBER_CONFIG_HELPER" remove "$PRINTER_CFG" || return 1
    restart_klipper || return 1
    python3 "$MOONRAKER_CONFIG_HELPER" remove "$MOONRAKER_CONF" || return 1
    restart_moonraker || return 1
    mark_removed || { log_error "Could not clear chamber-light installation state."; return 1; }
    log_success "Fluidd chamber-light macros and their Moonraker bridge were removed."
}

case "$1" in
    install|repair) install_light ;;
    remove) remove_light ;;
    *) echo "Usage: $0 [install|repair|remove]"; exit 2 ;;
esac
