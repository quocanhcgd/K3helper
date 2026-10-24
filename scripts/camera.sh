#!/bin/sh
# K3 camera bridge using the firmware's built-in Fluidd go2rtc adapter.

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
GO2RTC=$SCRIPT_DIR/go2rtc
GO2RTC_CONFIG=$SCRIPT_DIR/go2rtc-k3.yaml
PRINTER_IP_FILE=$SCRIPT_DIR/go2rtc-k3.ip
WATCHDOG_SOURCE=$SCRIPT_DIR/scripts/camera_watchdog.py
WATCHDOG=$SCRIPT_DIR/camera_watchdog.py
FLUIDD_COMPAT=$SCRIPT_DIR/scripts/fluidd_k3_compat.py
FLUIDD_SOURCE=/usr/share/fluidd
FLUIDD_DIR=$SCRIPT_DIR/fluidd
NGINX_CONF=/etc/nginx/nginx.conf
SERVICE=/etc/init.d/go2rtc-k3
INSTALLED_FILE=$SCRIPT_DIR/.installed
STREAM_NAME=k3
CAMERA_NAME="K3 Camera"

log_info() { printf '[INFO] %s\n' "$1"; }
log_error() { printf '[ERROR] %s\n' "$1" >&2; }
log_success() { printf '[OK] %s\n' "$1"; }

require_root() {
    [ "$(id -u)" = 0 ] || { log_error "Run this script as root."; return 1; }
}

require_k3() {
    if [ -x /usr/bin/get_sn_mac.sh ]; then
        board=$(/usr/bin/get_sn_mac.sh board 2>/dev/null)
        case "$board" in
            CR0CUF039C13*) ;;
            *) log_error "Unsupported board '$board'; this installer targets K3 board CR0CUF039C13."; return 1 ;;
        esac
    else
        log_error "Cannot identify the printer board (get_sn_mac.sh is missing)."
        return 1
    fi
    [ -f /usr/share/fluidd/moonraker.conf ] || [ -d /usr/share/fluidd/assets ] || {
        log_error "Fluidd was not found at /usr/share/fluidd."
        return 1
    }
}

require_overlay() {
    if ! awk '$2 == "/etc" && $3 == "overlay" { found=1 } END { exit !found }' /proc/mounts; then
        log_error "The firmware overlay is not active; system startup files are read-only."
        echo "Enable the firmware overlay and reboot first:"
        echo "  touch /mnt/SDCARD/overlay/enable.txt"
        echo "  reboot"
        echo "The firmware allocates a 512 MiB overlay image on the SD card."
        return 1
    fi
}

install_fluidd_compat() {
    [ -f "$FLUIDD_COMPAT" ] || { log_error "Missing $FLUIDD_COMPAT"; return 1; }
    python3 "$FLUIDD_COMPAT" install \
        --source "$FLUIDD_SOURCE" \
        --destination "$FLUIDD_DIR" \
        --nginx "$NGINX_CONF" \
        --refresh || return 1
    nginx -t || { log_error "Nginx rejected the Fluidd document-root change."; return 1; }
    /etc/init.d/nginx restart || { log_error "Could not restart Nginx."; return 1; }
}

get_printer_ip() {
    ip route get 1 2>/dev/null | sed -n 's/.* src \([^ ]*\).*/\1/p' | head -n 1
}

mark_installed() {
    touch "$INSTALLED_FILE"
    grep -qx 'camera_support_k3' "$INSTALLED_FILE" 2>/dev/null || echo 'camera_support_k3' >> "$INSTALLED_FILE"
}

mark_removed() {
    [ -f "$INSTALLED_FILE" ] && sed -i '/^camera_support_k3$/d' "$INSTALLED_FILE"
}

write_go2rtc_config() {
    printer_ip=$1
    printf '%s\n' "$printer_ip" > "$PRINTER_IP_FILE"
    cat > "$GO2RTC_CONFIG" <<EOF
api:
  listen: :1984
  origin: '*'

streams:
  $STREAM_NAME:
    - "webrtc:http://127.0.0.1:8000/call/webrtc_local#format=creality"

webrtc:
  listen: :8555
  candidates:
    - $printer_ip
  ice_servers:
    - urls:
        - stun:stun.l.google.com:19302
EOF
}

write_service() {
    cat > "$SERVICE" <<'EOF'
#!/bin/sh /etc/rc.common

START=98
USE_PROCD=1

start_service() {
    procd_open_instance go2rtc
    procd_set_param command /mnt/UDISK/helper-script/go2rtc -config /mnt/UDISK/helper-script/go2rtc-k3.yaml
    procd_set_param respawn 5 10 0
    procd_close_instance

    procd_open_instance watchdog
    procd_set_param command /usr/bin/python3 /mnt/UDISK/helper-script/camera_watchdog.py
    procd_set_param respawn 5 10 0
    procd_close_instance
}
EOF
    chmod 755 "$SERVICE"
}

