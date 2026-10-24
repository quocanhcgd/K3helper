# K3 Firmware Version API

The Helper Script can run a small, read-only HTTP service that reads the current version data from `/mnt/UDISK/creality/userdata/config/system_version.json` for every request. It does not modify Moonraker or the firmware JSON.

## Install

From the K3 Helper Script menu, select **12) K3 Firmware API**. The service requires the `/etc` overlay to be mounted so its OpenWrt `procd` init service can persist across reboots.

## Endpoint

```text
GET http://<printer-ip>:8765/api/firmware
```

Example response:

```json
{
  "sys_version": "4.0.3.1.13",
  "fw_version": "",
  "hw_version": "CR0CUF039C13",
  "app_version": 1
}
```

The API rereads the source JSON on every request, so it reflects firmware updates without reinstalling the API. It omits serial numbers and other fields. `Access-Control-Allow-Origin: *` is enabled for browser-based clients. No authentication is required; use it only on a trusted local network.

If the source file is missing or invalid, the endpoint responds with HTTP `503` and `{"error":"firmware_version_unavailable"}`. Other paths return HTTP `404`.

Remove the service from the Helper Script's **Remove** menu by selecting **12) K3 Firmware API**.
