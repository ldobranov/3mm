"""Resolve the single local controller without silently moving credentials.

Central management belongs to the Hub, never to a second Agent publisher.
This is startup configuration status, not proof of connectivity or enrollment.
"""

from urllib.parse import urlsplit, urlunsplit
from typing import Literal

from pydantic import BaseModel, ConfigDict

from three_mm_protocol import AgentRole
from three_mm_provisioning import ProvisioningSnapshot, ProvisioningState


class HubConnectionStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    hub_endpoint: str | None = None
    state: Literal[
        "not_configured", "awaiting_pairing", "credential_available",
        "reassignment_required", "invalid_endpoint",
        "pending_approval", "hub_unavailable", "rejected", "expired", "revoked",
        "enrollment_conflict", "enrollment_unavailable",
    ]
    central_management_path: Literal["via_hub"] = "via_hub"


def normalize_hub_endpoint(value: str) -> str:
    """Validate an explicit base URL without DNS requests or embedded secrets."""
    if not value or any(char.isspace() or ord(char) < 32 for char in value):
        raise ValueError("Invalid Hub endpoint")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or "\\" in value
    ):
        raise ValueError("Invalid Hub endpoint")
    port = parsed.port  # Also rejects invalid/out-of-range ports.
    if port == 0:
        raise ValueError("Invalid Hub endpoint")
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    if port is not None and (parsed.scheme, port) not in {("http", 80), ("https", 443)}:
        host = f"{host}:{port}"
    return urlunsplit((parsed.scheme, host, parsed.path.rstrip("/"), "", ""))


def resolve_hub_connection(
    *,
    role: AgentRole,
    snapshot: ProvisioningSnapshot | None,
    configured_endpoint: str | None,
    has_credential: bool,
    credential_endpoint: str | None = None,
) -> HubConnectionStatus:
    selected = configured_endpoint
    if (
        role is AgentRole.NODE
        and snapshot is not None
        and snapshot.state is ProvisioningState.PROVISIONED
        and snapshot.role is AgentRole.NODE
        and snapshot.hub_endpoint
    ):
        selected = snapshot.hub_endpoint
    if not selected:
        return HubConnectionStatus(state="not_configured")
    try:
        endpoint = normalize_hub_endpoint(selected)
    except ValueError:
        # Do not echo possibly embedded passwords in a diagnostic response.
        return HubConnectionStatus(state="invalid_endpoint")
    if not has_credential:
        return HubConnectionStatus(hub_endpoint=endpoint, state="awaiting_pairing")
    try:
        previous = normalize_hub_endpoint(credential_endpoint or configured_endpoint or "")
    except ValueError:
        previous = None
    # Legacy credentials have no authenticated Hub identity. A setup edit cannot
    # transfer them, their outbox or physical command history to a new controller.
    state = "credential_available" if endpoint == previous else "reassignment_required"
    return HubConnectionStatus(hub_endpoint=endpoint, state=state)