register_camera() {
    printer_ip=$1
    python3 - "$printer_ip" "$STREAM_NAME" "$CAMERA_NAME" <<'PY'
import json
import sys
import urllib.request

ip, stream, name = sys.argv[1:]
base = "http://127.0.0.1:7125/server/webcams"
with urllib.request.urlopen(base + "/list", timeout=5) as response:
    webcams = json.loads(response.read()).get("result", {}).get("webcams", [])
if any(camera.get("name") == name for camera in webcams):
    print("K3 camera is already registered with Moonraker")
    raise SystemExit(0)

camera = {
    "name": name,
    "location": "printer",
    "service": "webrtc-go2rtc",
    "target_fps": 15,
    "stream_url": "http://%s:1984/?src=%s" % (ip, stream),
    "snapshot_url": "http://%s:1984/api/frame.jpeg?src=%s" % (ip, stream),
    "flip_horizontal": False,
    "flip_vertical": False,
    "rotation": 0,
}
request = urllib.request.Request(
    base + "/item",
    data=json.dumps(camera).encode(),
    method="POST",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(request, timeout=10) as response:
    response.read()
print("K3 camera registered with Moonraker")
PY
}

wait_for_go2rtc() {
    attempt=0
    while [ "$attempt" -lt 15 ]; do
        if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:1984/api/streams', timeout=2).read()" 2>/dev/null; then
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
    return 1
}

install_camera() {
    require_root || return 1
    require_k3 || return 1
    require_overlay || return 1
    [ -f "$WATCHDOG_SOURCE" ] || { log_error "Missing $WATCHDOG_SOURCE"; return 1; }
    install_fluidd_compat || return 1

    printer_ip=$(get_printer_ip)
    case "$printer_ip" in
        ""|*[!0-9.]* ) log_error "Could not determine the printer's LAN IP."; return 1 ;;
    esac

    if [ ! -x "$GO2RTC" ]; then
        log_info "Downloading go2rtc for 32-bit ARM..."
        python3 - "$GO2RTC" <<'PY' || return 1
import sys
import urllib.request
urllib.request.urlretrieve(
    "https://github.com/AlexxIT/go2rtc/releases/latest/download/go2rtc_linux_arm",
    sys.argv[1],
)
PY
        chmod 755 "$GO2RTC" || return 1
    fi

    cp "$WATCHDOG_SOURCE" "$WATCHDOG" || return 1
    write_go2rtc_config "$printer_ip" || return 1
    write_service || return 1

    if ! /etc/init.d/go2rtc-k3 enable; then
        log_error "Could not enable the go2rtc procd service."
        return 1
    fi
    /etc/init.d/go2rtc-k3 restart || return 1

    if ! wait_for_go2rtc; then
        log_error "go2rtc did not start; inspect /mnt/UDISK/helper-script/go2rtc-k3.yaml and the system log."
        return 1
    fi

    register_camera "$printer_ip" || {
        log_error "Moonraker rejected the camera entry. The service is running; camera registration can be retried."
        return 1
    }

    mark_installed
    log_success "K3 camera installed. Fluidd connects directly to go2rtc on port 1984."
}

remove_camera() {
    require_root || return 1
    require_k3 || return 1
    require_overlay || return 1

    python3 - "$CAMERA_NAME" <<'PY'
import sys
import urllib.parse
import urllib.request
name = urllib.parse.urlencode({"name": sys.argv[1]})
request = urllib.request.Request(
    "http://127.0.0.1:7125/server/webcams/item?" + name, method="DELETE"
)
try:
    urllib.request.urlopen(request, timeout=5).read()
except Exception:
    pass
PY

    if [ -x "$SERVICE" ]; then
        "$SERVICE" stop >/dev/null 2>&1
        "$SERVICE" disable >/dev/null 2>&1
        rm -f "$SERVICE"
    fi
    rm -f /etc/rc.d/S98go2rtc-k3 "$GO2RTC" "$GO2RTC_CONFIG" "$PRINTER_IP_FILE" "$WATCHDOG"
    mark_removed
    log_success "K3 camera support removed."
}

case "$1" in
    install|repair|update) install_camera ;;
    remove) remove_camera ;;
    *) echo "Usage: $0 [install|repair|update|remove]"; exit 2 ;;
esac
