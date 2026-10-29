import asyncio
import importlib.util
import pathlib
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "moonraker_compat_component.py"
SPEC = importlib.util.spec_from_file_location("moonraker_compat_component_test", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeRequest:
    def __init__(self, values=None):
        self.values = values or {}

    def get_str(self, name, default=None):
        return self.values.get(name, default)


class FakeServer:
    def __init__(self):
        self.endpoints = {}
        self.file_manager = types.SimpleNamespace(
            get_file_metadata=lambda filename: {"size": 42}
        )

    def register_endpoint(self, path, methods, callback):
        self.endpoints[path] = (methods, callback)

    def lookup_component(self, name):
        if name == "file_manager":
            return self.file_manager
        raise RuntimeError(name)


class FakeConfig:
    def __init__(self):
        self.server = FakeServer()

    def get_server(self):
        return self.server


class MoonrakerCompatTests(unittest.TestCase):
    def setUp(self):
        self.config = FakeConfig()
        self.component = MODULE.K3MoonrakerCompat(self.config)

    def test_registers_optional_fluidd_endpoints(self):
        self.assertEqual(
            set(self.config.server.endpoints),
            {
                "/machine/peripherals/usb",
                "/machine/peripherals/serial",
                "/machine/peripherals/video",
                "/machine/peripherals/canbus",
                "/server/files/metascan",
            },
        )

    def test_peripheral_endpoints_return_empty_supported_shapes(self):
        self.assertEqual(asyncio.run(self.component._usb(None)), {"usb_devices": []})
        self.assertEqual(asyncio.run(self.component._serial(None)), {"serial_devices": []})
        self.assertEqual(
            asyncio.run(self.component._video(None)),
            {"v4l2_devices": [], "libcamera_devices": []},
        )
        self.assertEqual(asyncio.run(self.component._canbus(None)), {"can_uuids": []})

    def test_metascan_returns_cached_metadata(self):
        result = asyncio.run(
            self.component._metascan(FakeRequest({"filename": "gcodes/test.gcode"}))
        )
        self.assertEqual(result, {"size": 42, "filename": "gcodes/test.gcode"})


if __name__ == "__main__":
    unittest.main()
