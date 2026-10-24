#!/bin/sh
# mainsail.sh - Install, update, repair, or remove Mainsail on port 4409

SCRIPT_DIR=/mnt/UDISK/helper-script
. "$SCRIPT_DIR/scripts/system.sh"

MAINSAIL_DIR=/usr/share/mainsail
if is_k3; then
    MAINSAIL_DIR=$SCRIPT_DIR/mainsail
fi
MAINSAIL_URL=https://github.com/mainsail-crew/mainsail/releases/latest/download/mainsail.zip
NGINX_CONF=/etc/nginx/nginx.conf

# ── Download helper ───────────────────────────────────────────────────────────

check_download_tool() {
    if which wget > /dev/null 2>&1; then
        DOWNLOAD_CMD="wget"
    elif which curl > /dev/null 2>&1; then
        DOWNLOAD_CMD="curl"
    else
        log_error "Neither wget nor curl found. Install Entware first."
        return 1
    fi
}

download_file() {
    local url="$1"
    local dest="$2"
    if [ "$DOWNLOAD_CMD" = "wget" ]; then
        wget -q --show-progress -O "$dest" "$url"
    else
        curl -L --progress-bar -o "$dest" "$url"
    fi
}

# ── Nginx block management ────────────────────────────────────────────────────

check_mainsail_nginx_block() {
    grep -q "listen 4409" "$NGINX_CONF" 2>/dev/null
}

restore_mainsail_nginx_block() {
    if check_mainsail_nginx_block; then
        log_info "Mainsail nginx block (port 4409) already present."
        configure_mainsail_root || return 1
        return 0
    fi

    log_info "Adding Mainsail nginx block on port 4409..."
    backup_nginx_conf

    python3 - << PYEOF
with open('$NGINX_CONF') as f:
    content = f.read()

mainsail_block = """
    server {
        listen 4409 default_server;

        access_log /var/log/nginx/mainsail-access.log;
        error_log /var/log/nginx/mainsail-error.log;

        gzip on;
        gzip_vary on;
        gzip_proxied any;
        gzip_comp_level 4;
        gzip_buffers 16 8k;
        gzip_http_version 1.1;
        gzip_types text/plain text/css text/xml text/javascript application/x-javascript application/json application/xml;

        root /usr/share/mainsail;
        index index.html;
        server_name _;
        client_max_body_size 0;
        proxy_request_buffering off;

        location / {
            try_files \$uri \$uri/ /index.html;
        }
        location = /index.html {
            add_header Cache-Control "no-store, no-cache, must-revalidate";
        }
        location /websocket {
            proxy_pass http://apiserver/websocket;
            proxy_http_version 1.1;
            proxy_set_header Upgrade \$http_upgrade;
            proxy_set_header Connection \$connection_upgrade;
            proxy_set_header Host \$http_host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_read_timeout 86400;
        }
        location ~ ^/(printer|api|access|machine|server)/ {
            proxy_pass http://apiserver\$request_uri;
            proxy_set_header Host \$http_host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Scheme \$scheme;
        }
        location /webcam/  { proxy_pass http://mjpgstreamer1/; }
        location /webcam2/ { proxy_pass http://mjpgstreamer2/; }
        location /webcam3/ { proxy_pass http://mjpgstreamer3/; }
        location /webcam4/ { proxy_pass http://mjpgstreamer4/; }
    }
"""

content = content.rstrip()
if content.endswith('}'):
    content = content[:-1] + mainsail_block + '\n}'

with open('$NGINX_CONF', 'w') as f:
    f.write(content)
print("Mainsail nginx block added on port 4409.")
PYEOF

    configure_mainsail_root || return 1
    restart_nginx
    log_success "Mainsail nginx block restored on port 4409."
}

configure_mainsail_root() {
    is_k3 || return 0
    backup_nginx_conf
    python3 - "$NGINX_CONF" "$MAINSAIL_DIR" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
root = sys.argv[2]
content = path.read_text()
changed = False
for match in re.finditer(r"\bserver\s*\{", content):
    brace = content.find("{", match.start())
    depth = 0
    quote = None
    escaped = False
    for pos in range(brace, len(content)):
        char = content[pos]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = pos + 1
                break
    else:
        continue
    block = content[match.start():end]
    if not re.search(r"\blisten\s+4409\b", block):
        continue
    block, count = re.subn(r"(?m)^(\s*root\s+)[^;]+;", lambda m: m.group(1) + root + ";", block, count=1)
    if count != 1:
        raise SystemExit("Could not find the Mainsail root directive in port 4409 server.")
    content = content[:match.start()] + block + content[end:]
    changed = True
    break
if not changed:
    raise SystemExit("Could not find the Nginx server listening on port 4409.")
path.write_text(content)
PY
}

