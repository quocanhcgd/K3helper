import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "chamber_light_config.py"
SPEC = importlib.util.spec_from_file_location("chamber_light_config_test", MODULE_PATH)
CONFIG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONFIG)


class ChamberLightConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.printer_cfg = self.root / "printer.cfg"
        self.printer_cfg.write_text("[include base.cfg]\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_install_adds_on_off_macros_and_is_idempotent(self):
        objects = {"output_pin chamber_led"}

        self.assertTrue(CONFIG.manage_config(self.printer_cfg, "install", objects))
        self.assertFalse(CONFIG.manage_config(self.printer_cfg, "install", objects))

        content = self.printer_cfg.read_text(encoding="utf-8")
        macro = (self.root / "chamber_light.cfg").read_text(encoding="utf-8")
        self.assertEqual(content.count(CONFIG.INCLUDE_LINE), 1)
        self.assertIn("[gcode_macro CHAMBER_LED_ON]", macro)
        self.assertIn("SET_PIN PIN=chamber_led VALUE=1", macro)
        self.assertIn("[gcode_macro CHAMBER_LED_OFF]", macro)
        self.assertIn("SET_PIN PIN=chamber_led VALUE=0", macro)
        self.assertNotIn("[output_pin chamber_led]", macro)
        self.assertTrue(self.printer_cfg.with_name("printer.cfg.k3helper-chamber-light.bak").is_file())

    def test_install_includes_pin_when_not_already_configured(self):
        CONFIG.manage_config(self.printer_cfg, "install", set())
        macro = (self.root / "chamber_light.cfg").read_text(encoding="utf-8")

        self.assertIn("[output_pin chamber_led]", macro)
        self.assertIn("pin: rpi:gpio42", macro)
        self.assertIn("shutdown_value: 0", macro)

    def test_include_is_inserted_before_klipper_save_config_block(self):
        self.printer_cfg.write_text(
            "[include base.cfg]\n\n#*# <---------------------- SAVE_CONFIG ---------------------->\n"
            "#*# [probe]\n#*# z_offset = 0.0\n",
            encoding="utf-8",
        )
        CONFIG.manage_config(self.printer_cfg, "install", {"output_pin chamber_led"})
        content = self.printer_cfg.read_text(encoding="utf-8")

        self.assertLess(content.index(CONFIG.INCLUDE_LINE), content.index("SAVE_CONFIG"))

    def test_remove_deletes_only_managed_macro_and_include(self):
        CONFIG.manage_config(self.printer_cfg, "install", {"output_pin chamber_led"})

        self.assertTrue(CONFIG.manage_config(self.printer_cfg, "remove"))
        self.assertFalse(CONFIG.manage_config(self.printer_cfg, "remove"))

        self.assertEqual(self.printer_cfg.read_text(encoding="utf-8"), "[include base.cfg]\n")
        self.assertFalse((self.root / "chamber_light.cfg").exists())


if __name__ == "__main__":
    unittest.main()
