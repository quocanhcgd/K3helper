#!/bin/sh

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

require_i8 || exit 1

model=unknown
board=unknown
firmware=unknown
[ -x /usr/bin/get_sn_mac.sh ] && model=$(/usr/bin/get_sn_mac.sh model 2>/dev/null)
[ -x /etc/ota_bin/get_ota_board_name.sh ] && board=$(/etc/ota_bin/get_ota_board_name.sh 2>/dev/null)
[ -x /etc/ota_bin/get_ota_current_version.sh ] && firmware=$(/etc/ota_bin/get_ota_current_version.sh 2>/dev/null)

printf 'Model:          %s\n' "${model:-unknown}"
printf 'Board:          %s\n' "${board:-unknown}"
printf 'Firmware:       %s\n' "${firmware:-unknown}"
printf 'Cloud region:   '
if [ -x /usr/bin/keybox ]; then
    /usr/bin/keybox -r server_local 2>/dev/null | sed 's/^/                /'
else
    printf 'not available through the installed Keybox command\n'
fi

if [ -r /usr/bin/creality_paths.sh ]; then
    . /usr/bin/creality_paths.sh
    printf 'Config root:    %s\n' "${CONFIG_ROOT:-unknown}"
    printf 'Printer config: %s/creality/printer_data/config\n' "${CONFIG_ROOT:-unknown}"
fi
