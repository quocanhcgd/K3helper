import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "k3_boot_recovery.py"
SPEC = importlib.util.spec_from_file_location("k3_boot_recovery_test", MODULE_PATH)
RECOVERY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECOVERY)


class K3BootRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def rooted(self, path):
        return self.root / str(path).lstrip("/\\")

    def test_restores_only_missing_config_from_moonraker_backup(self):
        init = self.rooted(RECOVERY.MOONRAKER_INIT)
        init.parent.mkdir(parents=True)
        init.write_text("CONF=/mnt/SDCARD/cxsw/printer_data/config/moonraker.conf\n")
        backup = self.rooted("/mnt/SDCARD/cxsw/printer_data/config/.moonraker.conf.bkp")
        backup.parent.mkdir(parents=True)
        backup.write_text("[server]\nhost = 0.0.0.0\n[spoolman]\nserver = http://spoolman\n")

        config, restored = RECOVERY.restore_missing_moonraker_config(self.root)

        target = self.rooted(config)
        self.assertTrue(restored)
        self.assertEqual(target.read_text(), backup.read_text())
        RECOVERY.ensure_comms_directory(self.root, config)
        self.assertTrue(self.rooted("/mnt/SDCARD/cxsw/printer_data/comms").is_dir())

        target.write_text("user-edited\n")
        _, restored_again = RECOVERY.restore_missing_moonraker_config(self.root)
        self.assertFalse(restored_again)
        self.assertEqual(target.read_text(), "user-edited\n")

    def test_syncs_fluidd_firmware_version_from_current_firmware(self):
        source = self.rooted(RECOVERY.VERSION_SOURCE)
        source.parent.mkdir(parents=True)
        source.write_text(json.dumps({"sys_version": "4.0.3.2.10"}))

        self.assertTrue(RECOVERY.sync_firmware_version(self.root))
        target = self.rooted(RECOVERY.FLUIDD_ROOT / "creality-firmware-version.json")
        self.assertEqual(json.loads(target.read_text())["sys_version"], "4.0.3.2.10")
        self.assertFalse(RECOVERY.sync_firmware_version(self.root))

    def test_installs_a_late_boot_service_that_waits_for_udisk(self):
        self.assertTrue(RECOVERY.write_service(self.root))
        service = self.rooted(RECOVERY.SERVICE_PATH)
        content = service.read_text()
        self.assertIn("START=99", content)
        self.assertIn("/mnt/UDISK", content)
        self.assertIn("k3_boot_recovery.py run", content)
        if RECOVERY.os.name != "nt":
            self.assertTrue(service.stat().st_mode & 0o111)
        self.assertFalse(RECOVERY.write_service(self.root))

    def test_recovery_starts_only_integrations_marked_installed(self):
        installed = self.rooted(RECOVERY.INSTALLED_FILE)
        installed.parent.mkdir(parents=True)
        installed.write_text("camera_support_k3\nk3_firmware_api\nk3_screen_apps\n")
        for name in ("go2rtc-k3", "k3-firmware-api", "k3-screen-apps"):
            init = self.rooted(pathlib.Path("/etc/init.d") / name)
            init.parent.mkdir(parents=True, exist_ok=True)
            init.write_text("#!/bin/sh\n")
        with patch.object(RECOVERY, "_http_ready", return_value=False), patch.object(
            RECOVERY.subprocess, "run"
        ) as run:
            RECOVERY.recover(self.root, wait=False)

        started = [call.args[0][0] for call in run.call_args_list]
        self.assertEqual(
            started,
            [
                str(self.rooted("/etc/init.d/go2rtc-k3")),
                str(self.rooted("/etc/init.d/k3-firmware-api")),
                str(self.rooted("/etc/init.d/k3-screen-apps")),
            ],
        )

    def test_repairs_led_include_when_feature_is_installed(self):
        installed = self.rooted(RECOVERY.INSTALLED_FILE)
        installed.parent.mkdir(parents=True)
        installed.write_text("chamber_light\n")
        script = self.rooted(RECOVERY.INSTALL_ROOT / "scripts/chamber_light_config.py")
        script.parent.mkdir(parents=True)
        script.write_text("# helper\n")
        config = self.rooted("/mnt/SDCARD/cxsw/printer_data/config/printer.cfg")
        config.parent.mkdir(parents=True)
        config.write_text("[printer]\n")
        init = self.rooted("/etc/init.d/klipper")
        init.parent.mkdir(parents=True)
        init.write_text("#!/bin/sh\n")
        with patch.object(RECOVERY.subprocess, "run") as run:
            run.return_value.returncode = 0
            self.assertTrue(RECOVERY.repair_chamber_light(self.root))
        self.assertEqual(run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
