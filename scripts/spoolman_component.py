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
import urllib.request
from typing import Any, Dict, Optional

try:
    from moonraker.common import RequestType
except ImportError:
    # Creality's trimmed Moonraker has no common.py and uses method-name lists.
    RequestType = None


class SpoolmanBridge:
    def __init__(self, config):
        self.server = config.get_server()
        raw_url = str(config.get("server")).rstrip("/")
        if not raw_url.startswith(("http://", "https://")):
            raw_url = "http://" + raw_url
        self.api_url = raw_url + "/api"
        self.spool_id: Optional[int] = None
        self._connected = False
        self.database = None
        self._status_notification = "spoolman:spoolman_status_changed"
        self._active_spool_notification = "spoolman:active_spool_set"
        register_notification = getattr(self.server, "register_notification", None)
        if register_notification is not None:
            register_notification(self._status_notification)
            register_notification(self._active_spool_notification)
        self._register_endpoints()
        register_remote = getattr(self.server, "register_remote_method", None)
        if register_remote is not None:
            register_remote("spoolman_set_active_spool", self.set_active_spool)

    def _register_endpoints(self):
        self.server.register_endpoint(
            "/server/spoolman/status", ["GET"], self._status
        )
        self.server.register_endpoint(
            "/server/spoolman/spool_id",
            ["GET", "POST"],
            self._spool_id,
        )
        self.server.register_endpoint(
            "/server/spoolman/proxy", ["POST"], self._proxy
        )

    async def component_init(self):
        try:
            self.database = self.server.lookup_component("database")
            self.spool_id = await self.database.get_item(
                "moonraker", "spoolman.spool_id", None
            )
        except Exception:
            self.database = None

    async def close(self):
        return None

    def set_active_spool(self, spool_id=None):
        if spool_id == self.spool_id:
            return
        if spool_id is None:
            self.spool_id = None
        else:
            self.spool_id = int(spool_id)
        if self.database is not None:
            self.database.insert_item("moonraker", "spoolman.spool_id", self.spool_id)
        send_event = getattr(self.server, "send_event", None)
        if send_event is not None:
            send_event(self._active_spool_notification, {"spool_id": self.spool_id})

    async def _spool_id(self, web_request):
        request_type = getattr(web_request, "get_request_type", None)
        if request_type is not None:
            is_post = request_type() == RequestType.POST
        else:
            args = getattr(web_request, "get_args", lambda: getattr(web_request, "args", {}))()
            is_post = "spool_id" in args
        if is_post:
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
        try:
            response = urllib.request.urlopen(request, timeout=8)
        except urllib.error.HTTPError as error:
            return self._decode_response(error.read()), dict(error.headers.items()), error.code
        with response:
            return self._decode_response(response.read()), dict(response.headers.items()), response.status

    @staticmethod
    def _decode_response(raw: bytes):
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    def _set_connected(self, connected: bool):
        if self._connected == connected:
            return
        self._connected = connected
        send_event = getattr(self.server, "send_event", None)
        if send_event is not None:
            send_event(
                self._status_notification,
                {"spoolman_connected": connected},
            )

    async def _proxy(self, web_request):
        method = web_request.get_str("request_method")
        path = web_request.get_str("path")
        query = web_request.get_str("query", None)
        body = web_request.get("body", None)
        use_v2_response = web_request.get_boolean("use_v2_response", False)
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise self.server.error("Invalid HTTP method: %s" % method)
        if body is not None and method == "GET":
            raise self.server.error("GET requests cannot have a body")
        loop = asyncio.get_event_loop()
        try:
            response, headers, status = await loop.run_in_executor(
                None, self._request, method, path, query, body
            )
            self._set_connected(True)
            if use_v2_response:
                if status >= 400:
                    return {
                        "response": None,
                        "error": {
                            "status_code": status,
                            "message": "Spoolman returned HTTP %s" % status,
                        },
                    }
                return {"response": response, "response_headers": headers, "error": None}
            if status >= 400:
                raise self.server.error("Spoolman returned HTTP %s" % status, status)
            return response
        except Exception as error:
            self._set_connected(False)
            if use_v2_response:
                return {"response": None, "error": {"status_code": 503, "message": str(error)}}
            if hasattr(error, "status_code"):
                raise
            raise self.server.error("Spoolman request failed: %s" % error, 503)

    async def _status(self, _web_request) -> Dict[str, Any]:
        loop = asyncio.get_event_loop()
        try:
            _, _, status = await loop.run_in_executor(
                None, self._request, "GET", "/v1/info", None, None
            )
            self._set_connected(200 <= status < 300)
        except Exception:
            self._set_connected(False)
        return {
            "spoolman_connected": self._connected,
            "pending_reports": [],
            "spool_id": self.spool_id,
        }


def load_component(config):
    return SpoolmanBridge(config)
