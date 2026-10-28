import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "spoolman_config.py"
SPEC = importlib.util.spec_from_file_location("spoolman_config_test", MODULE_PATH)
CONFIG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONFIG)


class SpoolmanConfigTests(unittest.TestCase):
    def test_set_replaces_old_section_without_unsupported_sync_rate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "moonraker.conf"
            path.write_text(
                "[server]\nhost: 0.0.0.0\n\n[spoolman]\n"
                "server: http://old:7912\nsync_rate: 5\n",
                encoding="utf-8",
            )

            CONFIG.update_config(str(path), "set", "http://new:7912")
            content = path.read_text(encoding="utf-8")

            self.assertIn("[server]\nhost: 0.0.0.0", content)
            self.assertIn("[spoolman]\nserver: http://new:7912\n", content)
            self.assertNotIn("sync_rate", content)


if __name__ == "__main__":
    unittest.main()
