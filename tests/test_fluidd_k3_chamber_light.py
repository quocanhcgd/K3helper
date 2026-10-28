import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "fluidd_k3_compat.py"
SPEC = importlib.util.spec_from_file_location("fluidd_k3_compat_test", MODULE_PATH)
COMPAT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPAT)


class FluiddK3ChamberLightTests(unittest.TestCase):
    def test_install_is_idempotent_and_injects_websocket_control(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            index = root / "index.html"
            index.write_text("<html><body><main></main></body></html>", encoding="utf-8")

            COMPAT.install_chamber_light_display(root)
            first_html = index.read_text(encoding="utf-8")
            COMPAT.install_chamber_light_display(root)
            second_html = index.read_text(encoding="utf-8")
            script = (root / COMPAT.CHAMBER_LIGHT_SCRIPT).read_text(encoding="utf-8")

            self.assertEqual(first_html, second_html)
            self.assertEqual(first_html.count(f'id="{COMPAT.CHAMBER_LIGHT_ID}"'), 1)
            self.assertIn('new WebSocket(`${scheme}//${window.location.hostname}:9999/`)', script)
            self.assertIn('JSON.stringify({ method: "set", params: { lightSw: value } })', script)
            self.assertIn("panel.nextElementSibling !== macros", script)
            self.assertNotIn('toggle.type = "checkbox"', script)


if __name__ == "__main__":
    unittest.main()
