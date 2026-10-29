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
        objects = set()

        self.assertTrue(CONFIG.manage_config(self.printer_cfg, "install", objects))
        self.assertFalse(CONFIG.manage_config(self.printer_cfg, "install", objects))

        content = self.printer_cfg.read_text(encoding="utf-8")
        macro = (self.root / "chamber_light.cfg").read_text(encoding="utf-8")
        self.assertEqual(content.count(CONFIG.INCLUDE_LINE), 1)
        self.assertIn("[gcode_macro CHAMBER_LED_ON]", macro)
        self.assertIn('action_call_remote_method("k3helper_chamber_light", state=1)', macro)
        self.assertIn("[gcode_macro CHAMBER_LED_OFF]", macro)
        self.assertIn('action_call_remote_method("k3helper_chamber_light", state=0)', macro)
        self.assertNotIn("[output_pin", macro)
        self.assertTrue(self.printer_cfg.with_name("printer.cfg.k3helper-chamber-light.bak").is_file())

    def test_install_does_not_claim_a_gpio_pin(self):
        CONFIG.manage_config(self.printer_cfg, "install", set())
        macro = (self.root / "chamber_light.cfg").read_text(encoding="utf-8")

        self.assertNotIn("[output_pin", macro)
        self.assertNotIn("SET_PIN", macro)

    def test_include_is_inserted_before_klipper_save_config_block(self):
        self.printer_cfg.write_text(
            "[include base.cfg]\n\n#*# <---------------------- SAVE_CONFIG ---------------------->\n"
            "#*# [probe]\n#*# z_offset = 0.0\n",
            encoding="utf-8",
        )
        CONFIG.manage_config(self.printer_cfg, "install", set())
        content = self.printer_cfg.read_text(encoding="utf-8")

        self.assertLess(content.index(CONFIG.INCLUDE_LINE), content.index("SAVE_CONFIG"))

    def test_remove_deletes_only_managed_macro_and_include(self):
        CONFIG.manage_config(self.printer_cfg, "install", set())

        self.assertTrue(CONFIG.manage_config(self.printer_cfg, "remove"))
        self.assertFalse(CONFIG.manage_config(self.printer_cfg, "remove"))

        self.assertEqual(self.printer_cfg.read_text(encoding="utf-8"), "[include base.cfg]\n")
        self.assertFalse((self.root / "chamber_light.cfg").exists())

    def test_rejects_pin_names_that_conflict_with_stock_light_control(self):
        original = self.printer_cfg.read_text(encoding="utf-8")

        for object_name in ("output_pin nozzle_light", "output_pin chamber_led"):
            with self.subTest(object_name=object_name):
                with self.assertRaisesRegex(RuntimeError, "conflicts with the Creality WebSocket"):
                    CONFIG.manage_config(self.printer_cfg, "install", {object_name})

        self.assertEqual(self.printer_cfg.read_text(encoding="utf-8"), original)
        self.assertFalse((self.root / "chamber_light.cfg").exists())

    def test_remove_recognizes_legacy_helper_macro(self):
        self.printer_cfg.write_text(
            "[include base.cfg]\n" + CONFIG.INCLUDE_MARKER + "\n" + CONFIG.INCLUDE_LINE + "\n",
            encoding="utf-8",
        )
        (self.root / "chamber_light.cfg").write_text(
            CONFIG.LEGACY_MACRO_MARKERS[0] + "\n[gcode_macro CHAMBER_LED_ON]\n",
            encoding="utf-8",
        )

        self.assertTrue(CONFIG.manage_config(self.printer_cfg, "remove"))
        self.assertFalse((self.root / "chamber_light.cfg").exists())

    def test_upgrade_replaces_managed_pin_macro_with_websocket_macro(self):
        self.printer_cfg.write_text(
            "[include base.cfg]\n" + CONFIG.INCLUDE_MARKER + "\n" + CONFIG.INCLUDE_LINE + "\n",
            encoding="utf-8",
        )
        (self.root / "chamber_light.cfg").write_text(
            "# K3HELPER_CHAMBER_LIGHT_V2\n[output_pin nozzle_light]\npin: rpi:gpio42\n",
            encoding="utf-8",
        )

        self.assertTrue(CONFIG.manage_config(self.printer_cfg, "install", {"output_pin nozzle_light"}))
        macro = (self.root / "chamber_light.cfg").read_text(encoding="utf-8")
        self.assertIn(CONFIG.MACRO_MARKER, macro)
        self.assertIn("action_call_remote_method", macro)
        self.assertNotIn("[output_pin nozzle_light]", macro)


if __name__ == "__main__":
    unittest.main()
