# Spoolman on K3

Fluidd 1.37.7 includes a Spoolman interface. Moonraker must load a `[spoolman]` component and reach the Spoolman API. K3 firmware does not ship the upstream component, so the Helper Script supplies a small compatibility bridge from UDISK through `PYTHONPATH`; it does not install the Spoolman server on the printer.

## Before connecting

Run Spoolman on another computer, NAS, or server that stays available on the same network. This K3 integration configures Moonraker's connection; it does not install the server on the printer.

Confirm that this URL opens from a browser on the LAN, replacing the address with the Spoolman host:

```text
http://192.168.0.20:7912/api/v1/info
```

It should return JSON. Use the base URL, without `/api/v1/info`, in the Helper Script. Both `192.168.0.43:7912` and `http://192.168.0.43:7912` are accepted; the first form is automatically treated as HTTP.

## Connect the printer

Update the K3 Helper Script directly over SSH:

```sh
python3 /mnt/UDISK/helper-script/scripts/update_helper.py
```

Then reconnect Moonraker to Spoolman. Run the interactive menu and choose **25) Connect Fluidd to Spoolman**, or run the script directly:

```sh
sh /mnt/UDISK/helper-script/scripts/spoolman.sh install
```

Enter the Spoolman base URL, for example `http://192.168.0.20:7912`.

The installer checks the Spoolman API before changing Moonraker and detects the config path from its running process. If Moonraker currently reads the stock file at `/usr/share/moonraker/moonraker.conf`, the installer finds the writable printer config mount (including `/mnt/SDCARD/cxsw/printer_data/config`), creates a persistent wrapper that includes the stock config when needed, and updates the init script under `/etc` to load it. This requires the `/etc` overlay to be mounted read-write. It backs up both files, restarts Moonraker, and verifies that the `spoolman` component loaded. If it does not load, the installer restores the config and startup script, then restarts Moonraker again.

After the success message, refresh Fluidd at `http://<printer-ip>:4408`. Its built-in Spoolman controls can browse/manage spools and set an active spool ID. The K3 bridge follows Fluidd 1.37.7's proxy response contract, emits the active-spool and connection status notifications, and stores the active spool ID in Moonraker's database when that component is available. Automatic extrusion usage reporting still requires Klipper position subscriptions, Moonraker's history integration, and a Spoolman WebSocket connection; those upstream behaviors are not enabled by this compatibility bridge. The generated `[spoolman]` section therefore only contains the server URL and does not set Moonraker's unused `sync_rate` option.

This does not add CFS status or physical slot selection to Fluidd. The active Spoolman spool is a filament usage record; it does not command the K3 CFS hardware to load that slot.

## Disconnect

Choose **Remove a feature → 13) Spoolman connection**. The Helper Script backs up the config, removes the local `[spoolman]` section, restores the Moonraker startup script when this integration patched it, and restarts Moonraker. Existing spool records remain on the Spoolman server.

## Troubleshooting

- If the API check fails, confirm that the Spoolman host is reachable from the printer and that port `7912` is allowed through its firewall.
- If Moonraker rolls the change back, inspect `/mnt/UDISK/printer_data/logs/moonraker.log` for a component import or configuration error.
- If Moonraker reports the component as loaded but Fluidd does not show Spoolman, hard-refresh Fluidd and verify that the installed Fluidd copy is version `1.37.7` or later.
- Run **26) Diagnose Spoolman integration** and check that `/server/info` contains `spoolman`, `/server/config` contains a `spoolman` section, `/server/spoolman/spool_id` and `/server/spoolman/status` respond, and the proxy can fetch `/v1/info` and `/v1/spool`.
