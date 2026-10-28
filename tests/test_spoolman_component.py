import asyncio
import importlib.util
import pathlib
import sys
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "spoolman_component.py"


class FakeServer:
    def __init__(self, database=None):
        self.endpoints = {}
        self.notifications = []
        self.events = []
        self.database = database

    def register_endpoint(self, path, method, callback):
        self.endpoints[path] = (method, callback)

    def register_notification(self, name):
        self.notifications.append(name)

    def register_remote_method(self, name, callback):
        self.remote_method = (name, callback)

    def send_event(self, name, payload):
        self.events.append((name, payload))

    def lookup_component(self, name):
        if self.database is None:
            raise RuntimeError("database unavailable")
        return self.database

    @staticmethod
    def error(message, status_code=500):
        error = RuntimeError(message)
        error.status_code = status_code
        return error


class FakeDatabase:
    def __init__(self, initial=None):
        self.values = dict(initial or {})

    async def get_item(self, namespace, key, default=None):
        return self.values.get((namespace, key), default)

    def insert_item(self, namespace, key, value):
        self.values[(namespace, key)] = value


class FakeConfig:
    def __init__(self, database=None):
        self.server = FakeServer(database)

    def get_server(self):
        return self.server

    def get(self, name):
        return "http://spoolman.local:7912"


class FakeWebRequest:
    def __init__(self, values):
        self.values = values

    def get_str(self, name, default=None):
        return self.values.get(name, default)

    def get(self, name, default=None):
        return self.values.get(name, default)

    def get_boolean(self, name, default=False):
        return self.values.get(name, default)


class SpoolmanComponentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        common = types.ModuleType("moonraker.common")
        common.RequestType = types.SimpleNamespace(GET=1, POST=2)
        top_level_common = types.ModuleType("common")
        top_level_common.RequestType = common.RequestType
        moonraker = types.ModuleType("moonraker")
        moonraker.__path__ = []
        moonraker.common = common
        sys.modules.setdefault("moonraker", moonraker)
        sys.modules["moonraker.common"] = common
        sys.modules["common"] = top_level_common
        spec = importlib.util.spec_from_file_location("spoolman_component_test", MODULE_PATH)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def setUp(self):
        self.config = FakeConfig()
        self.bridge = self.module.SpoolmanBridge(self.config)

    def test_registers_fluidd_proxy_and_notifications(self):
        self.assertEqual(
            self.config.server.notifications,
            [
                "spoolman:spoolman_status_changed",
                "spoolman:active_spool_set",
            ],
        )
        self.assertIn("/server/spoolman/proxy", self.config.server.endpoints)
        self.assertEqual(self.config.server.endpoints["/server/spoolman/proxy"][0], 2)

    def test_loads_with_creality_top_level_common_module(self):
        sys.modules.pop("moonraker.common", None)
        sys.modules.pop("moonraker", None)
        spec = importlib.util.spec_from_file_location("spoolman_component_top_level_test", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(hasattr(module, "SpoolmanBridge"))

    def test_proxy_uses_fluidd_v2_response_contract(self):
        self.bridge._request = lambda *args: ({"id": 2}, {"content-type": "application/json"}, 200)
        request = FakeWebRequest({
            "request_method": "GET",
            "path": "/v1/spool",
            "use_v2_response": True,
        })
        result = asyncio.run(self.bridge._proxy(request))
        self.assertEqual(result, {
            "response": {"id": 2},
            "response_headers": {"content-type": "application/json"},
            "error": None,
        })

    def test_proxy_returns_v2_error_without_breaking_fluidd_rpc(self):
        self.bridge._request = lambda *args: ({"message": "missing"}, {}, 404)
        request = FakeWebRequest({
            "request_method": "GET",
            "path": "/v1/spool/404",
            "use_v2_response": True,
        })
        result = asyncio.run(self.bridge._proxy(request))
        self.assertEqual(result["error"]["status_code"], 404)

    def test_active_spool_emits_native_fluidd_event(self):
        self.bridge.set_active_spool(17)
        self.assertEqual(
            self.config.server.events,
            [("spoolman:active_spool_set", {"spool_id": 17})],
        )

    def test_active_spool_persists_and_loads_from_moonraker_database(self):
        database = FakeDatabase()
        config = FakeConfig(database)
        bridge = self.module.SpoolmanBridge(config)
        asyncio.run(bridge.component_init())
        bridge.set_active_spool(23)

        self.assertEqual(database.values[("moonraker", "spoolman.spool_id")], 23)
        restored = self.module.SpoolmanBridge(config)
        asyncio.run(restored.component_init())
        self.assertEqual(restored.spool_id, 23)


if __name__ == "__main__":
    unittest.main()
