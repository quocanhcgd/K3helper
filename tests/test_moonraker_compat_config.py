import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "moonraker_compat_config.py"
SPEC = importlib.util.spec_from_file_location("moonraker_compat_config_test", MODULE_PATH)
CONFIG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONFIG)


class MoonrakerCompatConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "moonraker.conf"
        self.path.write_text("[server]\nhost: 0.0.0.0\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_install_is_idempotent_and_remove_preserves_other_sections(self):
        CONFIG.update_config(self.path, "install")
        first = self.path.read_text(encoding="utf-8")
        CONFIG.update_config(self.path, "install")
        self.assertEqual(self.path.read_text(encoding="utf-8"), first)
        self.assertIn("[k3helper_compat]", first)

        CONFIG.update_config(self.path, "remove")
        self.assertEqual(self.path.read_text(encoding="utf-8"), "[server]\nhost: 0.0.0.0\n")

    def test_refuses_to_replace_unmanaged_section(self):
        self.path.write_text("[k3helper_compat]\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unmanaged"):
            CONFIG.update_config(self.path, "install")


if __name__ == "__main__":
    unittest.main()
