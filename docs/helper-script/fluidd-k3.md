# Fluidd on K3

The K3 Helper Script installs the current Fluidd release under `/mnt/UDISK/helper-script/fluidd` and serves it on port `4408`. Choose **8 — Fluidd update/repair** in the helper menu to download a clean release and apply the K3 compatibility setup.

## K3 integrations

Fluidd update and repair applies the K3-specific compatibility changes:

- Routes Fluidd's Moonraker API and WebSocket through the K3 nginx service.
- Keeps K3 camera entries visible and supports the firmware's camera service.
- Repairs file browsing, config editing, uploads, and downloads for the K3 Moonraker API and its one-shot HTTP tokens.
- Restores G-code thumbnails in Jobs and Re-print lists where Moonraker metadata is missing.
- Shows read-only CFS slot status on the dashboard. Slot selection for starting a print is not available through a verified K3 Moonraker API.
- Shows the installed Creality firmware version and preserves Fluidd's custom UI settings directory.

The compatibility setup is applied again on every repair. It does not replace printer configuration or Fluidd user settings.

## Chamber light macro

Creality controls the chamber light through its local WebSocket at `ws://127.0.0.1:9999/`, using `{"method":"set","params":{"lightSw":1}}` to turn it on and `lightSw: 0` to turn it off. Klipper must not claim GPIO42 through `[output_pin nozzle_light]` or another light `output_pin`: testing showed the WebSocket actuates the physical lamp after that pin is disabled and Klipper is restarted.

In the helper menu, choose **27 — Chamber LED On/Off macros for Fluidd**. The Helper installs a small Moonraker component that receives a remote method from the Klipper macros and relays the state to Creality's local WebSocket. It writes a separate `chamber_light.cfg`, includes it, restarts Moonraker and Klipper, and verifies that the component and both macros loaded. Fluidd displays `CHAMBER_LED_ON` and `CHAMBER_LED_OFF` in its existing **Macros** card. These macros use the same WebSocket as Creality and do not define an output pin.

If Klipper currently reports `output_pin nozzle_light` or `output_pin chamber_led`, disable the corresponding section in `printer.cfg` and restart Klipper before installing. The Helper stops if a light output pin is still active. Existing Helper-managed v1/v2 pin macros are upgraded to WebSocket macros when the old pin is managed by that file; the Helper leaves separately configured pins unchanged and reports the conflict.

The generated macro file contains:

```ini
[gcode_macro CHAMBER_LED_ON]
gcode:
  {action_call_remote_method("k3helper_chamber_light", state=1)}

[gcode_macro CHAMBER_LED_OFF]
gcode:
  {action_call_remote_method("k3helper_chamber_light", state=0)}
```

The Helper backs up the Moonraker and Klipper configs before changing them. If Moonraker cannot load the bridge, its config is restored. If Klipper does not load the macros, the macro include is removed. The Klipper backup is stored next to `printer.cfg` as `printer.cfg.k3helper-chamber-light.bak`.

Choose **Remove → 14 — Chamber light macro** to remove the helper-managed include, macro file, and Moonraker WebSocket bridge.

## Update and repair

To update the Helper Script, choose **15 — Update Helper Script from GitHub**. Then select **8 — Fluidd update/repair** and choose **Repair**. The repair downloads Fluidd again and reapplies the K3 integrations above.

Fluidd is available at:

```text
http://<printer-ip>:4408
```
