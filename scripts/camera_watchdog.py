#!/usr/bin/env python3
import json
import time
import urllib.request

STREAM_URL = "http://127.0.0.1:1984/api/streams?src=k3"
STREAMS_URL = "http://127.0.0.1:1984/api/streams"


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
