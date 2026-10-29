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

The Fluidd macros use Klipper's `nozzle_light` output pin. This lets Fluidd control the light through `SET_PIN PIN=nozzle_light`. A custom pin named `chamber_led` does not satisfy that lookup. These macros do not use the Creality screen WebSocket.

The Creality screen WebSocket accepts `{"method":"set","params":{"lightSw":1}}` and logs the requested light state, but that alone does not confirm hardware control. In testing, the WebSocket log changed to `lightSw = 1` while Moonraker still reported `nozzle_light = 0.0` and the lamp stayed off. Treat WebSocket-to-light actuation as unresolved; use the Fluidd macros until the firmware path to GPIO is confirmed.

In the helper menu, choose **27 — Chamber LED On/Off macros for Fluidd**. The helper backs up `printer.cfg`, writes a separate `chamber_light.cfg`, includes it, restarts Klipper, and verifies that both macros loaded. Fluidd displays `CHAMBER_LED_ON` and `CHAMBER_LED_OFF` in its existing **Macros** card.

If Klipper already reports `output_pin nozzle_light`, the helper adds only the two macros, avoiding a duplicate pin definition. Otherwise it also adds the verified K3 pin definition and the two macros. If an old custom `output_pin chamber_led` exists by itself, rename that section to `output_pin nozzle_light` before installing; the Helper stops instead of defining the same GPIO under two names:

```ini
[output_pin nozzle_light]
pin: rpi:gpio42
value: 0
shutdown_value: 0

[gcode_macro CHAMBER_LED_ON]
gcode:
  SET_PIN PIN=nozzle_light VALUE=1

[gcode_macro CHAMBER_LED_OFF]
gcode:
  SET_PIN PIN=nozzle_light VALUE=0
```

If the older Helper Script already installed a managed `chamber_led` macro, choose **Remove → 14** first, then choose **27** to install the `nozzle_light` version.

If Klipper does not load both macros, the helper restores the previous config automatically. The backup is stored next to `printer.cfg` as `printer.cfg.k3helper-chamber-light.bak`.

Choose **Remove → 14 — Chamber light macro** to remove only the helper-managed include and macro file.

## Update and repair

To update the Helper Script, choose **15 — Update Helper Script from GitHub**. Then select **8 — Fluidd update/repair** and choose **Repair**. The repair downloads Fluidd again and reapplies the K3 integrations above.

Fluidd is available at:

```text
http://<printer-ip>:4408
```
