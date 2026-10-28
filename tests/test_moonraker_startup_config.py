import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "moonraker_startup_config.py"
SPEC = importlib.util.spec_from_file_location("moonraker_startup_config_test", MODULE_PATH)
STARTUP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STARTUP)


class MoonrakerStartupConfigTests(unittest.TestCase):
    def test_patch_is_idempotent_when_config_path_is_already_active(self):
        with tempfile.TemporaryDirectory() as directory:
            service = pathlib.Path(directory) / "moonraker"
            service.write_text(
                "#!/bin/sh\n"
                "CONF=/mnt/SDCARD/cxsw/printer_data/config/moonraker.conf\n"
                "PROG=/usr/share/moonraker/moonraker.py\n"
                "procd_open_instance\n"
                "procd_set_param command /usr/bin/env PYTHONPATH=/mnt/UDISK/helper-script/scripts ${PROG} -c ${CONF}\n",
                encoding="utf-8",
            )

            result = STARTUP.patch(
                "/mnt/SDCARD/cxsw/printer_data/config/moonraker.conf",
                candidates=[str(service)],
            )

            self.assertEqual(result, str(service))
            self.assertIn("PYTHONPATH=/mnt/UDISK/helper-script/scripts", service.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
