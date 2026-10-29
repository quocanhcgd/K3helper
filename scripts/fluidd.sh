#!/bin/sh
# fluidd.sh - Install, repair, or remove Fluidd for K2 Plus and K3
#
# The K2 Plus ships with Fluidd pre-installed at /usr/share/fluidd served on port 4408.
# This script can:
#   install  - download and install the latest Fluidd (replaces stock or broken install)
#   remove   - remove Fluidd static files (nginx block stays, port 4408 will 404)
#   restore  - restore the nginx config to serve Fluidd on port 4408

SCRIPT_DIR=/mnt/UDISK/helper-script
. "$SCRIPT_DIR/scripts/system.sh"

FLUIDD_DIR=/usr/share/fluidd
K3_FLUIDD_COMPAT=$SCRIPT_DIR/scripts/fluidd_k3_compat.py
MOONRAKER_STARTUP_HELPER=$SCRIPT_DIR/scripts/moonraker_startup_config.py
MOONRAKER_PATH_HELPER=$SCRIPT_DIR/scripts/moonraker_config_path.py
MOONRAKER_WRAPPER_HELPER=$SCRIPT_DIR/scripts/spoolman_config.py
MOONRAKER_COMPAT_CONFIG=$SCRIPT_DIR/scripts/moonraker_compat_config.py
MOONRAKER_COMPAT_COMPONENT=$SCRIPT_DIR/scripts/moonraker_compat_component.py
MOONRAKER_STOCK_CONF=/usr/share/moonraker/moonraker.conf
if is_k3; then
    FLUIDD_DIR=$SCRIPT_DIR/fluidd
fi
FLUIDD_URL=https://github.com/fluidd-core/fluidd/releases/latest/download/fluidd.zip
NGINX_CONF=/etc/nginx/nginx.conf

