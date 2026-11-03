#!/bin/sh
# Install the K3 framebuffer screen viewer and Fluidd dashboard integration.

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
APP_SOURCE=$SCRIPT_DIR/scripts/screen_apps
APP_DIR=$SCRIPT_DIR/screen-apps
FLUIDD_DIR=$SCRIPT_DIR/fluidd
NGINX_CONF=/etc/nginx/nginx.conf
NGINX_BACKUP=$NGINX_CONF.k3-screen-apps.bak
SERVICE=/etc/init.d/k3-screen-apps
INSTALLED_FILE=$SCRIPT_DIR/.installed
LOCATION_MARKER="# k3-screen-apps-proxy"
THEME_MARKER="/* k3-screen-apps-camera-caption-v1 */"

log_info() { printf '[INFO] %s\n' "$1"; }
log_error() { printf '[ERROR] %s\n' "$1" >&2; }
log_success() { printf '[OK] %s\n' "$1"; }

require_prerequisites() {
    [ "$(id -u)" = 0 ] || { log_error "Run this installer as root."; return 1; }
    [ -x /usr/bin/get_sn_mac.sh ] || { log_error "Cannot identify the printer board."; return 1; }
    board=$(/usr/bin/get_sn_mac.sh board 2>/dev/null)
    case "$board" in CR0CUF039C13*) ;; *) log_error "Unsupported board '$board'."; return 1 ;; esac
    awk '$2 == "/etc" && $3 == "overlay" { found=1 } END { exit !found }' /proc/mounts || {
        log_error "The /etc overlay is not active; persistent service installation is unavailable."
        return 1
    }
    [ -c /dev/fb0 ] && [ -c /dev/input/event0 ] || { log_error "K3 framebuffer or touch device is missing."; return 1; }
    python3 -c 'import PIL' 2>/dev/null || { log_error "Python Pillow is required (the tested K3 image has Pillow 8.2)."; return 1; }
    [ -f "$APP_SOURCE/fb-http.py" ] && [ -f "$APP_SOURCE/LICENSE" ] && [ -f "$APP_SOURCE/html/index.html" ] || {
        log_error "Screen-apps package files are incomplete."; return 1;
    }
    [ -f "$APP_SOURCE/moonraker_webcam.py" ] || { log_error "Moonraker webcam registration helper is missing."; return 1; }
    [ -f "$FLUIDD_DIR/index.html" ] || { log_error "Fluidd is not installed at $FLUIDD_DIR."; return 1; }
}

write_service() {
    cat > "$SERVICE" <<'EOF'
#!/bin/sh /etc/rc.common

START=97
STOP=10
USE_PROCD=1

start_service() {
    procd_open_instance screen
    procd_set_param command /usr/bin/python3 /mnt/UDISK/helper-script/screen-apps/fb-http.py --fb /dev/fb0 --touch /dev/input/event0 --bind 127.0.0.1 --port 18092 --html-dir /mnt/UDISK/helper-script/screen-apps/html
    procd_set_param respawn 5 10 0
    procd_close_instance
}
EOF
    chmod 755 "$SERVICE"
}

write_nginx_proxy() {
    python3 - "$NGINX_CONF" "$NGINX_BACKUP" <<'PY'
import pathlib, re, shutil, sys
path, backup = map(pathlib.Path, sys.argv[1:])
text = path.read_text(encoding="utf-8")
marker = "# k3-screen-apps-proxy"
if marker not in text:
    if not backup.exists(): shutil.copy2(path, backup)
    blocks = []
    for match in re.finditer(r"\bserver\s*\{", text):
        start = match.start(); brace = text.find("{", start); depth = 0
        for pos in range(brace, len(text)):
            if text[pos] == "{": depth += 1
            elif text[pos] == "}":
                depth -= 1
                if depth == 0:
                    blocks.append((start, pos + 1, text[start:pos + 1])); break
    matches = [(a,b,s) for a,b,s in blocks if re.search(r"\blisten\s+4408\b", s)]
    if len(matches) != 1: raise SystemExit("Expected one nginx Fluidd server on port 4408")
    start, end, block = matches[0]
    location = '''
        location = /screen { return 301 /screen/; }
        location ^~ /screen/ {
            proxy_pass http://127.0.0.1:18092/;
            proxy_http_version 1.1;
            proxy_set_header Host $http_host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_read_timeout 30s;
        }
'''
    text = text[:end-1] + "\n        " + marker + location + text[end-1:]
    path.write_text(text, encoding="utf-8")
PY
}

remove_legacy_dashboard_injection() {
    python3 - "$FLUIDD_DIR" <<'PY'
import pathlib, re, sys
root = pathlib.Path(sys.argv[1])
index = root / "index.html"
if index.is_file():
    text = index.read_text(encoding="utf-8")
    cleaned = re.sub(
        r'<script\s+id=["\']creality-screen-apps-script["\'][^>]*></script>',
        "", text, flags=re.IGNORECASE,
    )
    if cleaned != text:
        index.write_text(cleaned, encoding="utf-8")
(root / "creality-screen-apps.js").unlink(missing_ok=True)
PY
}

