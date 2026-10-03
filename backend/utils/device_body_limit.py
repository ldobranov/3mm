"""Bound common device HTTP messages before FastAPI parses or persists them."""

import json
import re

from starlette.responses import JSONResponse
from three_mm_protocol.node_security import (
    MODULE_COMMAND_BYTES,
    NODE_MESSAGE_BYTES,
    validate_node_json,
)


class DeviceBodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        protected = (
            path.startswith("/api/v1/devices/") or path == "/api/v1/pairing/enroll"
        )
        if (
            scope["type"] != "http"
            or not protected
            or scope["method"] not in {"POST", "PUT", "PATCH"}
        ):
            return await self.app(scope, receive, send)
        limit = (
            MODULE_COMMAND_BYTES
            if re.fullmatch(r"/api/v1/devices/dev_[0-9a-f]{32}/commands", path)
            else NODE_MESSAGE_BYTES
        )
        headers = dict(scope.get("headers", ()))
        try:
            length = int(headers.get(b"content-length", b"0"))
            if length < 0:
                raise ValueError
        except ValueError:
            return await JSONResponse(
                {"detail": "Invalid body length"}, status_code=400
            )(scope, receive, send)
        if length > limit:
            return await JSONResponse(
                {"detail": "Device body limit exceeded"}, status_code=413
            )(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > limit:
                return await JSONResponse(
                    {"detail": "Device body limit exceeded"}, status_code=413
                )(scope, receive, send)
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        if body:
            try:

                def reject_constant(_):
                    raise ValueError("Non-finite JSON")

                parsed = json.loads(body, parse_constant=reject_constant)
                validate_node_json(parsed, max_bytes=limit)
            except (ValueError, RecursionError, UnicodeError):
                return await JSONResponse(
                    {"detail": "Invalid or excessive device JSON"}, status_code=400
                )(scope, receive, send)
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        return await self.app(scope, bounded_receive, send)
