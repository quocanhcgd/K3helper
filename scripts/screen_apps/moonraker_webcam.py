#!/usr/bin/env python3
"""Register Screen Apps with Fluidd's built-in Camera card through Moonraker."""

import json
import sys
import urllib.parse
import urllib.request

CAMERA_API = "http://127.0.0.1:7125/server/webcams"
CAMERA_NAME = "K3 Screen Apps"
SCREEN_URL = "/screen/"


def request_json(url, payload=None, method=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:
        body = response.read()
    return json.loads(body) if body else {}


def register():
    webcams = request_json(CAMERA_API + "/list").get("result", {}).get("webcams", [])
    existing = next((camera for camera in webcams if camera.get("name") == CAMERA_NAME), None)
    if existing:
        if (
            existing.get("service") == "iframe"
            and existing.get("stream_url") == SCREEN_URL
            and existing.get("source") != "config"
        ):
            print("Screen Apps is already registered in Fluidd's Camera card.")
            return
        raise RuntimeError(
            "A webcam named 'K3 Screen Apps' already exists with different settings; "
            "it was left unchanged."
        )

    webcam = {
        "name": CAMERA_NAME,
        "location": "printer",
        "service": "iframe",
        "enabled": True,
        "stream_url": SCREEN_URL,
        "snapshot_url": "",
        "aspect_ratio": "5:3",
        "flip_horizontal": False,
        "flip_vertical": False,
        "rotation": 0,
    }
    request_json(CAMERA_API + "/item", webcam, method="POST")
    print("Registered Screen Apps in Fluidd's built-in Camera card.")


def unregister():
    webcams = request_json(CAMERA_API + "/list").get("result", {}).get("webcams", [])
    existing = next((camera for camera in webcams if camera.get("name") == CAMERA_NAME), None)
    if existing is None:
        print("Screen Apps has no Fluidd webcam entry.")
        return
    if (
        existing.get("service") != "iframe"
        or existing.get("stream_url") != SCREEN_URL
        or existing.get("source") == "config"
    ):
        raise RuntimeError(
            "The 'K3 Screen Apps' webcam no longer matches the managed entry; "
            "it was left unchanged."
        )
    query = urllib.parse.urlencode({"name": CAMERA_NAME})
    request_json(CAMERA_API + "/item?" + query, method="DELETE")
    print("Removed Screen Apps from Fluidd's Camera card.")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("register", "unregister"):
        raise SystemExit("Usage: moonraker_webcam.py [register|unregister]")
    try:
        register() if sys.argv[1] == "register" else unregister()
    except Exception as exc:
        print("Screen Apps webcam registration failed: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
