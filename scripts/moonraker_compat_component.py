#!/usr/bin/env python3
"""Compatibility endpoints for optional Fluidd calls missing on K3 Moonraker."""


class K3MoonrakerCompat:
    def __init__(self, config):
        self.server = config.get_server()
        self.server.register_endpoint(
            "/machine/peripherals/usb", ["GET"], self._usb
        )
        self.server.register_endpoint(
            "/machine/peripherals/serial", ["GET"], self._serial
        )
        self.server.register_endpoint(
            "/machine/peripherals/video", ["GET"], self._video
        )
        self.server.register_endpoint(
            "/machine/peripherals/canbus", ["GET"], self._canbus
        )
        self.server.register_endpoint(
            "/server/files/metascan", ["GET"], self._metascan
        )

    async def _usb(self, _request):
        return {"usb_devices": []}

    async def _serial(self, _request):
        return {"serial_devices": []}

    async def _video(self, _request):
        return {"v4l2_devices": [], "libcamera_devices": []}

    async def _canbus(self, _request):
        return {"can_uuids": []}

    async def _metascan(self, request):
        """Return cached metadata without failing when K3 cannot rescan it."""
        filename = request.get_str("filename", "")
        metadata = {}
        try:
            file_manager = self.server.lookup_component("file_manager")
            metadata = file_manager.get_file_metadata(filename) or {}
        except Exception:
            metadata = {}
        result = dict(metadata)
        result["filename"] = filename
        return result


def load_component(config):
    return K3MoonrakerCompat(config)
