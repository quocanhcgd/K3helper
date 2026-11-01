#!/bin/sh
# Control i8 lights through firmware-provided tools and stock G-code.

LIGHT_CTRL=/usr/bin/light_ctrl.sh
WS281X_CTRL=/usr/bin/ws281x_led.sh
MOONRAKER_API=http://127.0.0.1:7125

log_error() { printf '[ERROR] %s\n' "$1" >&2; }

require_i8() {
    board=
    if [ -x /usr/bin/get_sn_mac.sh ]; then
        board=$(/usr/bin/get_sn_mac.sh board 2>/dev/null)
    elif [ -x /etc/ota_bin/get_ota_board_name.sh ]; then
        board=$(/etc/ota_bin/get_ota_board_name.sh 2>/dev/null)
    fi
    case "$(printf '%s' "$board" | tr -d '\r')" in
        CR3SUF030C10*) return 0 ;;
    esac
    log_error "This feature targets SparkX i8 board CR3SUF030C10."
    return 1
}

show_menu() {
    clear
    echo "i8 Camera and LED Controls"
    echo ""
    echo "  1) Auxiliary light on (firmware GPIO111 control)"
    echo "  2) Auxiliary light off"
    echo "  3) Auxiliary light status"
    echo "  4) Addressable LED strip on"
    echo "  5) Addressable LED strip off"
    echo "  6) Adjust LED strip effect and brightness"
    echo "  7) CFS box LED on"
    echo "  8) CFS box LED off"
    echo "  0) Back"
    echo ""
    printf "Enter choice: "
}

require_i8 || exit 1
[ "$(id -u)" = 0 ] || { log_error "Run this feature as root."; exit 1; }

show_menu
read choice
case "$choice" in
    1|2|3)
        [ -x "$LIGHT_CTRL" ] || { log_error "Firmware light controller is missing."; exit 1; }
        case "$choice" in
            1) "$LIGHT_CTRL" on ;;
            2) "$LIGHT_CTRL" off ;;
            3) "$LIGHT_CTRL" status ;;
        esac
        ;;
    4|5)
        [ -x "$WS281X_CTRL" ] || { log_error "Firmware WS281x controller is missing."; exit 1; }
        if [ ! -e /sys/class/ws281x_led/suspend ]; then
            log_error "The firmware WS281x LED controller is not available."
            exit 1
        fi
        if [ "$choice" = 4 ]; then
            "$WS281X_CTRL" --resume || exit 1
            echo "LED strip resumed."
        else
            "$WS281X_CTRL" --suspend || exit 1
            echo "LED strip suspended."
        fi
        ;;
    6)
        [ -x "$WS281X_CTRL" ] || { log_error "Firmware WS281x controller is missing."; exit 1; }
        echo "Supported effect IDs:"
        "$WS281X_CTRL" --help || exit 1
        printf "Effect ID (numbers only): "
        read effect_id
        case "$effect_id" in
            ''|*[!0-9]*) log_error "Effect ID must contain digits only."; exit 2 ;;
        esac
        printf "Brightness (0-255): "
        read brightness
        case "$brightness" in
            ''|*[!0-9]*) log_error "Brightness must be an integer from 0 to 255."; exit 2 ;;
        esac
        [ "$brightness" -le 255 ] || { log_error "Brightness must be from 0 to 255."; exit 2; }
        "$WS281X_CTRL" --effect "$effect_id" --brightness "$brightness"
        ;;
    7|8)
        switch=1
        [ "$choice" = 7 ] || switch=0
        python3 - "$MOONRAKER_API" "$switch" <<'PY'
import json
import sys
import urllib.request
base, switch = sys.argv[1:]
request = urllib.request.Request(
    base + "/printer/gcode/script",
    data=json.dumps({"script": "LED_SWITCH SWITCH=%s" % switch}).encode("utf-8"),
    method="POST",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(request, timeout=10) as response:
    result = json.loads(response.read())
print(result.get("result", "CFS box LED command sent."))
PY
        ;;
    0) exit 0 ;;
    *) log_error "Invalid choice."; exit 2 ;;
esac
