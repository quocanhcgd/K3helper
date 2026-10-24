# K3 Camera Support

The K3 firmware includes a `webrtc_local` camera service and a Fluidd WebRTC adapter for go2rtc. This installer places go2rtc on `/mnt/UDISK`, registers the camera through Moonraker, and runs go2rtc with OpenWrt `procd`.

The stock Moonraker webcam API omits Fluidd's `enabled` and `uid` fields, and its delete endpoint expects `name`. The installer copies Fluidd to `/mnt/UDISK/helper-script/fluidd`, applies those compatibility defaults to the JavaScript bundle, and changes the port `4408` Nginx document root to that writable copy. It also reads `sys_version` from `/mnt/UDISK/creality/userdata/config/system_version.json`, publishes only that version next to Fluidd, and displays it in a small badge. The original firmware files stay untouched. Fluidd updates and camera repairs recreate this integration. The version is available to local clients at `http://<printer-ip>:4408/creality-firmware-version.json`. For a dynamic API that returns the current hardware and firmware fields, see [K3 Firmware Version API](k3-firmware-api.md).

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

The installer stores the go2rtc binary, config, printer IP, and watchdog on UDISK. Its `procd` service is installed into the writable overlay and enabled at boot. The watchdog restores the Moonraker camera entry if an update removes it, while leaving an existing entry's enabled state alone. The camera appears in Fluidd as **K3 Camera**. go2rtc listens on port `1984`.

After a firmware update, open Helper Script and select **11) K3 Camera (install/repair)** again. It refreshes the writable Fluidd copy from the version shipped in the current firmware, reapplies the webcam patch and Nginx root, and refreshes the go2rtc service and stream config. It only creates the Moonraker camera entry if it is missing.

If the update removed or disabled the `/etc` overlay, enable it again using the steps above, reboot, then run the same Helper Script menu option.

## Remove

With the overlay mounted, select **K3 Camera** in the remove menu, or run:

```sh
sh /mnt/UDISK/helper-script/scripts/camera.sh remove
```

This removes the Moonraker camera entry, service, and go2rtc files. The UDISK-hosted Fluidd copy and Nginx document-root change remain, so Fluidd updates and the API compatibility fix are preserved. It leaves the firmware overlay itself in place.
