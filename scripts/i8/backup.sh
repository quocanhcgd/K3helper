#!/bin/sh
# Back up the active i8 Klipper configuration without deleting older backups.

SCRIPT_DIR=/mnt/UDISK/helper-script-i8
BACKUP_DIR=$SCRIPT_DIR/backups

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

[ "$(id -u)" = 0 ] || { log_error "Run this feature as root."; exit 1; }
require_i8 || exit 1
[ -r /usr/bin/creality_paths.sh ] || { log_error "Missing firmware path definitions at /usr/bin/creality_paths.sh."; exit 1; }
. /usr/bin/creality_paths.sh

CONFIG_DIR=$CONFIG_ROOT/creality/printer_data/config
[ -d "$CONFIG_DIR" ] || { log_error "Active printer configuration directory not found: $CONFIG_DIR"; exit 1; }
[ -r "$CONFIG_DIR/printer.cfg" ] || { log_error "printer.cfg is not readable in $CONFIG_DIR"; exit 1; }

mkdir -p "$BACKUP_DIR" || { log_error "Could not create $BACKUP_DIR"; exit 1; }
timestamp=$(date +%Y%m%d_%H%M%S)
backup_file=$BACKUP_DIR/i8_config_$timestamp.tar.gz

if ! tar -czf "$backup_file" -C "$(dirname "$CONFIG_DIR")" "$(basename "$CONFIG_DIR")"; then
    rm -f "$backup_file"
    log_error "Configuration backup failed."
    exit 1
fi

if ! tar -tzf "$backup_file" >/dev/null 2>&1; then
    rm -f "$backup_file"
    log_error "Backup archive verification failed."
    exit 1
fi

sync
log_info "Backup verified: $backup_file"
