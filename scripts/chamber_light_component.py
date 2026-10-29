"""Bridge Klipper macros to Creality's local chamber-light WebSocket."""

import base64
import hashlib
import json
import logging
import os
import socket
import struct
import time


LOG = logging.getLogger(__name__)


def _client_frame(payload):
    mask = os.urandom(4)
    length = len(payload)
    if length < 126:
        header = bytes((0x81, 0x80 | length))
    elif length < 65536:
        header = bytes((0x81, 0xFE)) + struct.pack("!H", length)
    else:
        header = bytes((0x81, 0xFF)) + struct.pack("!Q", length)
    masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    return header + mask + masked


def send_light_state(host, port, state):
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    request = (
        "GET / HTTP/1.1\r\n"
        "Host: %s:%s\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Key: %s\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    ) % (host, port, key)
    expected_accept = base64.b64encode(
        hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
    ).decode("ascii")
    payload = json.dumps(
        {"method": "set", "params": {"lightSw": state}},
        separators=(",", ":"),
    ).encode("utf-8")

    with socket.create_connection((host, port), timeout=2.5) as connection:
        connection.settimeout(2.5)
        connection.sendall(request.encode("ascii"))
        response = bytearray()
        while b"\r\n\r\n" not in response and len(response) < 8192:
            chunk = connection.recv(1024)
            if not chunk:
                raise RuntimeError("Creality WebSocket closed during handshake")
            response.extend(chunk)
        headers = bytes(response).split(b"\r\n\r\n", 1)[0].decode("latin-1")
        if not headers.startswith("HTTP/1.1 101 "):
            raise RuntimeError("Creality WebSocket handshake failed: %s" % headers.splitlines()[0])
        if ("sec-websocket-accept: " + expected_accept).lower() not in headers.lower():
            raise RuntimeError("Creality WebSocket returned an invalid handshake")
        connection.sendall(_client_frame(payload))
        time.sleep(0.2)


class ChamberLightBridge:
    def __init__(self, config):
        self.server = config.get_server()
        self.host = config.get("host", "127.0.0.1")
        self.port = config.getint("port", 9999)
        self.server.register_remote_method(
            "k3helper_chamber_light", self.set_light_state
        )

    def set_light_state(self, state=None):
        try:
            value = int(state)
        except (TypeError, ValueError):
            raise ValueError("Chamber light state must be 0 or 1")
        if value not in (0, 1):
            raise ValueError("Chamber light state must be 0 or 1")
        try:
            send_light_state(self.host, self.port, value)
        except Exception:
            LOG.exception("K3 Helper could not send chamber-light state %s", value)


def load_component(config):
    return ChamberLightBridge(config)
