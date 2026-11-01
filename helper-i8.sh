#!/bin/sh
# Standalone helper for Creality SparkX i8 firmware CR3SUF030C10.

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
I8_SCRIPTS_DIR=$SCRIPT_DIR/scripts/i8

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m'

get_i8_board() {
    if [ -x /usr/bin/get_sn_mac.sh ]; then
        /usr/bin/get_sn_mac.sh board 2>/dev/null
    elif [ -x /etc/ota_bin/get_ota_board_name.sh ]; then
        /etc/ota_bin/get_ota_board_name.sh 2>/dev/null
    fi
}

check_i8() {
    board=$(get_i8_board | tr -d '\r')
    case "$board" in
        CR3SUF030C10*) return 0 ;;
    esac
    echo -e "${RED}This helper targets SparkX i8 board CR3SUF030C10; detected '${board:-unknown}'.${NC}" >&2
    return 1
}

check_root() {
    if [ "$(id -u)" != 0 ]; then
        echo -e "${RED}Run this helper as root.${NC}" >&2
        exit 1
    fi
}

main_menu() {
    clear
    echo -e "${CYAN}======================================================${NC}"
    echo -e "${WHITE}   Creality SparkX i8 Helper Script${NC}"
    echo -e "${CYAN}======================================================${NC}"
    echo "    1) Cloud region switch (USB request + touchscreen confirmation)"
    echo "    2) Show firmware and board information"
    echo "    3) Back up printer configuration"
    echo "    4) Configure i8 camera in Fluidd"
    echo "    5) Camera and LED controls"
    echo "    0) Exit"
    echo ""
    printf "  Enter choice: "
    read choice

    case "$choice" in
        1) sh "$I8_SCRIPTS_DIR/cloud_region.sh" ;;
        2) sh "$I8_SCRIPTS_DIR/firmware_info.sh" ;;
        3) sh "$I8_SCRIPTS_DIR/backup.sh" ;;
        4) sh "$I8_SCRIPTS_DIR/camera.sh" ;;
        5) sh "$I8_SCRIPTS_DIR/led.sh" ;;
        0) exit 0 ;;
        *) echo -e "${RED}Invalid choice.${NC}" ;;
    esac
    echo ""
    printf "Press Enter to return to the menu..."
    read _
    main_menu
}

check_root
check_i8 || exit 1
main_menu
