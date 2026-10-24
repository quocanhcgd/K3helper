#!/usr/bin/env python3
"""Read-only HTTP API for selected Creality K3 firmware metadata."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


VERSION_FILE = Path("/mnt/UDISK/creality/userdata/config/system_version.json")
HOST = "0.0.0.0"
PORT = 8765


class FirmwareHandler(BaseHTTPRequestHandler):
    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/api/firmware":
            self.send_json(404, {"error": "not_found", "endpoint": "/api/firmware"})
            return

        try:
            with VERSION_FILE.open(encoding="utf-8") as version_file:
                source = json.load(version_file)
            if not isinstance(source, dict):
                raise ValueError("firmware version document must be an object")
        except (OSError, ValueError, json.JSONDecodeError):
            self.send_json(503, {"error": "firmware_version_unavailable"})
            return

        fields = ("sys_version", "fw_version", "hw_version", "app_version")
        self.send_json(200, {key: source.get(key, "") for key in fields})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def log_message(self, format_string, *args):
        print("firmware-api: " + format_string % args, flush=True)


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), FirmwareHandler).serve_forever()
