#!/usr/bin/env python3
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.request

STREAM_URL = "http://127.0.0.1:1984/api/streams?src=k3"
STREAMS_URL = "http://127.0.0.1:1984/api/streams"
CAMERA_API = "http://127.0.0.1:7125/server/webcams"
PRINTER_IP_FILE = "/mnt/UDISK/helper-script/go2rtc-k3.ip"
CAMERA_NAME = "K3 Camera"


def ensure_camera_registered():
    with urllib.request.urlopen(CAMERA_API + "/list", timeout=3) as response:
        webcams = json.loads(response.read()).get("result", {}).get("webcams", [])
    if any(camera.get("name") == CAMERA_NAME for camera in webcams):
        return

    try:
        with open(PRINTER_IP_FILE, encoding="utf-8") as ip_file:
            printer_ip = ip_file.read().strip()
    except OSError:
        return
    if not printer_ip:
        return

    camera = {
        "name": CAMERA_NAME,
        "location": "printer",
        "service": "webrtc-go2rtc",
        "target_fps": 15,
        "stream_url": "http://%s:1984/?src=k3" % printer_ip,
        "snapshot_url": "http://%s:1984/api/frame.jpeg?src=k3" % printer_ip,
        "flip_horizontal": False,
        "flip_vertical": False,
        "rotation": 0,
    }
    request = urllib.request.Request(
        CAMERA_API + "/item",
        data=json.dumps(camera).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        response.read()
    print("K3 camera registration restored in Moonraker", flush=True)


def reconnect():
    try:
        with urllib.request.urlopen(STREAM_URL, timeout=10) as response:
            response.read()
    except Exception as error:
        print("Camera reconnect failed:", error, flush=True)


last_bytes = None
stale_count = 0
while True:
    try:
        ensure_camera_registered()
        with urllib.request.urlopen(STREAMS_URL, timeout=3) as response:
            state = json.loads(response.read())
        producers = state.get("k3", {}).get("producers", [])
        current_bytes = producers[0].get("bytes_recv", 0) if producers else 0
        if current_bytes == 0 or current_bytes == last_bytes:
            stale_count += 1
        else:
            stale_count = 0
        if stale_count >= 3:
            reconnect()
            stale_count = 0
        last_bytes = current_bytes
    except Exception as error:
        print("Camera watchdog error:", error, flush=True)
        reconnect()
        last_bytes = None
        stale_count = 0
    time.sleep(10)
