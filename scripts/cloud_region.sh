#!/bin/sh
# Prepare the K3 firmware's removable-USB cloud-region switch request.

CONFIG_FILE=/mnt/exUDISK/custom_server_config
APP_LOG=/mnt/SDCARD/cxsw/creality/userdata/log/22_AppUi.log
CLOUD_LOG=/mnt/SDCARD/cxsw/creality/userdata/log/app-server.log

log_info() { printf '[INFO] %s\n' "$1"; }
log_error() { printf '[ERROR] %s\n' "$1" >&2; }

if [ "$(id -u)" != 0 ]; then
    log_error "Run this feature as root."
    exit 1
fi

if ! grep -q '^OPENWRT_BOARD=.*CR0CUF039C13' /etc/os-release 2>/dev/null; then
    log_error "This feature targets K3 board CR0CUF039C13."
    exit 1
fi

if ! awk '$2 == "/mnt/exUDISK" { found=1 } END { exit !found }' /proc/mounts; then
    log_error "No removable USB storage is mounted at /mnt/exUDISK."
    exit 1
fi

show_menu() {
    clear
    echo "K3 Cloud Region"
    echo ""
    echo "  1) Request international server (Server.COM)"
    echo "  2) Request China mainland server (Server.CN)"
    echo "  3) Remove the pending request file"
    echo "  0) Back"
    echo ""
    printf "Enter choice: "
}

stage_request() {
    server_value=$1
    server_name=$2

    if [ -e "$CONFIG_FILE" ]; then
        log_error "A request file already exists at $CONFIG_FILE."
        echo "Remove it with option 3 before staging another request."
        return 1
    fi

    if ! printf '%s\n' "$server_value" > "$CONFIG_FILE"; then
        log_error "Could not write $CONFIG_FILE."
        return 1
    fi
    sync

    if [ "$(cat "$CONFIG_FILE" 2>/dev/null)" != "$server_value" ]; then
        log_error "The request file did not verify; remove it and retry."
        return 1
    fi

    log_info "Staged $server_name request as $server_value."
    echo "Check the printer touchscreen and confirm the region switch there."
    echo "This file only requests the switch; the Helper Script does not confirm it."
    echo "After the switch succeeds, use option 3 to remove the request file."
    echo ""
    echo "UI log: $APP_LOG"
    echo "Cloud log: $CLOUD_LOG"
    return 0
}

remove_request() {
    if [ -e "$CONFIG_FILE" ]; then
        rm -f "$CONFIG_FILE" || { log_error "Could not remove $CONFIG_FILE."; return 1; }
        sync
        log_info "Removed the pending cloud-region request file."
    else
        log_info "No cloud-region request file is present."
    fi
}

show_menu
read choice
case "$choice" in
    1) stage_request "Server.COM" "international" ;;
    2) stage_request "Server.CN" "China mainland" ;;
    3) remove_request ;;
    0) exit 0 ;;
    *) log_error "Invalid choice."; exit 2 ;;
esac
