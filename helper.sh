#!/bin/sh
# Creality Helper Script
# https://github.com/sw3defy/Creality-Helper-Script-Wiki-K2-Plus
# K3 board support: CR0CUF039C13
# OS: Tina 5.0 / OpenWrt 21.02

SCRIPT_DIR=/mnt/UDISK/helper-script
SCRIPTS_DIR=$SCRIPT_DIR/scripts
FILES_DIR=$SCRIPT_DIR/files
PRINTER_DATA=/mnt/UDISK/printer_data
CONFIG_DIR=$PRINTER_DATA/config
LOGS_DIR=$PRINTER_DATA/logs
. "$SCRIPTS_DIR/system.sh"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m'

print_header() {
    clear
    echo ""
    echo -e "${CYAN}======================================================${NC}"
    if is_k3; then
        echo -e "${WHITE}   Creality K3 Helper Script${NC}"
    else
        echo -e "${WHITE}   Creality K2 Plus Helper Script${NC}"
    fi
    echo -e "${CYAN}======================================================${NC}"
    if is_k3; then
        echo -e "${YELLOW}   K3 support is limited to the features listed below.${NC}"
    else
        echo -e "${YELLOW}   https://sw3defy.github.io/Creality-Helper-Script-Wiki-K2-Plus${NC}"
    fi
    echo -e "${CYAN}======================================================${NC}"
    echo ""
}

check_root() {
    if [ "$(id -u)" != "0" ]; then
        echo -e "${RED}ERROR: This script must be run as root.${NC}"
        exit 1
    fi
}

check_printer() {
    if [ ! -f "$CONFIG_DIR/printer.cfg" ]; then
        echo -e "${RED}ERROR: printer.cfg not found at $CONFIG_DIR/printer.cfg${NC}"
        echo "Make sure the printer has booted fully before running this script."
        exit 1
    fi
}

main_menu() {
    print_header
    if is_k3; then
        echo -e "  ${WHITE}[K3-compatible features]${NC}"
        echo "    1) Check K3 Moonraker config"
        echo "    8) Fluidd update/repair (port 4408)"
        echo "   11) K3 Camera (install/repair)"
        echo "   12) K3 Firmware API (port 8765)"
        echo "   13) Trace Cloud connections (5 min)"
        echo "   14) K3 Cloud region switch (USB + LCD confirmation)"
        echo "   15) Update Helper Script from GitHub"
        echo ""
        echo -e "  ${WHITE}[Fluidd integrations]${NC}"
        echo "   25) Connect Fluidd to Spoolman"
        echo "   26) Diagnose Spoolman integration"
        echo "   27) Chamber LED WebSocket macros for Fluidd"
        echo ""
        echo -e "  ${WHITE}[Backup & Restore] Menu${NC}"
        echo "   17) Backup Klipper configuration"
        echo "   18) Restore Klipper configuration"
        echo ""
        echo -e "  ${WHITE}[Tools] Menu${NC}"
        echo "   19) Restart Klipper"
        echo "   20) Restart Moonraker"
        echo "   21) Restart Nginx"
        echo "   22) View Klipper log"
        echo "   23) View Moonraker log"
        echo "   24) Show installed features"
        echo ""
        echo "   16) Remove a feature"
        echo "    0) Exit"
        echo ""
        printf "  Enter choice: "
        read choice
        handle_choice "$choice"
        return
    fi

    echo -e "  ${WHITE}[Install] Menu${NC}"
    echo -e "  ${YELLOW}--- Step 1: Foundation (install first) ---${NC}"
    echo -e "    1) Moonraker Extensions & Update Manager  ${GREEN}[recommended first]${NC}"
    echo ""
    echo -e "  ${YELLOW}--- Step 2: Print macros ---${NC}"
    echo -e "    2) Fans Control Macros                    ${CYAN}[needed by START_PRINT]${NC}"
    echo "    3) Useful Macros (START_PRINT / END_PRINT)"
    echo "    4) Save Z-Offset Macros"
    echo "    5) M600 Filament Change Support"
    echo ""
    echo -e "  ${YELLOW}--- Step 3: Leveling & calibration ---${NC}"
    echo "    6) Klipper Adaptive Meshing & Purging (KAMP)"
    echo "    7) Improved Shapers Calibrations"
    echo ""
    echo -e "  ${YELLOW}--- Step 4: Web interface & camera ---${NC}"
    echo "    8) Fluidd (install/update/repair — port 4408)"
    echo -e "    9) Mainsail (install/update/repair — port 4409)"
    echo "   10) Moonraker Timelapse"
    echo ""
    echo -e "  ${YELLOW}--- Step 5: Remote access & notifications ---${NC}"
    echo "   12) Entware"
    echo ""
    echo -e "  ${WHITE}[Remove] Menu${NC}"
    echo "   16) Remove a feature"
    echo ""
    echo -e "  ${WHITE}[Backup & Restore] Menu${NC}"
    echo "   17) Backup Klipper configuration"
    echo "   18) Restore Klipper configuration"
    echo ""
    echo -e "  ${WHITE}[Tools] Menu${NC}"
    echo "   19) Restart Klipper"
    echo "   20) Restart Moonraker"
    echo "   21) Restart Nginx"
    echo "   22) View Klipper log"
    echo "   23) View Moonraker log"
    echo "   24) Show installed features"
    echo ""
    echo "    0) Exit"
    echo ""
    printf "  Enter choice: "
    read choice
    handle_choice "$choice"
}

