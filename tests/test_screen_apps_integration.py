import ast
import importlib.util
import pathlib
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
WEBCAM_SPEC = importlib.util.spec_from_file_location(
    "screen_apps_webcam_test", ROOT / "scripts" / "screen_apps" / "moonraker_webcam.py"
)
WEBCAM = importlib.util.module_from_spec(WEBCAM_SPEC)
WEBCAM_SPEC.loader.exec_module(WEBCAM)
FB_TREE = ast.parse((ROOT / "scripts" / "screen_apps" / "fb-http.py").read_text())
TOUCH_CLASS = next(node for node in FB_TREE.body if isinstance(node, ast.ClassDef) and node.name == "TouchInput")
SCALE_METHOD = next(node for node in TOUCH_CLASS.body if isinstance(node, ast.FunctionDef) and node.name == "_scale")
SCALE_MODULE = ast.Module(body=[SCALE_METHOD], type_ignores=[])
exec(compile(SCALE_MODULE, "fb-http.py", "exec"), globals())


class ScreenAppsIntegrationTests(unittest.TestCase):
    def test_fluidd_integration_uses_existing_iframe_camera_card(self):
        helper = (ROOT / "scripts" / "screen_apps" / "moonraker_webcam.py").read_text()
        self.assertIn('"service": "iframe"', helper)
        self.assertIn('"stream_url": SCREEN_URL', helper)
        self.assertIn('CAMERA_API + "/item"', helper)
        self.assertIn("Registered Screen Apps in Fluidd's built-in Camera card.", helper)
        compat = (ROOT / "scripts" / "fluidd_k3_compat.py").read_text()
        self.assertNotIn("SCREEN_APPS_SOURCE", compat)
        self.assertNotIn("install_screen_apps_display(destination)", compat)

    def test_camera_caption_style_is_scoped_and_allows_touch_through(self):
        installer = (ROOT / "scripts" / "screen_apps" / "install.sh").read_text()
        stylesheet = (ROOT / "scripts" / "screen_apps" / "fluidd-camera-caption.css").read_text()
        self.assertIn('fluidd-camera-caption.css" >> "$css_path"', installer)
        self.assertIn('iframe.camera-image[src*="/screen/"] + .camera-name', stylesheet)
        self.assertIn("display: none !important", stylesheet)
        self.assertIn("pointer-events: none !important", stylesheet)
        self.assertIn("remove_camera_caption_css", installer)

    def test_registration_uses_native_iframe_and_is_idempotent(self):
        calls = []
        webcams = []

        def request(url, payload=None, method=None):
            calls.append((url, payload, method))
            if url.endswith("/list"):
                return {"result": {"webcams": webcams}}
            if method == "POST":
                webcams.append({**payload, "source": "database"})
            return {}

        with patch.object(WEBCAM, "request_json", side_effect=request):
            WEBCAM.register()
            WEBCAM.register()

        payload = calls[1][1]
        self.assertEqual(payload["service"], "iframe")
        self.assertEqual(payload["stream_url"], "/screen/")
        self.assertEqual(payload["aspect_ratio"], "5:3")
        self.assertEqual(sum(1 for call in calls if call[2] == "POST"), 1)

    def test_registration_does_not_overwrite_conflicting_camera(self):
        existing = {
            "name": WEBCAM.CAMERA_NAME,
            "service": "webrtc-go2rtc",
            "stream_url": "http://camera/",
            "source": "database",
        }
        with patch.object(
            WEBCAM, "request_json", return_value={"result": {"webcams": [existing]}}
        ):
            with self.assertRaises(RuntimeError):
                WEBCAM.register()

    def test_unregister_deletes_only_matching_managed_iframe(self):
        entry = {
            "name": WEBCAM.CAMERA_NAME,
            "service": "iframe",
            "stream_url": WEBCAM.SCREEN_URL,
            "source": "database",
        }
        calls = []

        def request(url, payload=None, method=None):
            calls.append((url, payload, method))
            return {"result": {"webcams": [entry]}} if url.endswith("/list") else {}

        with patch.object(WEBCAM, "request_json", side_effect=request):
            WEBCAM.unregister()
        self.assertEqual(calls[1][2], "DELETE")
        self.assertIn("name=K3+Screen+Apps", calls[1][0])

    def test_screen_app_viewer_uses_relative_api_paths_for_proxy_mount(self):
        viewer = (ROOT / "scripts" / "screen_apps" / "html" / "index.html").read_text()
        self.assertIn("fetch('snapshot?ts='", viewer)
        self.assertIn("fetch('touch?a='", viewer)
        self.assertIn("pointerdown", viewer)
        self.assertIn("pointermove", viewer)
        self.assertIn("pointerup", viewer)
        self.assertIn("context.rotate(-Math.PI / 2)", viewer)

    def test_touch_transform_clamps_and_maps_calibrated_corners(self):
        self.assertEqual(_scale(None, 0, 0), (475, 8))
        self.assertEqual(_scale(None, 799, 0), (475, 777))
        self.assertEqual(_scale(None, 0, 479), (15, 8))
        self.assertEqual(_scale(None, 799, 479), (15, 777))
        self.assertEqual(_scale(None, -100, 900), (15, 8))


if __name__ == "__main__":
    unittest.main()
