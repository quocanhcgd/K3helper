# Spoolman on K3

Fluidd 1.37.7 includes a Spoolman interface. Moonraker must also load its `[spoolman]` component and reach the Spoolman API. The K3 Helper Script configures that connection; it does not install Spoolman on the printer.

## Before connecting

Run Spoolman on another computer, NAS, or server that stays available on the same network. This K3 integration configures Moonraker's connection; it does not install the server on the printer.

Confirm that this URL opens from a browser on the LAN, replacing the address with the Spoolman host:

```text
http://192.168.0.20:7912/api/v1/info
```

It should return JSON. Use the base URL, without `/api/v1/info`, in the Helper Script.

## Connect the printer

Update the K3 Helper Script to the latest version, run `helper.sh`, and choose **25) Connect Fluidd to Spoolman**. Enter the Spoolman base URL, for example `http://192.168.0.20:7912`.

The installer checks the Spoolman API before changing Moonraker, detects the active config path from the Moonraker process (including the K3 mount at `/mnt/SDCARD/cxsw/printer_data/config/`), saves a timestamped config backup, writes the `[spoolman]` section, restarts Moonraker, and verifies that the `spoolman` component loaded. If Moonraker does not load it, the installer restores the saved config and restarts Moonraker again.

After the success message, refresh Fluidd at `http://<printer-ip>:4408`. Its built-in Spoolman controls can manage spools and set the active spool for usage tracking. Moonraker periodically sends filament usage to Spoolman.

This does not add CFS status or physical slot selection to Fluidd. The active Spoolman spool is a filament usage record; it does not command the K3 CFS hardware to load that slot.

## Disconnect

Choose **Remove a feature → 13) Spoolman connection**. The Helper Script backs up the config, removes the local `[spoolman]` section, and restarts Moonraker. Existing spool records remain on the Spoolman server.

## Troubleshooting

- If the API check fails, confirm that the Spoolman host is reachable from the printer and that port `7912` is allowed through its firewall.
- If Moonraker rolls the change back, inspect `/mnt/UDISK/printer_data/logs/moonraker.log` for a missing `spoolman` component or configuration error.
- If Moonraker reports the component as loaded but Fluidd does not show Spoolman, hard-refresh Fluidd and verify that the installed Fluidd copy is version `1.37.7` or later.