theme_css_path() {
    if [ -d /mnt/SDCARD/cxsw/printer_data/config ]; then
        printf '%s/.fluidd-theme/custom.css\n' /mnt/SDCARD/cxsw/printer_data/config
    else
        printf '%s/.fluidd-theme/custom.css\n' /mnt/UDISK/printer_data/config
    fi
}

install_camera_caption_css() {
    css_path=$(theme_css_path)
    mkdir -p "$(dirname "$css_path")" || return 1
    [ -f "$css_path" ] || : > "$css_path" || return 1
    if ! grep -Fq "$THEME_MARKER" "$css_path"; then
        printf '\n' >> "$css_path"
        cat "$APP_SOURCE/fluidd-camera-caption.css" >> "$css_path" || return 1
    fi
}

remove_camera_caption_css() {
    css_path=$(theme_css_path)
    [ -f "$css_path" ] || return 0
    python3 - "$css_path" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
pattern = re.compile(
    r"\n?/\* k3-screen-apps-camera-caption-v1 \*/\n"
        r'iframe\.camera-image\[src\*="/screen/"\] \+ \.camera-name \{.*?\n\}\n?',
    re.DOTALL,
)
updated = pattern.sub("\n", text, count=1)
if updated != text:
    path.write_text(updated, encoding="utf-8")
PY
}

mark_installed() {
    touch "$INSTALLED_FILE"
    grep -qx 'k3_screen_apps' "$INSTALLED_FILE" 2>/dev/null || echo 'k3_screen_apps' >> "$INSTALLED_FILE"
}

install_screen() {
    require_prerequisites || return 1
    mkdir -p "$APP_DIR/html" || return 1
    cp "$APP_SOURCE/fb-http.py" "$APP_DIR/fb-http.py" || return 1
    cp "$APP_SOURCE/LICENSE" "$APP_DIR/LICENSE" || return 1
    cp "$APP_SOURCE/html/index.html" "$APP_DIR/html/index.html" || return 1
    cp "$APP_SOURCE/moonraker_webcam.py" "$APP_DIR/moonraker_webcam.py" || return 1
    chmod 755 "$APP_DIR/fb-http.py"
    remove_legacy_dashboard_injection || return 1
    install_camera_caption_css || return 1
    write_service || return 1
    write_nginx_proxy || return 1
    if ! nginx -t; then
        [ -f "$NGINX_BACKUP" ] && cp "$NGINX_BACKUP" "$NGINX_CONF"
        log_error "Nginx rejected the screen proxy; original configuration restored."
        return 1
    fi
    "$SERVICE" enable || return 1
    "$SERVICE" restart || return 1
    attempt=0
    while [ "$attempt" -lt 10 ]; do
        if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:18092/', timeout=2).read(128)" 2>/dev/null; then break; fi
        attempt=$((attempt + 1)); sleep 1
    done
    if [ "$attempt" -ge 10 ]; then log_error "Screen service did not start; inspect logread."; return 1; fi
    python3 "$APP_DIR/moonraker_webcam.py" register || return 1
    nginx -t && /etc/init.d/nginx restart || return 1
    mark_installed
    python3 "$SCRIPT_DIR/scripts/k3_boot_recovery.py" install || {
        log_error "K3 boot recovery service could not be enabled."
        return 1
    }
    log_success "Screen viewer is integrated at http://<printer-ip>:4408/screen/"
}

remove_screen() {
    [ "$(id -u)" = 0 ] || { log_error "Run this script as root."; return 1; }
    if [ -f "$APP_DIR/moonraker_webcam.py" ]; then python3 "$APP_DIR/moonraker_webcam.py" unregister || return 1; fi
    [ -x "$SERVICE" ] && { "$SERVICE" stop >/dev/null 2>&1; "$SERVICE" disable >/dev/null 2>&1; rm -f "$SERVICE"; }
    remove_camera_caption_css || return 1
    rm -f /etc/rc.d/S97k3-screen-apps
    python3 - "$NGINX_CONF" <<'PY'
import pathlib, re, sys
path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
pattern = re.compile(r"\n\s*# k3-screen-apps-proxy\n\s*location = /screen \{[^}]*\}\s*location \^~ /screen/ \{[^}]*\}\s*")
updated, count = pattern.subn("\n", text, count=1)
if count: path.write_text(updated, encoding="utf-8")
PY
    if [ -f "$NGINX_BACKUP" ]; then
        nginx -t && /etc/init.d/nginx restart || return 1
        rm -f "$NGINX_BACKUP"
    fi
    rm -rf "$APP_DIR"
    [ -f "$INSTALLED_FILE" ] && sed -i '/^k3_screen_apps$/d' "$INSTALLED_FILE"
    log_success "K3 screen viewer removed."
}

case "$1" in
    install|repair|update) install_screen ;;
    remove) remove_screen ;;
    *) echo "Usage: $0 [install|repair|update|remove]"; exit 2 ;;
esac
