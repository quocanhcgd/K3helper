# AI Handoff: K3 Screen Apps in Fluidd

Use this note when changing or debugging the K3 framebuffer viewer integration. Do not assume the upstream `screen-apps` program works unchanged on the K3: the tested panel needs a rotated viewer and a measured touch transform.

## Device facts

- Printer board: `CR0CUF039C13`, K3.
- OS reports `armv7l`, Python `3.9.12`, Pillow `8.2.0`.
- Framebuffer: `/dev/fb0`, `480x800`, `32` bits per pixel; `/proc/fb` lists framebuffer `0`.
- Touch device: `/dev/input/event0`, named `gt9xxnew_ts`.
- The kernel touch-axis ioctl data was not useful. Use the physical-corner calibration below instead of inferring axis extents from ioctl.
- `/etc` overlay was active at install time, so the init service can persist across reboot.

## Screen and touch mapping

The viewer presents the portrait framebuffer as an `800x480` landscape image rotated 90 degrees left (`rotate(-Math.PI / 2)`). Browser coordinates are clamped to `x=0..799`, `y=0..479`, then mapped to the touch device as:

```python
touch_x = round(475 - y * (460 / 479))
touch_y = round(8 + x * (769 / 799))
```

This was measured from physical taps at the four corners. Do not replace it with a generic linear scaling based on framebuffer width/height. Keep the iframe and `/screen/` same-origin so the browser can send touch requests without cross-origin configuration. The viewer supports pointer down/move/up for tap, hold, and drag.

## Firmware layout and integration choice

The stock firmware's `/usr/share/fluidd` is not the active page root for this installation. The live Nginx server on port `4408` uses `/mnt/UDISK/helper-script/fluidd` as its document root. The firmware also exposes `/mnt/SDCARD/cxsw/printer_data/config` and `/mnt/UDISK/printer_data/config`; Fluidd compatibility currently picks the SDCARD config root when present and otherwise falls back to UDISK.

Fluidd Custom UI on this firmware is provided through `.fluidd-theme` for theme CSS/background assets; it is not needed for the live screen. Fluidd v1.37.7 already supports `iframe` as a webcam service, rendered by its native Camera dashboard card. Register `/screen/` through Moonraker's `server.webcams` API with `service: "iframe"`; Fluidd creates its normal camera item inside CameraCard, including the existing card's layout, collapse, and fullscreen behavior. Do not inject a Screen Apps script or create a new dashboard card.

Fluidd's native `CameraItem.vue` overlays each webcam's name at the lower-left of its image. On K3 that overlay can intercept touchscreen pointer input, so the installer adds a narrowly scoped rule to Moonraker's documented `.fluidd-theme/custom.css`: hide `.camera-name` only for the iframe whose source contains `/screen/`, and disable pointer events on that overlay. It does not change Fluidd's app bundle, webcam name in Moonraker, or other camera labels. Removal deletes only this marked CSS block and preserves the rest of `custom.css`.

