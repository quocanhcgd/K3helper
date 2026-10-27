# K3 Camera Support

The K3 firmware includes a `webrtc_local` camera service and a Fluidd WebRTC adapter for go2rtc. This installer places go2rtc on `/mnt/UDISK`, registers the camera through Moonraker, and runs go2rtc with OpenWrt `procd`.

The stock Moonraker webcam API omits Fluidd's `enabled` and `uid` fields, and its delete endpoint expects `name`. The installer keeps a writable Fluidd copy at `/mnt/UDISK/helper-script/fluidd`, applies those compatibility defaults to the JavaScript bundle, and points the port `4408` Nginx document root at that copy. It also routes Fluidd's G-code download links through the `4408` proxy, and adds thumbnail previews to the Jobs and RE-PRINT lists when a G-code file embeds a preview. It reads `sys_version` from `/mnt/UDISK/creality/userdata/config/system_version.json`, publishes only that version next to Fluidd, and displays it in a small badge. A CFS panel is mounted in the Fluidd dashboard and reads Klipper's `box` object through Moonraker. It is read-only and does not select filament for a print. Firmware files remain untouched. Fluidd update/repair and camera repair apply the compatibility layer without replacing an existing newer Fluidd copy. The version is available to local clients at `http://<printer-ip>:4408/creality-firmware-version.json`. For a dynamic API that returns the current hardware and firmware fields, see [K3 Firmware Version API](k3-firmware-api.md).

## Requirements

- Creality K3 board `CR0CUF039C13` with rooted SSH access.
- The K3 firmware overlay enabled and mounted on `/etc`.
- Network access to GitHub for downloading go2rtc.

The firmware overlay is currently off by default. This firmware creates a 512 MiB ext4 overlay image on the SD card. Enable it and reboot:

```sh
touch /mnt/SDCARD/overlay/enable.txt
reboot
```

Confirm `/etc` is mounted as `overlay` after reboot:

```sh
grep ' /etc overlay ' /proc/mounts
```

## Install

Copy the helper script to `/mnt/UDISK/helper-script`, then start it:

```sh
sh /mnt/UDISK/helper-script/helper.sh
```

Select **11) K3 Camera (install/repair)**. The same menu option installs the feature the first time and repairs it on later runs.

To update the Helper Script code on the printer, select **15) Update Helper Script from GitHub**. Then use **8) Fluidd update/repair** to refresh Fluidd and reapply all K3 compatibility patches.

The installer stores the go2rtc binary, config, printer IP, and watchdog on UDISK. Its `procd` service is installed into the writable overlay and enabled at boot. The watchdog restores the Moonraker camera entry if an update removes it, while leaving an existing entry's enabled state alone. The camera appears in Fluidd as **K3 Camera**. go2rtc listens on port `1984`.

After a firmware update, update the Helper Script with option **15**, run **8) Fluidd update/repair** to install the current Fluidd release and compatibility layer, then run **11) K3 Camera (install/repair)** to refresh the go2rtc service and stream config. Camera repair preserves the existing writable Fluidd copy. It only creates the Moonraker camera entry if it is missing.

The CFS panel appears in the lower-right corner of Fluidd. It shows four slot cards for each reported CFS unit, color, material name/type, loaded state when reported by the firmware, temperature, humidity, and a detail view when a slot is selected. It refreshes every 10 seconds from `/printer/objects/query?box` and has a manual **Refresh** button; it does not use Creality Cloud. K3 firmware reports some material names through `box.same_material`, so the panel combines that data with the per-slot arrays and handles the firmware's `vender` spelling. If firmware omits a field, that value is shown as unavailable rather than inferred. The panel is read-only; it does not call the unverified `:9999` WebSocket or send feed/retract commands, and print/reprint slot selection remains controlled by Creality's print workflow.

If the update removed or disabled the `/etc` overlay, enable it again using the steps above, reboot, then run the same Helper Script menu option.

## Remove

With the overlay mounted, select **K3 Camera** in the remove menu, or run:

```sh
sh /mnt/UDISK/helper-script/scripts/camera.sh remove
```

This removes the Moonraker camera entry, service, and go2rtc files. The UDISK-hosted Fluidd copy and Nginx document-root change remain, so Fluidd updates and the API compatibility fix are preserved. It leaves the firmware overlay itself in place.
