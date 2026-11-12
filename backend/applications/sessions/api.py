"""Explicit composition only. No production mounting or default provider."""

from fastapi import APIRouter, Header, HTTPException, Response, WebSocket
from pydantic import BaseModel, ConfigDict, Field

from backend.applications.management.api import ApplicationUiBinding
from backend.applications.authority.management import AuthorityManagementError
from packages.protocol.interactive_session import SessionOpenRequestV1
from backend.system.diagnostics.operations import operation_step
from backend.system.diagnostics.failures import note_dispatch, note_failure


class BrowserSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    ui_context: ApplicationUiBinding
    binding_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")
    request: SessionOpenRequestV1


def application_session_router(service):
    router = APIRouter(prefix="/api/v1/application-extensions")

    @router.get("/{module_id}/session-recovery")
    def recovery_status(module_id: str, response: Response,
                        authorization: str | None = Header(default=None)):
        response.headers["Cache-Control"] = "no-store"
        return service.recovery_status(module_id, authorization)

    @router.post("/{module_id}/session-recovery/{session_id}/confirm-cleanup")
    async def reconcile(module_id: str, session_id: str, response: Response,
                        authorization: str | None = Header(default=None)):
        response.headers["Cache-Control"] = "no-store"
        return await service.confirm_cleanup(module_id, session_id, authorization)

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
            note_dispatch('not_dispatched')
            with operation_step('session.targets', operation='session.targets'):
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
        note_dispatch('not_dispatched')  # Ticket issuance does not start an executor.
        if (
            body.ui_context.entrypoint_id != entrypoint_id
            or body.ui_context.built_ui_sha256 is None
        ):
            note_failure('session.ui', 'ui_code_unavailable')
            raise HTTPException(403, "Session UI binding is unavailable")
        try:
            with operation_step('session.ticket', operation='session.ticket'):
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
