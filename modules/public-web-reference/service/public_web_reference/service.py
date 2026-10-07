"""Neutral public-web reference application used for platform acceptance."""

from __future__ import annotations

from html import escape

from three_mm_application_sdk import ApplicationContext, OperationContext


class PublicWebReferenceService:
    def __init__(self, application: ApplicationContext) -> None:
        self.application = application

    def handle(self, operation_id: str, payload: dict, context: OperationContext):
        if operation_id == "health":
            return {"status": "ready"}
        if operation_id != "render_public" or context.audience != "public":
            raise ValueError("Operation is unsupported")
        return self._render(payload)

    @staticmethod
    def _render(payload: dict):
        path = str(payload["path"])
        params = payload.get("path_params")
        if not isinstance(params, dict):
            raise ValueError("Public request parameters are invalid")

        if path == "/":
            return {
                "status": 200,
                "content_type": "text/html; charset=utf-8",
                "headers": {"Cache-Control": "public, max-age=60"},
                "body": (
                    "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
                    "<title>Public Web Reference</title></head>"
                    "<body><h1>Public Web Reference</h1></body></html>"
                ),
            }
        if path.startswith("/items/") and isinstance(params.get("slug"), str):
            slug = escape(params["slug"])
            return {
                "status": 200,
                "content_type": "text/html; charset=utf-8",
                "headers": {},
                "body": (
                    "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
                    f"<title>Reference item {slug}</title></head>"
                    f"<body><h1>{slug}</h1></body></html>"
                ),
            }
        if path == "/feed.xml":
            return {
                "status": 200,
                "content_type": "application/xml",
                "headers": {"Cache-Control": "public, max-age=60"},
                "body": "<?xml version=\"1.0\" encoding=\"UTF-8\"?><feed><title>Reference</title></feed>",
            }
        if path == "/info.txt":
            return {
                "status": 200,
                "content_type": "text/plain; charset=utf-8",
                "headers": {},
                "body": "Public Web Reference\n",
            }
        if path == "/old-item":
            return {"status": 301, "headers": {}, "location": "/items/example"}
        if path == "/gone":
            return {
                "status": 410,
                "content_type": "text/plain; charset=utf-8",
                "headers": {"Cache-Control": "no-store"},
                "body": "Gone\n",
            }
        raise ValueError("Declared public route is unsupported")


def create_service(application: ApplicationContext):
    return PublicWebReferenceService(application)