# Stock nginx server block for Fluidd — matches what ships on the K2 Plus
STOCK_FLUIDD_BLOCK='    server {
        listen 4408 default_server;

        access_log /var/log/nginx/fluidd-access.log;
        error_log /var/log/nginx/fluidd-error.log;

        gzip on;
        gzip_vary on;
        gzip_proxied any;
        gzip_proxied expired no-cache no-store private auth;
        gzip_comp_level 4;
        gzip_buffers 16 8k;
        gzip_http_version 1.1;
        gzip_types text/plain text/css text/xml text/javascript application/x-javascript application/json application/xml;

        root /usr/share/fluidd;
        index index.html;
        server_name _;
        client_max_body_size 0;
        proxy_request_buffering off;

        location / {
            try_files $uri $uri/ /index.html;
        }
        location = /index.html {
            add_header Cache-Control "no-store, no-cache, must-revalidate";
        }
        location /websocket {
            proxy_pass http://apiserver/websocket;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection $connection_upgrade;
            proxy_set_header Host $http_host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_read_timeout 86400;
        }
        location ~ ^/(printer|api|access|machine|server)/ {
            proxy_pass http://apiserver$request_uri;
            proxy_set_header Host $http_host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Scheme $scheme;
        }
        location /webcam/  { proxy_pass http://mjpgstreamer1/; }
        location /webcam2/ { proxy_pass http://mjpgstreamer2/; }
        location /webcam3/ { proxy_pass http://mjpgstreamer3/; }
        location /webcam4/ { proxy_pass http://mjpgstreamer4/; }
    }'

# ── Check internet ────────────────────────────────────────────────────────────

check_download_tool() {
    if which wget > /dev/null 2>&1; then
        DOWNLOAD_CMD="wget"
    elif which curl > /dev/null 2>&1; then
        DOWNLOAD_CMD="curl"
    elif which python3 > /dev/null 2>&1; then
        DOWNLOAD_CMD="python3"
    else
        log_error "No supported downloader found (wget, curl, or python3)."
        return 1
    fi
}

download_file() {
    local url="$1"
    local dest="$2"
    if [ "$DOWNLOAD_CMD" = "wget" ]; then
        wget -q --show-progress -O "$dest" "$url"
    elif [ "$DOWNLOAD_CMD" = "curl" ]; then
        curl -L --progress-bar -o "$dest" "$url"
    else
        python3 - "$url" "$dest" <<'PY'
import sys
import urllib.request
urllib.request.urlretrieve(sys.argv[1], sys.argv[2])
PY
    fi
}

extract_fluidd_archive() {
    archive=$1
    destination=$2
    if which unzip > /dev/null 2>&1; then
        unzip -q -o "$archive" -d "$destination"
        return $?
    fi
    if which python3 > /dev/null 2>&1; then
        python3 - "$archive" "$destination" <<'PY'
import pathlib
import sys
import zipfile

archive_path = sys.argv[1]
destination = pathlib.Path(sys.argv[2]).resolve()
destination.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(archive_path) as archive:
    for entry in archive.infolist():
        target = (destination / entry.filename).resolve()
        if target != destination and destination not in target.parents:
            raise RuntimeError("Unsafe path in Fluidd archive: " + entry.filename)
    archive.extractall(str(destination))
PY
        return $?
    fi
    log_error "Neither unzip nor python3 is available to extract Fluidd."
    return 1
}

fluidd_version() {
    version_dir=$1
    if [ -f "$version_dir/release_info.json" ] && which python3 > /dev/null 2>&1; then
        python3 - "$version_dir/release_info.json" <<'PY'
import json
import sys
try:
    with open(sys.argv[1], encoding="utf-8") as source:
        info = json.load(source)
    version = info.get("version") if isinstance(info, dict) else None
    if version:
        print(version)
except (OSError, ValueError):
    pass
PY
    elif [ -f "$version_dir/release_info.json" ]; then
        sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$version_dir/release_info.json"
    elif [ -f "$version_dir/version" ]; then
        cat "$version_dir/version"
    fi
}

# ── Nginx: check and restore Fluidd block ────────────────────────────────────

check_fluidd_nginx_block() {
    grep -q "listen 4408" "$NGINX_CONF" 2>/dev/null
}

restore_fluidd_nginx_block() {
    if check_fluidd_nginx_block; then
        log_info "Fluidd nginx block (port 4408) already present."
        if is_k3; then
            configure_fluidd_for_k3 || return 1
            restart_nginx
        fi
        return 0
    fi

    log_info "Adding Fluidd nginx block on port 4408..."
    backup_nginx_conf

    python3 - << PYEOF
with open('$NGINX_CONF') as f:
    content = f.read()

fluidd_block = """
$STOCK_FLUIDD_BLOCK
"""

# Insert before the closing brace of the http block
content = content.rstrip()
if content.endswith('}'):
    content = content[:-1] + fluidd_block + '\n}'

with open('$NGINX_CONF', 'w') as f:
    f.write(content)
print("Fluidd nginx block restored on port 4408.")
PYEOF

    if is_k3; then
        configure_fluidd_for_k3 || return 1
        nginx -t || return 1
    fi
    restart_nginx
}

configure_fluidd_for_k3() {
    configure_moonraker_k3_compat || return 1
    python3 "$K3_FLUIDD_COMPAT" install \
        --source /usr/share/fluidd \
        --destination "$SCRIPT_DIR/fluidd" \
        --nginx "$NGINX_CONF" || return 1
    nginx -t
}

resolve_fluidd_moonraker_config() {
    [ -f "$MOONRAKER_PATH_HELPER" ] || return 1
    active=$(python3 "$MOONRAKER_PATH_HELPER") || return 1
    case "$active" in
        "$MOONRAKER_STOCK_CONF")
            config=$(python3 "$MOONRAKER_PATH_HELPER" wrapper) || return 1
            if [ ! -e "$config" ]; then
                python3 "$MOONRAKER_WRAPPER_HELPER" init-wrapper "$config" "$MOONRAKER_STOCK_CONF" || return 1
            fi
            ;;
        /mnt/SDCARD/*|/mnt/UDISK/*)
            config=$active
            ;;
        *)
            return 1
            ;;
    esac
    [ -f "$config" ] || return 1
    [ -w "$config" ] && [ -w "$(dirname "$config")" ] || return 1
    MOONRAKER_ACTIVE_CONF=$config
}

moonraker_k3_compat_loaded() {
    python3 - <<'PY'
import json
import urllib.request
with urllib.request.urlopen("http://127.0.0.1:7125/server/info", timeout=3) as response:
    result = json.loads(response.read().decode("utf-8")).get("result", {})
if "k3helper_compat" not in result.get("components", []):
    raise SystemExit(1)
PY
}

configure_moonraker_k3_compat() {
    [ -f "$MOONRAKER_STARTUP_HELPER" ] && [ -f "$MOONRAKER_COMPAT_CONFIG" ] && \
        [ -f "$MOONRAKER_COMPAT_COMPONENT" ] || {
        log_warn "K3 Moonraker compatibility files are missing."
        return 1
    }
    resolve_fluidd_moonraker_config || {
        log_warn "Could not resolve a writable Moonraker config for K3 compatibility."
        return 1
    }
    python3 "$MOONRAKER_STARTUP_HELPER" patch-pythonpath >/dev/null 2>&1 || {
        log_warn "Could not enable K3 Moonraker file-access compatibility."
        return 1
    }
    if moonraker_k3_compat_loaded 2>/dev/null; then
        return 0
    fi
    compat_backup=$MOONRAKER_ACTIVE_CONF.k3helper-compat.bak
    if [ ! -e "$compat_backup" ]; then
        cp -p "$MOONRAKER_ACTIVE_CONF" "$compat_backup" || return 1
    fi
    python3 "$MOONRAKER_COMPAT_CONFIG" install "$MOONRAKER_ACTIVE_CONF" || return 1
    if ! restart_moonraker; then
        cp -p "$compat_backup" "$MOONRAKER_ACTIVE_CONF"
        restart_moonraker >/dev/null 2>&1
        return 1
    fi
    attempt=0
    while [ "$attempt" -lt 30 ]; do
        moonraker_k3_compat_loaded 2>/dev/null && return 0
        attempt=$((attempt + 1))
        sleep 1
    done
    log_warn "Moonraker did not load the K3 Fluidd compatibility component."
    cp -p "$compat_backup" "$MOONRAKER_ACTIVE_CONF"
    restart_moonraker >/dev/null 2>&1
    return 1
}

# ── Install / repair Fluidd ───────────────────────────────────────────────────

install_fluidd() {
    echo ""

    # Detect whether this is a fresh install or a repair
    if [ -d "$FLUIDD_DIR" ] && [ -f "$FLUIDD_DIR/index.html" ]; then
        echo -e "${YELLOW}Fluidd is already installed at $FLUIDD_DIR.${NC}"
        echo ""
        echo "  1) Update to the latest version"
        echo "  2) Repair (re-download and reinstall current latest)"
        echo "  0) Cancel"
        echo ""
        printf "  Enter choice: "
        read subchoice
        case "$subchoice" in
            1|2) : ;;  # continue with install
            *)  log_info "Cancelled."; return 0 ;;
        esac
    else
        log_info "Installing Fluidd..."
    fi

    echo ""
    check_download_tool || return 1

    # Get current installed version if present
    CURRENT_VER=$(fluidd_version "$FLUIDD_DIR")
    if [ -n "$CURRENT_VER" ]; then
        log_info "Current version: $CURRENT_VER"
    fi

    log_info "Downloading latest Fluidd..."
    rm -f /tmp/fluidd.zip
    if ! download_file "$FLUIDD_URL" /tmp/fluidd.zip; then
        log_error "Download failed. Check your internet connection."
        rm -f /tmp/fluidd.zip
        return 1
    fi

    if [ ! -f /tmp/fluidd.zip ] || [ ! -s /tmp/fluidd.zip ]; then
        log_error "Download failed. Check your internet connection."
        rm -f /tmp/fluidd.zip
        return 1
    fi

    if which python3 > /dev/null 2>&1; then
        DOWNLOADED_VER=$(python3 - /tmp/fluidd.zip <<'PY'
import json
import sys
import zipfile

try:
    with zipfile.ZipFile(sys.argv[1]) as archive:
        broken = archive.testzip()
        if broken:
            raise RuntimeError("CRC check failed for " + broken)
        info = json.loads(archive.read("release_info.json"))
        version = info.get("version") if isinstance(info, dict) else None
        if not version:
            raise RuntimeError("release_info.json has no version")
        print(version)
except Exception as error:
    print("Fluidd archive validation failed: %s" % error, file=sys.stderr)
    raise SystemExit(1)
PY
        )
        ZIP_STATUS=$?
        if [ "$ZIP_STATUS" -ne 0 ]; then
            log_error "Downloaded Fluidd archive could not be validated; kept at /tmp/fluidd.zip."
            ls -l /tmp/fluidd.zip 2>/dev/null
            return 1
        fi
    else
        if ! unzip -l /tmp/fluidd.zip > /dev/null 2>&1; then
            log_error "Downloaded Fluidd archive is invalid; kept at /tmp/fluidd.zip."
            ls -l /tmp/fluidd.zip 2>/dev/null
            return 1
        fi
        DOWNLOADED_VER=$(unzip -p /tmp/fluidd.zip release_info.json 2>/dev/null | sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
    fi
    if [ -z "$DOWNLOADED_VER" ]; then
        log_error "Downloaded Fluidd archive has no version; kept at /tmp/fluidd.zip."
        ls -l /tmp/fluidd.zip 2>/dev/null
        return 1
    fi
    log_info "Downloaded release: $DOWNLOADED_VER"

    log_info "Installing Fluidd to $FLUIDD_DIR..."
    INSTALL_SOURCE="$FLUIDD_DIR"
    K3_STAGING_DIR=""
    if [ "$FLUIDD_DIR" = "$SCRIPT_DIR/fluidd" ]; then
        # Extract a clean release first. Old hashed assets must not remain after an update.
        K3_STAGING_DIR="$SCRIPT_DIR/.fluidd-install.$$"
        rm -rf "$K3_STAGING_DIR"
        mkdir -p "$K3_STAGING_DIR"
        INSTALL_SOURCE="$K3_STAGING_DIR"
    else
        mkdir -p "$INSTALL_SOURCE"
    fi
    if ! extract_fluidd_archive /tmp/fluidd.zip "$INSTALL_SOURCE"; then
        log_error "Could not extract Fluidd archive."
        [ -n "$K3_STAGING_DIR" ] && rm -rf "$K3_STAGING_DIR"
        rm -f /tmp/fluidd.zip
        return 1
    fi
    rm -f /tmp/fluidd.zip

    if [ ! -f "$INSTALL_SOURCE/index.html" ]; then
        log_error "Installation failed — index.html not found after extraction."
        [ -n "$K3_STAGING_DIR" ] && rm -rf "$K3_STAGING_DIR"
        return 1
    fi

    # Ensure nginx block is in place
    if ! restore_fluidd_nginx_block; then
        [ -n "$K3_STAGING_DIR" ] && rm -rf "$K3_STAGING_DIR"
        return 1
    fi

    if [ "$FLUIDD_DIR" = "$SCRIPT_DIR/fluidd" ]; then
        python3 "$K3_FLUIDD_COMPAT" install \
            --source "$INSTALL_SOURCE" \
            --destination "$FLUIDD_DIR" \
            --nginx "$NGINX_CONF" \
            --refresh || { rm -rf "$K3_STAGING_DIR"; return 1; }
        rm -rf "$K3_STAGING_DIR"
        nginx -t || return 1
    fi

    # Restart nginx to serve updated files
    restart_nginx

    # Show installed version
    NEW_VER=$(fluidd_version "$FLUIDD_DIR")
    if [ -n "$NEW_VER" ]; then
        log_success "Fluidd installed: version $NEW_VER"
    else
        log_success "Fluidd installed successfully."
    fi

    mark_installed "fluidd_updated"
    echo ""
    FLUIDD_IP=$(get_lan_ip)
    if [ -n "$FLUIDD_IP" ]; then
        log_info "Access Fluidd at: http://$FLUIDD_IP:4408"
    else
        log_warn "Fluidd is listening on port 4408; could not detect the printer's LAN IP."
    fi
    echo ""
}

# ── Remove Fluidd static files ────────────────────────────────────────────────

remove_fluidd() {
    echo ""
    echo -e "${YELLOW}WARNING: This removes the Fluidd web interface static files.${NC}"
    echo "Port 4408 will return a 404 until Fluidd is reinstalled."
    echo "Moonraker and Klipper continue running normally."
    echo ""
    printf "Are you sure? [y/N]: "
    read confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        log_info "Cancelled."
        return 0
    fi

    log_info "Removing Fluidd static files from $FLUIDD_DIR..."
    rm -rf "$FLUIDD_DIR"
    mkdir -p "$FLUIDD_DIR"  # keep the directory so nginx doesn't error on root

    restart_nginx
    mark_removed "fluidd_updated"
    echo ""
    log_success "Fluidd removed."
    log_info "To reinstall, run this script again and select Install."
    echo ""
}

# ── Status ────────────────────────────────────────────────────────────────────

status_fluidd() {
    echo ""
    echo "Fluidd status:"
    if [ -f "$FLUIDD_DIR/index.html" ]; then
        log_success "Static files present at $FLUIDD_DIR"
        CURRENT_VER=$(fluidd_version "$FLUIDD_DIR")
        if [ -n "$CURRENT_VER" ]; then
            echo "  Version: $CURRENT_VER"
        fi
    else
        log_warn "Static files NOT found at $FLUIDD_DIR"
    fi

    if check_fluidd_nginx_block; then
        log_success "Nginx block present (port 4408)"
    else
        log_warn "Nginx block NOT found for port 4408"
    fi

    if pgrep -f nginx > /dev/null; then
        log_success "Nginx is running"
    else
        log_warn "Nginx is NOT running"
    fi
    echo ""
}

# ── Entry point ───────────────────────────────────────────────────────────────

case "$1" in
    install) install_fluidd ;;
    remove)  remove_fluidd ;;
    restore) restore_fluidd_nginx_block; restart_nginx ;;
    status)  status_fluidd ;;
    *)       echo "Usage: $0 [install|remove|restore|status]" ;;
esac
