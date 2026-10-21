"""Explicit composition only. No production mounting or default provider."""

from fastapi import APIRouter, Header, HTTPException, Response, WebSocket
from pydantic import BaseModel, ConfigDict, Field

from backend.routes.application_extensions import ApplicationUiBinding
from backend.services.application_authority_management import AuthorityManagementError
from three_mm_protocol.interactive_session import SessionOpenRequestV1


class BrowserSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    ui_context: ApplicationUiBinding
    binding_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")
    request: SessionOpenRequestV1


def application_session_router(service):
    router = APIRouter(prefix="/api/v1/application-extensions")

    @router.get("/{module_id}/session-host/{entrypoint_id}")
    def targets(
        module_id: str,
        entrypoint_id: str,
        artifact_sha256: str,
        built_ui_sha256: str,
        response: Response,
        authorization: str | None = Header(default=None),
    ):
        response.headers["Cache-Control"] = "no-store"
        try:
            binding = ApplicationUiBinding(
                host_version=1,
                entrypoint_id=entrypoint_id,
                artifact_sha256=artifact_sha256,
                built_ui_sha256=built_ui_sha256,
            )
            return service.targets(module_id, binding, authorization)
        except HTTPException:
            raise
        except (ValueError, AuthorityManagementError, OSError):
            raise HTTPException(403, "Current session access is unavailable") from None

    @router.post("/{module_id}/session-host/{entrypoint_id}/ticket")
    def ticket(
        module_id: str,
        entrypoint_id: str,
        body: BrowserSessionRequest,
        response: Response,
        authorization: str | None = Header(default=None),
    ):
        response.headers["Cache-Control"] = "no-store"
        if (
            body.ui_context.entrypoint_id != entrypoint_id
            or body.ui_context.built_ui_sha256 is None
        ):
            raise HTTPException(403, "Session UI binding is unavailable")
        try:
            return service.issue(
                module_id, body.ui_context, authorization, body.binding_id, body.request
            )
        except HTTPException:
            raise
        except (ValueError, AuthorityManagementError, OSError, StopIteration):
            raise HTTPException(403, "Current session access is unavailable") from None

    @router.websocket("/{module_id}/session-host/{entrypoint_id}/ws")
    async def stream(websocket: WebSocket, module_id: str, entrypoint_id: str):
        await service.serve(websocket, module_id, entrypoint_id)

    return router
