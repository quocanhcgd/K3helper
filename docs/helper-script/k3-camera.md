# K3 Camera Support

The K3 firmware includes a `webrtc_local` camera service and a Fluidd WebRTC adapter for go2rtc. This installer places go2rtc on `/mnt/UDISK`, registers the camera through Moonraker, and runs go2rtc with OpenWrt `procd`.

It does not patch the stock Nginx or Fluidd files. Fluidd connects directly to go2rtc on port `1984`.

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

Copy the helper script to `/mnt/UDISK/helper-script`, then select **K3 Camera Support** from the install menu. You can also run:

```sh
sh /mnt/UDISK/helper-script/scripts/camera.sh install
```

The installer stores the go2rtc binary, config, and watchdog on UDISK. Its `procd` service is installed into the writable overlay and enabled at boot. The camera appears in Fluidd as **K3 Camera**. go2rtc listens on port `1984`.

## Remove

With the overlay mounted, select **K3 Camera Support** in the remove menu, or run:

```sh
sh /mnt/UDISK/helper-script/scripts/camera.sh remove
```

This removes the Moonraker camera entry, service, and K3 camera files. It leaves the firmware overlay itself in place.