remove_mainsail_nginx_block() {
    if ! check_mainsail_nginx_block; then
        log_info "Mainsail nginx block not found — nothing to remove."
        return 0
    fi

    log_info "Removing Mainsail nginx block from nginx.conf..."
    python3 - << PYEOF
import re
with open('$NGINX_CONF') as f:
    content = f.read()
# Remove the server block listening on 4409
content = re.sub(r'\n\s*server\s*\{[^}]*listen\s+4409[^}]*(?:\{[^}]*\}[^}]*)?\}', '', content)
with open('$NGINX_CONF', 'w') as f:
    f.write(content)
print("Mainsail nginx block removed.")
PYEOF
    log_success "Mainsail nginx block removed."
}

# ── Status ────────────────────────────────────────────────────────────────────

status_mainsail() {
    echo ""
    echo "Mainsail status:"
    if [ -f "$MAINSAIL_DIR/index.html" ]; then
        log_success "Static files present at $MAINSAIL_DIR"
        if [ -f "$MAINSAIL_DIR/version" ]; then
            echo "  Version: $(cat $MAINSAIL_DIR/version)"
        fi
    else
        log_warn "Static files NOT found at $MAINSAIL_DIR"
    fi

    if check_mainsail_nginx_block; then
        log_success "Nginx block present (port 4409)"
    else
        log_warn "Nginx block NOT found for port 4409"
    fi

    if pgrep -f nginx > /dev/null; then
        log_success "Nginx is running"
    else
        log_warn "Nginx is NOT running"
    fi
    echo ""
}

# ── Install / update / repair ─────────────────────────────────────────────────

install_mainsail() {
    require_k2_only || return 1
    echo ""

    # Detect whether this is a fresh install or update/repair
    if [ -d "$MAINSAIL_DIR" ] && [ -f "$MAINSAIL_DIR/index.html" ]; then
        echo -e "${YELLOW}Mainsail is already installed at $MAINSAIL_DIR.${NC}"
        if [ -f "$MAINSAIL_DIR/version" ]; then
            echo "  Current version: $(cat $MAINSAIL_DIR/version)"
        fi
        echo ""
        echo "  1) Update to the latest version"
        echo "  2) Repair (re-download and reinstall)"
        echo "  3) Restore nginx block only (if port 4409 is broken)"
        echo "  0) Cancel"
        echo ""
        printf "  Enter choice: "
        read subchoice
        case "$subchoice" in
            1|2) : ;;  # continue with full install
            3)  restore_mainsail_nginx_block; return 0 ;;
            *)  log_info "Cancelled."; return 0 ;;
        esac
    else
        log_info "Installing Mainsail..."
    fi

    echo ""
    log_info "Downloading latest Mainsail..."
    python3 << PYEOF || { log_error "Download failed. Check your internet connection."; return 1; }
import urllib.request, zipfile, os
os.makedirs('$MAINSAIL_DIR', exist_ok=True)
print('Downloading Mainsail...')
urllib.request.urlretrieve('$MAINSAIL_URL', '/tmp/mainsail.zip')
print('Extracting...')
with zipfile.ZipFile('/tmp/mainsail.zip', 'r') as z:
    z.extractall('$MAINSAIL_DIR')
os.remove('/tmp/mainsail.zip')
print('Done')
PYEOF

    if [ ! -f "$MAINSAIL_DIR/index.html" ]; then
        log_error "Installation failed — index.html not found after extraction."
        return 1
    fi

    # Ensure nginx block is in place
    restore_mainsail_nginx_block

    restart_nginx

    if [ -f "$MAINSAIL_DIR/version" ]; then
        NEW_VER=$(cat "$MAINSAIL_DIR/version")
        log_success "Mainsail installed: version $NEW_VER"
    else
        log_success "Mainsail installed successfully."
    fi

    mark_installed "mainsail"
    echo ""
    MAINSAIL_IP=$(get_lan_ip)
    if [ -n "$MAINSAIL_IP" ]; then
        log_info "Access Mainsail at: http://$MAINSAIL_IP:4409"
    else
        log_warn "Mainsail is listening on port 4409; could not detect the printer's LAN IP."
    fi
    echo ""
}

# ── Remove ────────────────────────────────────────────────────────────────────

remove_mainsail() {
    require_k2_only || return 1
    echo ""
    echo -e "${YELLOW}WARNING: This removes Mainsail static files and the port 4409 nginx block.${NC}"
    echo "Fluidd on port 4408 is not affected."
    echo ""
    printf "Are you sure? [y/N]: "
    read confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        log_info "Cancelled."
        return 0
    fi

    remove_mainsail_nginx_block
    rm -rf "$MAINSAIL_DIR"
    restart_nginx
    mark_removed "mainsail"
    echo ""
    log_success "Mainsail removed."
    log_info "Fluidd on port 4408 is unaffected."
    echo ""
}

# ── Entry point ───────────────────────────────────────────────────────────────

case "$1" in
    install) install_mainsail ;;
    remove)  remove_mainsail ;;
    restore) restore_mainsail_nginx_block; restart_nginx ;;
    status)  status_mainsail ;;
    *)       echo "Usage: $0 [install|remove|restore|status]" ;;
esac
