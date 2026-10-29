#!/bin/sh
# Install or remove the Klipper macro used to toggle the K3 chamber LED in Fluidd.

SCRIPT_DIR=/mnt/UDISK/helper-script
PRINTER_CFG=/mnt/UDISK/printer_data/config/printer.cfg
. "$SCRIPT_DIR/scripts/system.sh"

if ! is_k3; then
    log_error "This chamber-light macro targets K3 only."
    exit 1
fi

manage_light() {
    action=$1
    python3 "$SCRIPT_DIR/scripts/chamber_light_config.py" "$action" "$PRINTER_CFG" || return 1
    if [ "$action" = "install" ]; then
        if ! restart_klipper; then
            python3 "$SCRIPT_DIR/scripts/chamber_light_config.py" remove "$PRINTER_CFG" >/dev/null 2>&1
            restart_klipper >/dev/null 2>&1
            return 1
        fi
        if ! python3 - <<'PY'
import json
import urllib.request
payload = json.load(urllib.request.urlopen("http://127.0.0.1:7125/printer/objects/list", timeout=5))
objects = payload.get("result", {}).get("objects", [])
if not {"gcode_macro CHAMBER_LED_ON", "gcode_macro CHAMBER_LED_OFF"}.issubset(objects):
    raise SystemExit(1)
PY
        then
            log_error "Klipper did not load both chamber LED macros; restoring the previous config."
            python3 "$SCRIPT_DIR/scripts/chamber_light_config.py" remove "$PRINTER_CFG" || return 1
            restart_klipper || return 1
            return 1
        fi
        mark_installed "chamber_light"
        log_success "CHAMBER_LED_ON and CHAMBER_LED_OFF are available in Fluidd's Macros card."
    else
        restart_klipper || return 1
        mark_removed "chamber_light"
        log_success "The chamber LED macros were removed from Fluidd's Macros card."
    fi
}

case "$1" in
    install|repair) manage_light install ;;
    remove) manage_light remove ;;
    *) echo "Usage: $0 [install|repair|remove]"; exit 2 ;;
esac