handle_choice() {
    if is_k3; then
        case "$1" in
            2|3|4|5|6|7|9|10)
                echo -e "${RED}This feature is not enabled for K3 because its dependencies are unverified.${NC}"
                sleep 2
                main_menu
                return
                ;;
        esac
    fi
    case "$1" in
        # Step 1 — Foundation
        1)  sh "$SCRIPTS_DIR/moonraker.sh" install ;;
        # Step 2 — Print macros (fans before useful_macros — chamber refs)
        2)  sh "$SCRIPTS_DIR/fans.sh" install ;;
        3)  sh "$SCRIPTS_DIR/useful_macros.sh" install ;;
        4)  sh "$SCRIPTS_DIR/z_offset.sh" install ;;
        5)  sh "$SCRIPTS_DIR/m600.sh" install ;;
        # Step 3 — Leveling & calibration
        6)  sh "$SCRIPTS_DIR/kamp.sh" install ;;
        7)  sh "$SCRIPTS_DIR/shapers.sh" install ;;
        # Step 4 — Web interface & camera
        8)  sh "$SCRIPTS_DIR/fluidd.sh" install ;;
        9)  sh "$SCRIPTS_DIR/mainsail.sh" install ;;
        10) sh "$SCRIPTS_DIR/timelapse.sh" install ;;
        11) sh "$SCRIPTS_DIR/camera.sh" repair ;;
        12)
            if is_k3; then
                sh "$SCRIPTS_DIR/firmware_api.sh" install
            else
                sh "$SCRIPTS_DIR/entware.sh" install
            fi
            ;;
        13)
            if is_k3; then
                sh "$SCRIPTS_DIR/cloud_trace.sh"
            else
                echo -e "${RED}Invalid choice.${NC}"
            fi
            ;;
        14)
            if is_k3; then
                sh "$SCRIPTS_DIR/cloud_region.sh"
            else
                echo -e "${RED}Invalid choice.${NC}"
            fi
            ;;
        15)
            if is_k3; then
                sh "$SCRIPTS_DIR/update_helper.sh"
            else
                echo -e "${RED}Invalid choice.${NC}"
            fi
            ;;
        25)
            if is_k3; then
                sh "$SCRIPTS_DIR/spoolman.sh" install
            else
                echo -e "${RED}Invalid choice.${NC}"
            fi
            ;;
        26)
            if is_k3; then
                sh "$SCRIPTS_DIR/spoolman.sh" status
            else
                echo -e "${RED}Invalid choice.${NC}"
            fi
            ;;
        27)
            if is_k3; then
                sh "$SCRIPTS_DIR/chamber_light.sh" install
            else
                echo -e "${RED}Invalid choice.${NC}"
            fi
            ;;
        # Step 5 — Remote access
        # Other menus
        16) remove_menu ;;
        17) sh "$SCRIPTS_DIR/backup.sh" backup ;;
        18) sh "$SCRIPTS_DIR/backup.sh" restore ;;
        19) sh "$SCRIPTS_DIR/system.sh" restart_klipper ;;
        20) sh "$SCRIPTS_DIR/system.sh" restart_moonraker ;;
        21) sh "$SCRIPTS_DIR/system.sh" restart_nginx ;;
        22) tail -50 "$LOGS_DIR/klippy.log" | less ;;
        23) tail -50 "$LOGS_DIR/moonraker.log" | less ;;
        24) sh "$SCRIPTS_DIR/system.sh" show_installed ;;
        0)  echo ""; echo "Goodbye!"; echo ""; exit 0 ;;
        *)  echo -e "${RED}Invalid choice.${NC}"; sleep 1 ;;
    esac
    echo ""
    printf "Press Enter to return to menu..."
    read dummy
    main_menu
}

