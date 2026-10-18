"""Experimental M21 HTTP + WebSocket adapter; NOT mounted by production Core.

Tests explicitly construct an isolated app with this router. M21/WP4 current
human/device/resource authority and isolation are incomplete; neither this
module nor its reference providers may be enabled by the release composition.

The HTTP route issues a one-time, short-lived ticket bound to the authenticated
user (existing JWT via ``require_user``). The WebSocket route redeems exactly one
ticket at connect time and then serves the session gateway. The JWT is never
placed in the WebSocket URL and a bare ``session_id`` grants nothing.

This adapter performs no OS isolation and starts no process; provider native
review through M20 is still pending. A future live uvicorn needs a WebSocket
implementation (``uvicorn[standard]`` / ``websockets``); the Starlette
``TestClient`` exercises the endpoint without that dependency.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.services.interactive_session_agent import (
    AgentSessionTransport,
    get_device_tickets,
)
from backend.services.interactive_session_discovery import build_session_discovery
from backend.services.interactive_session_gateway import (
    SessionGatewayError,
    get_session_gateway,
)
from backend.services.interactive_session_transport import (
    RemoteDeviceSession,
    RemoteSessionError,
)
from backend.utils.auth_dep import require_admin, require_user
from backend.utils.db_utils import get_db
from backend.utils.device_auth import require_device
from three_mm_protocol.interactive_session import SessionDiscoveryV1

router = APIRouter(tags=["interactive-sessions"])

WS_CLOSE_UNAUTHORIZED = 4401
WS_CLOSE_GATEWAY_ERROR = 4400


class SessionTicketResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket: str
    expires_at: str


@router.post(
    "/api/v1/interactive-sessions/ticket", response_model=SessionTicketResponse
)
def issue_interactive_session_ticket(
    claims: dict = Depends(require_user),
) -> SessionTicketResponse:
    """Issue a single-use ticket bridging the JWT login to a WebSocket."""
    try:
        user_id = int(claims.get("sub") or claims.get("user_id"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid user subject") from exc
    issue = get_session_gateway().issue_ticket(user_id)
    return SessionTicketResponse(
        ticket=issue.ticket, expires_at=issue.expires_at.isoformat()
    )


@router.get(
    "/api/v1/interactive-sessions/discovery", response_model=SessionDiscoveryV1
)
def list_interactive_session_targets(
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
) -> SessionDiscoveryV1:
    """List devices that offer session capabilities, with availability.

    Read-only over the real capability registry; no grants and no user-scoped
    visibility (that remains M20/WP4 work).
    """
    gateway = get_session_gateway()
    return build_session_discovery(
        db, session_capability_ids=gateway.manager.session_capability_ids
    )


@router.websocket("/api/v1/interactive-sessions/ws")
async def interactive_session_ws(websocket: WebSocket) -> None:
    """Redeem one ticket, then serve control/data frames for the session."""
    gateway = get_session_gateway()
    ticket = websocket.query_params.get("ticket")
    await websocket.accept()
    try:
        user_id = gateway.redeem(ticket or "")
    except Exception:  # noqa: BLE001 - any redemption failure is unauthorized
        await websocket.close(code=WS_CLOSE_UNAUTHORIZED)
        return
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message.get("text") is not None:
                try:
                    response = await gateway.handle_text(user_id, message["text"])
                except SessionGatewayError as exc:
                    await websocket.send_text(
                        f'{{"op":"error","detail":{_json_detail(str(exc))}}}'
                    )
                    continue
                await websocket.send_text(response)
            elif message.get("bytes") is not None:
                try:
                    outbound = await gateway.handle_binary(user_id, message["bytes"])
                except SessionGatewayError as exc:
                    await websocket.send_text(
                        f'{{"op":"error","detail":{_json_detail(str(exc))}}}'
                    )
                    continue
                await websocket.send_bytes(outbound)
    except WebSocketDisconnect:
        return


@router.post(
    "/api/v1/devices/{device_id}/session-ticket", response_model=SessionTicketResponse
)
def issue_agent_session_ticket(
    device_id: str,
    device=Depends(require_device),
) -> SessionTicketResponse:
    """Issue a single-use ticket binding the device credential to the WS."""
    if device.device_id != device_id:
        raise HTTPException(status_code=403, detail="Device identity mismatch")
    issue = get_device_tickets().issue_with_expiry(device_id)
    return SessionTicketResponse(
        ticket=issue.ticket,
        expires_at=issue.expires_at.isoformat(),
    )


@router.websocket("/api/v1/devices/{device_id}/session-ws")
async def agent_session_ws(websocket: WebSocket, device_id: str) -> None:
    """Redeem one device ticket, then serve Core->Agent session operations."""
    gateway = get_session_gateway()
    ticket = websocket.query_params.get("ticket")
    await websocket.accept()
    try:
        bound_device = get_device_tickets().redeem(ticket or "")
    except Exception:  # noqa: BLE001 - any redemption failure is unauthorized
        await websocket.close(code=WS_CLOSE_UNAUTHORIZED)
        return
    if bound_device != device_id:
        await websocket.close(code=WS_CLOSE_UNAUTHORIZED)
        return
    try:
        hello = json.loads(await websocket.receive_text())
        capability_ids = tuple(hello.get("capability_ids") or ())
        display_name = str(hello.get("display_name") or device_id)
    except (ValueError, TypeError, KeyError):
        await websocket.close(code=WS_CLOSE_GATEWAY_ERROR)
        return
    transport = AgentSessionTransport(device_id)
    transport.attach(websocket)
    transport.declare(capability_ids)
    device = RemoteDeviceSession(
        device_id=device_id,
        display_name=display_name,
        sessions=capability_ids,
        available=True,
        authority_generation=1,
        local=True,
    )
    try:
        gateway.router.register_device(device)
    except RemoteSessionError:
        gateway.router.update_device(device)
    gateway.router.attach_transport(transport)
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message.get("text") is not None:
                transport.resolve_text(message["text"])
            elif message.get("bytes") is not None:
                transport.resolve_bytes(message["bytes"])
    except WebSocketDisconnect:
        pass
    finally:
        gateway.router.detach_transport(device_id)
        transport.detach()


def _json_detail(detail: str) -> str:
    return json.dumps(detail)


__all__ = ["router"]
