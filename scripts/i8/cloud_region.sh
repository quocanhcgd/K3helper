#!/bin/sh
# Stage the i8 firmware's Server.COM / Server.CN request on removable USB.

CONFIG_FILE=${I8_SERVER_CONFIG_FILE:-/mnt/exUDISK/custom_server_config}

log_info() { printf '[INFO] %s\n' "$1"; }
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

require_root() {
    [ "$(id -u)" = 0 ] || { log_error "Run this feature as root."; return 1; }
}

require_usb() {
    awk '$2 == "/mnt/exUDISK" { found=1 } END { exit !found }' /proc/mounts || {
        log_error "No removable USB storage is mounted at /mnt/exUDISK."
        return 1
    }
}

show_menu() {
    clear
    echo "i8 Cloud Region"
    echo ""
    echo "  1) Request international server (Server.COM)"
    echo "  2) Request China mainland server (Server.CN)"
    echo "  3) Remove pending request file"
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
    echo "Confirm the region switch on the printer touchscreen."
    echo "The helper does not write Keybox settings or confirm the switch."
    echo "Remove the request file with option 3 after the touchscreen confirms."
    return 0
}

remove_request() {
    if [ -e "$CONFIG_FILE" ]; then
        rm -f "$CONFIG_FILE" || { log_error "Could not remove $CONFIG_FILE."; return 1; }
        sync
        log_info "Removed the pending request file."
    else
        log_info "No pending request file is present."
    fi
}

require_root || exit 1
require_i8 || exit 1
require_usb || exit 1

show_menu
read choice
case "$choice" in
    1) stage_request "Server.COM" "international" ;;
    2) stage_request "Server.CN" "China mainland" ;;
    3) remove_request ;;
    0) exit 0 ;;
    *) log_error "Invalid choice."; exit 2 ;;
esac
