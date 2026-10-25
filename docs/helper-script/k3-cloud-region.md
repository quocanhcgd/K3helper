# K3 Cloud Region Switch

On K3 firmware `4.0.3.1.13` for board `CR0CUF039C13`, the touchscreen UI checks a request file on removable storage at `/mnt/exUDISK/custom_server_config`. The supported tokens found in the firmware are `Server.COM` and `Server.CN`. The UI prompts for confirmation and persists the selection in the printer's keybox; editing `cloundServerType` in `/etc/appcfg/22_FactoryConfigAppUi.json` alone does not switch the active Cloud endpoint.

The international switch was confirmed on a K3 running this firmware: the UI logged `udisk server config is COM`, displayed its custom-switch prompt, and the user confirmed it on the touchscreen. The China Mainland token is present in the same firmware, but returning to that region has not been independently verified on this printer.

## Prepare a Switch Request

Keep the printer idle. Connect the USB drive and confirm it is mounted at `/mnt/exUDISK`. Run the Helper Script as root and choose **14) K3 Cloud region switch**.

Choose **1** for international (`Server.COM`) or **2** for China Mainland (`Server.CN`). The script writes the exact token plus a newline to `/mnt/exUDISK/custom_server_config`. It refuses to overwrite an existing request file. The file only requests the switch; it does not confirm the change or modify firmware files.

Check the printer touchscreen and confirm the region-switch prompt. The UI may reject the request if the printer is in factory mode, the USB is not detected by the UI, the request is unchanged, or the file contents are unsupported. The relevant UI log is:

```sh
grep -F 'MachineServerSwitch' /mnt/SDCARD/cxsw/creality/userdata/log/22_AppUi.log | tail -n 30
```

Successful request detection includes `udisk server config is COM` or `udisk server config is CN` and `show custom server switch tips`. After confirming on the touchscreen, look for `custom server switch confirmed` and `write keybox after cmd ok`.

## Verify the Active Region

After the UI confirms the change and Cloud reconnects, inspect the app log and live MQTT endpoint:

```sh
grep -E 'init param server|now server|qrcode Info' /mnt/SDCARD/cxsw/creality/userdata/log/app-server.log | tail -n 30
netstat -ntp | grep app-server
```

The QR scan host `qr.creality.com` by itself does not prove which Cloud region is active. Verify the MQTT connection as well. The account may need to be linked again after changing regions.

## Remove the Request File

Once the switch is confirmed, return to menu **14** and choose **3** to remove `/mnt/exUDISK/custom_server_config`. Removing this trigger file does not undo the region already saved in the keybox.

If the UI reports `unsupported custom server config`, remove the request with menu option **3** and do not edit protected configuration files or try arbitrary token values.
