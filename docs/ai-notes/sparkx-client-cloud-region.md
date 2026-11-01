# AI Handoff: K3 Cloud Region from SparkX Client

Use this note when changing the SparkX Windows client's K3 **Chuyển vùng Cloud** feature.

## Script used by the client

- The client feature ID remains `cloud_region`; the feature button and run flow are in `sparkx-i8/client/sparkx_client/app.py`.
- The license server maps `("k3", "cloud_region")` in `sparkx-i8/license-server/main.py` to two source files: `scripts/k3/prepare_screen_apps.sh` and `scripts/k3/cloud_region_com.sh`.
- The repository sources are `sparkx-i8/scripts/k3/prepare_screen_apps.sh` and `sparkx-i8/scripts/k3/cloud_region_com.sh`.
- The signed bundle's default entrypoint is `prepare_screen_apps.sh`; the client runs it first, then invokes `feature.sh` (the packaged region-switch script) only when preparation returns success. This order is implemented with `SshPrinter.run_script_bundle_sequence()` in `sparkx-i8/client/sparkx_client/core.py`.
- The deployed source checkout paths are `<checkout>/scripts/k3/prepare_screen_apps.sh` and `<checkout>/scripts/k3/cloud_region_com.sh`. `deploy_ubuntu.sh` and `update_server.sh` copy both repository sources into these paths for signing and distribution.
- Do not point the client's K3 `cloud_region` bundle at `scripts/cloud_region.sh` or `scripts/k3/cloud_region.sh`; those are older interactive menu scripts with two-way region choices.

## Behavior and constraints

- The client bundle toggles between `Server.COM` and `Server.CN` based on the active Cloud endpoint.
- The preparation script checks the K3 board and Helper Script storage, installs/repairs Screen Apps, and verifies the local snapshot and Fluidd viewer endpoints.
- The region script independently checks the K3 board, removable storage, and Screen Apps readiness, stages `/mnt/exUDISK/custom_server_config`, and sends `SIGTERM` only to `22_AppUi`. `27_AppMonitor` then relaunches the touchscreen UI so firmware reads the staged request. Do not restart `/etc/init.d/app3_0`: its stop hook kills other firmware services.
- Screen Apps serves the viewer at `http://<printer-ip>:4408/screen/`. The operator confirms the popup there. After the firmware logs both confirmation and successful Keybox write, the script removes the request file from USB.
- Keep the existing signed bundle verification and license checks in the client. Do not bypass the API by running a local/unsigned replacement script directly over SSH.

## Verification

From `sparkx-i8/license-server`, run `python -m pytest -q`. The bundle test checks that both scripts are signed together, preparation is the default entrypoint, and the region script toggles either server while restarting only the supervised App UI and removing the request after success.

From `sparkx-i8/client`, run `python -m pytest -q` to verify signed-bundle execution and that a preparation error prevents the region script from running.
