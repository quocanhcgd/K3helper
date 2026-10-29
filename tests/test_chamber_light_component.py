import base64
import hashlib
import importlib.util
import json
import socket
import threading
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "chamber_light_component.py"
SPEC = importlib.util.spec_from_file_location("chamber_light_component_test", MODULE_PATH)
COMPONENT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPONENT)


class ChamberLightComponentTests(unittest.TestCase):
    def test_sends_masked_websocket_set_frame(self):
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        messages = []
        failures = []

        def read_until(connection, delimiter):
            data = bytearray()
            while delimiter not in data:
                chunk = connection.recv(1024)
                if not chunk:
                    break
                data.extend(chunk)
            return bytes(data)

        def serve():
            try:
                connection, _ = server.accept()
                with connection:
                    request = read_until(connection, b"\r\n\r\n").decode("ascii")
                    key = next(
                        line.split(":", 1)[1].strip()
                        for line in request.split("\r\n")
                        if line.lower().startswith("sec-websocket-key:")
                    )
                    accept = base64.b64encode(
                        hashlib.sha1(
                            (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")
                        ).digest()
                    ).decode("ascii")
                    connection.sendall(
                        ("HTTP/1.1 101 Switching Protocols\r\n"
                         "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                         "Sec-WebSocket-Accept: %s\r\n\r\n" % accept).encode("ascii")
                    )
                    header = connection.recv(2)
                    first, second = header
                    size = second & 0x7F
                    if size == 126:
                        size = int.from_bytes(connection.recv(2), "big")
                    mask = connection.recv(4)
                    payload = bytearray()
                    while len(payload) < size:
                        payload.extend(connection.recv(size - len(payload)))
                    decoded = bytes(value ^ mask[i % 4] for i, value in enumerate(payload))
                    messages.append((first, json.loads(decoded.decode("utf-8"))))
            except Exception as error:
                failures.append(error)
            finally:
                server.close()

        thread = threading.Thread(target=serve)
        thread.start()
        COMPONENT.send_light_state("127.0.0.1", port, 1)
        thread.join(timeout=3)

        self.assertFalse(thread.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(messages, [(0x81, {"method": "set", "params": {"lightSw": 1}})])

    def test_rejects_non_boolean_light_state(self):
        with self.assertRaises(ValueError):
            COMPONENT.ChamberLightBridge.set_light_state(object(), state=2)


if __name__ == "__main__":
    unittest.main()
