# SparkX i8 Helper Script

The standalone i8 helper targets board `CR3SUF030C10` and firmware family `F030`. It is kept separate from the existing K2/K3 helper so i8 paths and behavior cannot change K3 behavior.

## Install layout

Copy the launcher and `scripts/i8/` directory to the printer, preserving this layout:

```text
/mnt/UDISK/helper-script-i8/helper-i8.sh
/mnt/UDISK/helper-script-i8/scripts/i8/cloud_region.sh
/mnt/UDISK/helper-script-i8/scripts/i8/firmware_info.sh
/mnt/UDISK/helper-script-i8/scripts/i8/backup.sh
/mnt/UDISK/helper-script-i8/scripts/i8/camera.sh
/mnt/UDISK/helper-script-i8/scripts/i8/led.sh
```

Then run:

```sh
chmod +x /mnt/UDISK/helper-script-i8/helper-i8.sh /mnt/UDISK/helper-script-i8/scripts/i8/*.sh
sh /mnt/UDISK/helper-script-i8/helper-i8.sh
```

## Initial features

- **Cloud region request** stages `Server.COM` or `Server.CN` on removable storage and waits for touchscreen confirmation. The i8 firmware contains a `MachineServerSwitch` UI, both region tokens, and Keybox read/write calls. The request path currently follows the K3 convention `/mnt/exUDISK/custom_server_config`; this path still needs confirmation on a physical i8 before treating the workflow as fully verified. The helper never edits Keybox directly.
- **Firmware information** reads the board and current version through the firmware's `/etc/ota_bin/get_ota_board_name.sh` and `/etc/ota_bin/get_ota_current_version.sh`, and reports the configured Cloud region through Keybox when available.
- **Configuration backup** follows `/usr/bin/creality_paths.sh`. The active config directory is `$CONFIG_ROOT/creality/printer_data/config`, where `CONFIG_ROOT` is `/mnt/user_data` when `/dev/by-name/user_data` exists and `/mnt/UDISK` otherwise. Backups are stored under `/mnt/UDISK/helper-script-i8/backups`; older backups are retained.
- **Fluidd camera** registers the firmware's existing `/usr/share/fluidd/camera.html` page as an `iframe` webcam through Moonraker's `server/webcams` API. The page signals to the firmware endpoint `/call/webrtc_local` on port `8000`; the helper does not install go2rtc or create a new camera service.
- **Lights** use the firmware's `/usr/bin/light_ctrl.sh` for the auxiliary GPIO111 light, `/usr/bin/ws281x_led.sh` for the addressable strip, and the stock `LED_SWITCH` G-code macro for the CFS box light. Effect/brightness changes are sent to the running WS281x controller without the firmware script's `-S` persistent-save option. The CFS command only takes effect when the box is connected.

The current source firmware in this workspace is `2.0.1.0`. The helper has not yet been exercised on a physical i8. Region switching and camera display need on-device confirmation tests. Check backup path selection against the running printer before restoring or modifying any configuration.
