#!/bin/sh
# Register the firmware's built-in camera page as a Fluidd iframe camera.

CAMERA_NAME="SparkX i8 Camera"
FLUIDD_ROOT=/usr/share/fluidd
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

get_printer_ip() {
    ip -4 -o addr show scope global 2>/dev/null |
        awk '{split($4, parts, "/"); if (parts[1] !~ /^127\./) {print parts[1]; exit}}'
}

show_menu() {
    clear
    echo "i8 Fluidd Camera"
    echo ""
    echo "  1) Add camera to Fluidd"
    echo "  2) Show current camera entry"
    echo "  3) Remove helper-managed camera entry"
    echo "  0) Back"
    echo ""
    printf "Enter choice: "
}

require_i8 || exit 1
[ "$(id -u)" = 0 ] || { log_error "Run this feature as root."; exit 1; }
[ -f "$FLUIDD_ROOT/camera.html" ] || { log_error "Firmware camera page not found at $FLUIDD_ROOT/camera.html."; exit 1; }

show_menu
read choice
case "$choice" in
    1)
        printer_ip=$(get_printer_ip)
        case "$printer_ip" in
            ""|*[!0-9.]* ) log_error "Could not determine the printer LAN IP."; exit 1 ;;
        esac
        python3 - "$MOONRAKER_API" "$CAMERA_NAME" "$printer_ip" <<'PY'
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

base, name, ip = sys.argv[1:]
api = base + "/server/webcams"
with urllib.request.urlopen(api + "/list", timeout=5) as response:
    webcams = json.loads(response.read()).get("result", {}).get("webcams", [])
for webcam in webcams:
    if webcam.get("name") == name:
        print("Camera entry already exists: %s" % webcam.get("stream_url", ""))
        raise SystemExit(0)

camera = {
    "name": name,
    "location": "printer",
    "service": "iframe",
    "target_fps": 15,
    "stream_url": "http://%s:4408/camera.html" % ip,
    "snapshot_url": "",
    "flip_horizontal": False,
    "flip_vertical": False,
    "rotation": 0,
}
request = urllib.request.Request(
    api + "/item",
    data=json.dumps(camera).encode("utf-8"),
    method="POST",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(request, timeout=10) as response:
    response.read()
print("Added %s to Fluidd: %s" % (name, camera["stream_url"]))
print("Refresh Fluidd and check the Camera panel.")
PY
        ;;
    2)
        python3 - "$MOONRAKER_API" "$CAMERA_NAME" <<'PY'
import json
import sys
import urllib.request
base, name = sys.argv[1:]
with urllib.request.urlopen(base + "/server/webcams/list", timeout=5) as response:
    webcams = json.loads(response.read()).get("result", {}).get("webcams", [])
for webcam in webcams:
    if webcam.get("name") == name:
        print(json.dumps(webcam, indent=2, sort_keys=True))
        break
else:
    print("No helper-managed i8 camera entry is configured.")
PY
        ;;
    3)
        python3 - "$MOONRAKER_API" "$CAMERA_NAME" <<'PY'
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
base, name = sys.argv[1:]
query = urllib.parse.urlencode({"name": name})
request = urllib.request.Request(base + "/server/webcams/item?" + query, method="DELETE")
try:
    with urllib.request.urlopen(request, timeout=10) as response:
        print(response.read().decode("utf-8", "replace"))
except urllib.error.HTTPError as exc:
    if exc.code == 404:
        print("No helper-managed i8 camera entry exists.")
    else:
        raise
PY
        ;;
    0) exit 0 ;;
    *) log_error "Invalid choice."; exit 2 ;;
esac
