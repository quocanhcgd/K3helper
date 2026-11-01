# K3 Screen Apps integration

The framebuffer HTTP server is vendored from [paxx12/screen-apps](https://github.com/paxx12/screen-apps), licensed under GPL-3.0-or-later. The K3 touch transform and Fluidd viewer are local adaptations.

K3 uses a 480x800 framebuffer. The viewer rotates it 90 degrees left and reports 800x480 browser points. Touch coordinates use the measured four-corner calibration recorded during K3 hardware testing; the kernel ioctl range for this panel is unreliable.

Run `scripts/screen_apps/install.sh install` as root on a K3 with the `/etc` overlay enabled and Fluidd installed. It installs a procd service bound to localhost port 18092, exposes it through Fluidd at `/screen/`, then registers `/screen/` with Moonraker as an `iframe` webcam. Fluidd renders it inside its built-in Camera dashboard card. `remove` removes only the matching managed webcam entry, disables the service, and removes the marked Nginx proxy.