This is verified against the tagged Fluidd v1.37.7 sources: [`CameraCard.vue`](https://github.com/fluidd-core/fluidd/blob/v1.37.7/src/components/widgets/camera/CameraCard.vue) displays configured Moonraker webcams; [`CameraConfigDialog.vue`](https://github.com/fluidd-core/fluidd/blob/v1.37.7/src/components/settings/cameras/CameraConfigDialog.vue) lists `iframe` as an HTTP Page service; [`IframeCamera.vue`](https://github.com/fluidd-core/fluidd/blob/v1.37.7/src/components/widgets/camera/services/IframeCamera.vue) loads `stream_url` in an iframe; [`CameraItem.vue`](https://github.com/fluidd-core/fluidd/blob/v1.37.7/src/components/widgets/camera/CameraItem.vue) explicitly enables pointer events on iframe feeds; and [`moonraker.webcam.d.ts`](https://github.com/fluidd-core/fluidd/blob/v1.37.7/src/typings/moonraker.webcam.d.ts) defines the webcam service and API shape. This confirms interactive iframe/touch is supported by the native camera integration, not merely an image preview.

The live request path is:

```text
Fluidd's native CameraCard -> Moonraker webcam entry (service=iframe)
  -> Fluidd IframeCamera -> iframe /screen/
  -> Nginx server :4408, location ^~ /screen/
  -> proxy_pass http://127.0.0.1:18092/
  -> framebuffer HTTP server (HTML, /snapshot, POST /touch)
  -> /dev/fb0 and /dev/input/event0
```

Keep the registered iframe and the viewer's `snapshot`/`touch` requests on this same-origin path. The relative fetch URLs are important because an absolute `/snapshot` would bypass the `/screen/` location and resolve against Fluidd's static root, while a direct browser request to the daemon would require CORS and expose a LAN port.

## Repeatable implementation procedure

1. Verify the target before changing it: board ID, Fluidd version, actual `root` directive in the Nginx server listening on `4408`, framebuffer geometry/bpp, touch event device, Python/Pillow, `/etc` overlay, and the current Fluidd index/theme config paths. Do not infer the active web root from `/usr/share/fluidd` alone.
2. Keep the upstream server separate from Fluidd static assets. Install it under a managed UDISK directory and start it through an OpenWrt `rc.common`/procd service. Bind to `127.0.0.1`; select a port only after checking it is unused.
3. Use the measured K3 transform and rotated landscape viewer in this note. Verify that pointer down/move/up each reaches the backend, since sliders and hold controls need more than click events.
4. Add an explicit Nginx location inside the unique server block whose `listen` is `4408`: redirect `/screen` to `/screen/`, then use `location ^~ /screen/` and a trailing-slash `proxy_pass` to the daemon. Back up the config, run `nginx -t`, restart Nginx only after syntax succeeds, and preserve unrelated locations/configuration.
5. Use Moonraker's `GET /server/webcams/list` and `POST /server/webcams/item` to register a uniquely named entry such as `K3 Screen Apps`, `service: "iframe"`, and `stream_url: "/screen/"`. `/screen/` is resolved against the Fluidd origin by `IframeCamera.buildAbsoluteUrl`, preserving same-origin touch requests. `aspect_ratio: "5:3"` matches the landscape viewer. Fluidd's `CameraCard` renders it automatically; do not edit its DOM or inject app JS.
6. Make registration idempotent and safe: if the exact managed entry exists, leave it; if that name exists with different URL/service or is config-managed, fail without overwriting. Remove only the matching database entry. Enable/repair should register the entry; remove should unregister it, stop the service, and remove only the marked proxy.
7. Verify the daemon locally, through Nginx, and in the actual Fluidd UI. Check HTML `200`, snapshot `200 image/png`, Screen Apps listed within the existing Camera card, and service status/autostart. Test a harmless touch target; test a drag only on a control where the result can be safely observed.

## Installed state (verified 2026-11-01)

- Fluidd: `http://192.168.0.158:4408/`, observed version `1.37.7-b2edab5`.
- Screen endpoint: `http://192.168.0.158:4408/screen/`.
- Upstream service listens only on `127.0.0.1:18092`, supervised by procd service `/etc/init.d/k3-screen-apps`.
- Service was `running`; `/etc/rc.d/S97k3-screen-apps` and `K10k3-screen-apps` existed.
- Nginx proxies `/screen/` to `127.0.0.1:18092`; its block is marked `# k3-screen-apps-proxy` in `/etc/nginx/nginx.conf`.
- Screen Apps is registered in Moonraker as a webcam (`service: iframe`, `stream_url: /screen/`) and appears in Fluidd's native Camera card.
- The native `K3 Screen Apps` caption is hidden by a marked rule in the active Moonraker `.fluidd-theme/custom.css`; the caption layer no longer intercepts touch input.
- Live `/etc/nginx/nginx.conf` has the marked `/screen/` proxy nested in the port-4408 server. Its actual document root is `/mnt/UDISK/helper-script/fluidd`, not the firmware's `/usr/share/fluidd`.
- At verification time, both SDCARD and UDISK printer config directories existed, and neither `.fluidd-theme` directory contained files. The compatibility helper's default chooses SDCARD whenever that directory exists.
- Verified through Fluidd on 2026-11-01: `K3 Screen Apps` appeared inside the existing Cameras card beside `K3 Camera`; its iframe showed the live K3 display. `/screen/` returned HTTP 200, `/screen/snapshot` returned `image/png`, the service was running, and `nginx -t` passed. The printer was actively printing during this visual verification, so no touch input was sent.
- The earlier temporary preview confirmed that a browser tap could open a Fluidd panel while leaving fan values unchanged. After the packaged pointer down/move/up viewer was deployed, HTTP/UI and process health were verified; a new physical drag test was not performed in that final session.
- SSH password was provided during setup. Do not store or repeat it in source, logs, or notes. Ask the user for updated access if the current SSH session is unavailable.

## Repository entry points

- Upstream server (vendored): `scripts/screen_apps/fb-http.py`.
- Rotated interactive viewer: `scripts/screen_apps/html/index.html`.
- Install/repair/remove: `scripts/screen_apps/install.sh`.
- Native Fluidd Camera card registration/removal: `scripts/screen_apps/moonraker_webcam.py`.
- Nginx `/screen/` proxy and service lifecycle: `scripts/screen_apps/install.sh`.
- Helper menu: choice `28` installs/repairs; Remove choice `15` removes.
- User-facing K3 notes: `docs/helper-script/fluidd-k3.md`.
- Focused tests: `tests/test_screen_apps_integration.py`.

On the printer, installed files are under `/mnt/UDISK/helper-script/screen-apps/`; the source and installer are under `/mnt/UDISK/helper-script/scripts/screen_apps/`.

## Client and license-server distribution

- The license feature ID is `screen_apps`; it is available only for board `CR0CUF039C13` (K3).
- The signed K3 bundle is defined in `sparkx-i8/license-server/main.py`. It includes the full runtime, viewer, Fluidd webcam helper, installer, GPL-3 license, and `prepare_screen_apps.sh` entrypoint.
- `sparkx-i8/license-server/deploy_ubuntu.sh` and `update_server.sh` copy these files into the configured `I8_SCRIPT_SOURCE_ROOT` before the API serves bundles.
- Client profile support and the separate feature row are in `sparkx-i8/client/sparkx_client/core.py` and `app.py`. A successful `screen_apps` run records readiness for that printer identity and starts the debug preview only after the signed installer returns successfully.
- Fluidd registration remains the Moonraker `iframe` webcam at `/screen/`; do not add a custom Fluidd dashboard card or inject client-side Fluidd JavaScript.
- Client code is currently versioned `1.3.11`; a releasable client build still needs to be packaged and published separately.

## Useful checks

On the printer as root:

```sh
/etc/init.d/k3-screen-apps status
nginx -t
python3 -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:4408/screen/').status)"
python3 -c "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:4408/screen/snapshot'); print(r.status, r.headers.get('Content-Type'))"
```

From the repository:

```sh
python -m unittest discover -s tests
python -m py_compile scripts/screen_apps/fb-http.py scripts/fluidd_k3_compat.py
```

## Known implementation issues and follow-up

- The first implementation injected a custom Fluidd dashboard card. The current installer removes that old script/tag and registers a native Moonraker webcam entry. `fluidd_k3_compat.py` no longer injects the custom card, so routine Fluidd/camera repairs will not recreate it.
- A fresh physical hold/drag test is still desirable when the printer is idle. The current native camera iframe is source-verified to accept pointer events; hardware mapping itself was previously validated with corner taps and the viewer sends pointer down/move/up.
- **Nginx rollback needs care.** `install.sh` keeps a full-file backup on first install. Its failure path copies that whole backup back, which can discard unrelated Nginx edits made after the backup was created. Prefer save/restore of just the marked block or take a fresh rollback copy immediately before each mutation; never overwrite a changed user config with a stale full-file backup.
- The vendored `scripts/screen_apps/LICENSE` now contains the full GPL-3 text. Preserve its SPDX attribution in `fb-http.py` and include the license in every distributed bundle.
- The last hardware validation before the pointer down/move/up update verified the earlier tap path against a harmless Fluidd panel. The packaged hold/drag support has had HTTP/UI and process health checks, but still needs a new physical hold/drag check on an appropriate safe control.