remove_menu() {
    print_header
    echo -e "  ${WHITE}[Remove] Menu${NC}"
    echo ""
    if is_k3; then
        echo "    8) Fluidd"
        echo "   11) K3 Camera"
        echo "   12) K3 Firmware API"
        echo "   13) Spoolman connection"
        echo "   14) Chamber light macro"
        echo "    0) Back"
        echo ""
        printf "  Enter choice: "
        read choice
        case "$choice" in
            8) sh "$SCRIPTS_DIR/fluidd.sh" remove ;;
            11) sh "$SCRIPTS_DIR/camera.sh" remove ;;
            12) sh "$SCRIPTS_DIR/firmware_api.sh" remove ;;
            13) sh "$SCRIPTS_DIR/spoolman.sh" remove ;;
            14) sh "$SCRIPTS_DIR/chamber_light.sh" remove ;;
            0) return ;;
            *) echo -e "${RED}Invalid choice.${NC}" ;;
        esac
        return
    fi

    echo "    1) Moonraker Extensions"
    echo "    2) Fans Control Macros"
    echo "    3) Useful Macros"
    echo "    4) Save Z-Offset Macros"
    echo "    5) M600 Support"
    echo "    6) KAMP"
    echo "    7) Improved Shapers Calibrations"
    echo "    8) Fluidd"
    echo -e "    9) Mainsail (install/update/repair — port 4409)"
    echo "   10) Moonraker Timelapse"
    echo "   12) Entware"
    echo "    0) Back"
    echo ""
    printf "  Enter choice: "
    read choice
    case "$choice" in
        1)  sh "$SCRIPTS_DIR/moonraker.sh" remove ;;
        2)  sh "$SCRIPTS_DIR/fans.sh" remove ;;
        3)  sh "$SCRIPTS_DIR/useful_macros.sh" remove ;;
        4)  sh "$SCRIPTS_DIR/z_offset.sh" remove ;;
        5)  sh "$SCRIPTS_DIR/m600.sh" remove ;;
        6)  sh "$SCRIPTS_DIR/kamp.sh" remove ;;
        7)  sh "$SCRIPTS_DIR/shapers.sh" remove ;;
        8)  sh "$SCRIPTS_DIR/fluidd.sh" remove ;;
        9)  sh "$SCRIPTS_DIR/mainsail.sh" remove ;;
        10) sh "$SCRIPTS_DIR/timelapse.sh" remove ;;
        11) sh "$SCRIPTS_DIR/camera.sh" remove ;;
        12) sh "$SCRIPTS_DIR/entware.sh" remove ;;
        0)  return ;;
        *)  echo -e "${RED}Invalid choice.${NC}" ;;
    esac
}

# Entry point
check_root
check_printer
main_menu
