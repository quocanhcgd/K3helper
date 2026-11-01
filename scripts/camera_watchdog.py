#!/usr/bin/env python3
import ipaddress
import json
import sys
import time
import urllib.parse
import urllib.request

try:
    import fcntl
except ImportError:
    fcntl = None

STREAMS_URL = "http://127.0.0.1:1984/api/streams"
RESTART_URL = "http://127.0.0.1:1984/api/restart"
CAMERA_API = "http://127.0.0.1:7125/server/webcams"
PRINTER_IP_FILE = "/mnt/UDISK/helper-script/go2rtc-k3.ip"
REGISTRATION_LOCK_FILE = "/tmp/k3-camera-registration.lock"
CAMERA_NAME = "K3 Camera"
STREAM_NAME = "k3"
STALE_SAMPLE_LIMIT = 3
RESTART_COOLDOWN_SECONDS = 60


def _request_json(url, payload=None, method=None, timeout=5):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
    return json.loads(body) if body else {}


def _camera_payload(printer_ip):
    ipaddress.IPv4Address(printer_ip)
    return {
        "name": CAMERA_NAME,
        "location": "printer",
        "service": "webrtc-go2rtc",
        "target_fps": 15,
        "stream_url": "http://%s:1984/?src=%s" % (printer_ip, STREAM_NAME),
        "snapshot_url": "http://%s:1984/api/frame.jpeg?src=%s" % (
            printer_ip, STREAM_NAME,
        ),
        "flip_horizontal": False,
        "flip_vertical": False,
        "rotation": 0,
    }


def _restore_payload(camera):
    fields = (
        "name", "location", "service", "target_fps", "target_fps_idle",
        "stream_url", "snapshot_url", "flip_horizontal", "flip_vertical",
        "rotation", "icon",
    )
    return {key: camera[key] for key in fields if key in camera}


def _ensure_camera_registered(printer_ip=None):
    if printer_ip is None:
        try:
            with open(PRINTER_IP_FILE, encoding="utf-8") as ip_file:
                printer_ip = ip_file.read().strip()
        except OSError:
            return False
    if not printer_ip:
        return False

    desired = _camera_payload(printer_ip)
    response = _request_json(CAMERA_API + "/list")
    webcams = response.get("result", {}).get("webcams", [])
    existing = next(
        (camera for camera in webcams if camera.get("name") == CAMERA_NAME),
        None,
    )

    if existing is None:
        _request_json(CAMERA_API + "/item", desired, method="POST", timeout=10)
        print("K3 camera registered with Moonraker", flush=True)
        return True

    if existing.get("source") == "config":
        raise RuntimeError("K3 Camera is managed by moonraker.conf; refusing to overwrite it.")
    if existing.get("service") != "webrtc-go2rtc":
        raise RuntimeError("K3 Camera exists with a different service; refusing to overwrite it.")
    if (existing.get("stream_url") == desired["stream_url"] and
            existing.get("snapshot_url") == desired["snapshot_url"]):
        return False

    uid = existing.get("uid")
    if uid:
        update = {
            "uid": uid,
            "name": CAMERA_NAME,
            "stream_url": desired["stream_url"],
            "snapshot_url": desired["snapshot_url"],
        }
        _request_json(CAMERA_API + "/item", update, method="POST", timeout=10)
    else:
        # Older K3 Moonraker builds omit webcam UIDs; replace only our named entry.
        query = urllib.parse.urlencode({"name": CAMERA_NAME})
        _request_json(CAMERA_API + "/item?" + query, method="DELETE", timeout=10)
        try:
            _request_json(CAMERA_API + "/item", desired, method="POST", timeout=10)
        except Exception:
            try:
                previous = _restore_payload(existing)
                if previous:
                    _request_json(CAMERA_API + "/item", previous, method="POST", timeout=10)
            except Exception as restore_error:
                print("K3 camera restore failed:", restore_error, flush=True)
            raise

    print("K3 camera URLs refreshed in Moonraker", flush=True)
    return True


def ensure_camera_registered(printer_ip=None):
    if fcntl is None:
        return _ensure_camera_registered(printer_ip)
    with open(REGISTRATION_LOCK_FILE, "a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        return _ensure_camera_registered(printer_ip)


def inspect_stream_health(state, last_bytes, stale_count):
    stream = state.get(STREAM_NAME, {})
    if not stream.get("consumers"):
        return False, None, 0

    producers = stream.get("producers", [])
    current_bytes = None
    if producers:
        current_bytes = sum(int(producer.get("bytes_recv", 0) or 0)
                            for producer in producers)
    stalled = not producers or current_bytes == 0 or current_bytes == last_bytes
    stale_count = stale_count + 1 if stalled else 0
    return True, current_bytes, stale_count


def reconnect():
    request = urllib.request.Request(RESTART_URL, data=b"", method="POST")
    with urllib.request.urlopen(request, timeout=5) as response:
        response.read()
    print("go2rtc restart requested for stalled K3 camera", flush=True)


def run_watchdog():
    last_bytes = None
    stale_count = 0
    api_error_count = 0
    last_restart_attempt = 0
    while True:
        try:
            ensure_camera_registered()
        except Exception as error:
            print("Camera registration check failed:", error, flush=True)

        try:
            with urllib.request.urlopen(STREAMS_URL, timeout=3) as response:
                state = json.loads(response.read())
            active, last_bytes, stale_count = inspect_stream_health(
                state, last_bytes, stale_count,
            )
            api_error_count = 0
            now = time.monotonic()
            if (active and stale_count >= STALE_SAMPLE_LIMIT and
                    now - last_restart_attempt >= RESTART_COOLDOWN_SECONDS):
                last_restart_attempt = now
                reconnect()
                stale_count = 0
                last_bytes = None
        except Exception as error:
            print("Camera watchdog error:", error, flush=True)
            api_error_count += 1
            now = time.monotonic()
            if (api_error_count >= STALE_SAMPLE_LIMIT and
                    now - last_restart_attempt >= RESTART_COOLDOWN_SECONDS):
                last_restart_attempt = now
                try:
                    reconnect()
                except Exception as restart_error:
                    print("go2rtc restart request failed:", restart_error, flush=True)
                api_error_count = 0
                last_bytes = None
                stale_count = 0
        time.sleep(10)


def main(argv):
    if len(argv) == 3 and argv[1] == "--register":
        ensure_camera_registered(argv[2])
        return 0
    if len(argv) != 1:
        print("Usage: camera_watchdog.py [--register PRINTER_IP]", file=sys.stderr)
        return 2
    run_watchdog()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
