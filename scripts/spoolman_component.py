#!/usr/bin/env python3
"""Small Spoolman bridge for the trimmed Moonraker shipped with Creality K3.

It intentionally uses only the old Moonraker endpoint/config APIs.  This keeps
Fluidd's spool browser usable when the firmware does not ship the upstream
moonraker.components.spoolman module.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from moonraker.common import RequestType


class SpoolmanBridge:
    def __init__(self, config):
        self.server = config.get_server()
        raw_url = str(config.get("server")).rstrip("/")
        if not raw_url.startswith(("http://", "https://")):
            raw_url = "http://" + raw_url
        self.api_url = raw_url + "/api"
        self.spool_id: Optional[int] = None
        self._register_endpoints()
        register_remote = getattr(self.server, "register_remote_method", None)
        if register_remote is not None:
            register_remote("spoolman_set_active_spool", self.set_active_spool)

    def _register_endpoints(self):
        self.server.register_endpoint(
            "/server/spoolman/status", RequestType.GET, self._status
        )
        self.server.register_endpoint(
            "/server/spoolman/spool_id",
            RequestType.GET | RequestType.POST,
            self._spool_id,
        )
        self.server.register_endpoint(
            "/server/spoolman/proxy",
            RequestType.GET | RequestType.POST,
            self._proxy,
        )

    async def component_init(self):
        return None

    async def close(self):
        return None

    def set_active_spool(self, spool_id=None):
        if spool_id is None:
            self.spool_id = None
        else:
            self.spool_id = int(spool_id)

    async def _spool_id(self, web_request):
        if web_request.get_request_type() == RequestType.POST:
            self.set_active_spool(web_request.get_int("spool_id", None))
        return {"spool_id": self.spool_id}

    def _request(self, method: str, path: str, query: Optional[str], body: Any):
        if not path.startswith("/v1/"):
            raise ValueError("Spoolman path must start with /v1/")
        target = self.api_url + path
        if query:
            target += "?" + query
        payload = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            target,
            data=payload,
            method=method,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            raw = response.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))

    async def _proxy(self, web_request):
        method = web_request.get_str("request_method")
        path = web_request.get_str("path")
        query = web_request.get_str("query", None)
        body = web_request.get("body", None)
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise ValueError("Unsupported Spoolman HTTP method")
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(
                None, self._request, method, path, query, body
            )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise self.server.error("Spoolman request failed: %s" % error, 503)

    async def _status(self, _web_request) -> Dict[str, Any]:
        loop = asyncio.get_event_loop()
        connected = False
        try:
            await loop.run_in_executor(None, self._request, "GET", "/v1/info", None, None)
            connected = True
        except Exception:
            pass
        return {
            "spoolman_connected": connected,
            "pending_reports": [],
            "spool_id": self.spool_id,
        }


def load_component(config):
    return SpoolmanBridge(config)
