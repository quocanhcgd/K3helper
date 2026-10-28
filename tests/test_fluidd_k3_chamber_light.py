import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "fluidd_k3_compat.py"
SPEC = importlib.util.spec_from_file_location("fluidd_k3_compat_test", MODULE_PATH)
COMPAT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPAT)


class FluiddK3ChamberLightRemovalTests(unittest.TestCase):
    def test_removes_retired_card_script_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            index = root / "index.html"
            index.write_text(
                '<html><head><script id="creality-chamber-light-script" '
                'defer src="/creality-chamber-light.js?v=1"></script>'
                "</head><body></body></html>",
                encoding="utf-8",
            )
            script = root / "creality-chamber-light.js"
            script.write_text("retired card code", encoding="utf-8")

            COMPAT.remove_chamber_light_display(root)
            cleaned_html = index.read_text(encoding="utf-8")
            COMPAT.remove_chamber_light_display(root)

            self.assertNotIn("creality-chamber-light-script", cleaned_html)
            self.assertNotIn("creality-chamber-light.js", cleaned_html)
            self.assertFalse(script.exists())
            self.assertEqual(index.read_text(encoding="utf-8"), cleaned_html)


if __name__ == "__main__":
    unittest.main()
