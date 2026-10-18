"""Scoped local projection through exact existing human-consented peer links.

This does not enroll, sign, report, list inbound peers or manufacture consent.
The installed SDK method and compatibility dispatch keep their public shapes.
"""

import re

from sqlalchemy import select

from backend.db.installation_peer import InstallationPeerOutbound
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services.application_authority_context import ResolvedStatusScope
from backend.services.installation_projection import bound_installation_projection
from backend.services.installation_status_binding import (
    ExistingStatusBinding,
    read_existing_status_binding,
)
from three_mm_protocol.installation_peer import PEER_ID_PATTERN


_FIELDS = {
    "version",
    "request_id",
    "timestamp",
    "instance_id",
    "action",
    "signature",
    "link_id",
}


def resolve_status_scopes(db, application, principal, artifact_sha256):
    """Core snapshot reader only. Complete bounded set, not a caller selector."""
    columns = InstallationPeerOutbound.__table__.c
    with db.no_autoflush:
        links = tuple(
            db.scalars(
                select(columns.link_id)
                .where(
                    columns.module_id == application.module_id,
                    columns.application_instance_id == application.instance_id,
                    columns.state != "revoked",
                )
                .order_by(columns.link_id)
                .limit(33)
            )
        )
        if not links or len(links) > 32:
            raise ValueError("Existing status consent is unavailable or exceeds limits")
        resources = []
        for link_id in links:
            binding = read_existing_status_binding(
                db, application, link_id, allow_stopped=True
            )
            values = vars(binding).copy()
            values.pop("module_id")  # Exact same module is carried in owner.
            resources.append(
                ResolvedStatusScope(
                    owner=principal,
                    package_artifact_sha256=artifact_sha256,
                    operation="installation.status.read",
                    **values,
                )
            )
        return tuple(resources)


def read_application_status(db, installation, request):
    """Only the instance-authenticated platform boundary may call this adapter."""
    if (
        set(request) != _FIELDS
        or request.get("action") != "installation.status.get"
        or type(request.get("version")) is not int
        or request["version"] != 1
        or type(request.get("link_id")) is not str
        or re.fullmatch(PEER_ID_PATTERN, request["link_id"]) is None
    ):
        raise ValueError("Installation status request fields are invalid")
    if db.new or db.dirty or db.deleted or db.in_nested_transaction():
        raise ValueError("Installation status admission requires a clean session")
    installation_id, link_id = installation.id, request["link_id"]
    db.rollback()  # End the gateway snapshot before key -> guard -> peer row.
    from backend.services.application_authority_management import effect_admission

    try:
        with effect_admission(
            db, installation_id, f"status:{link_id}:read"
        ) as admission:
            if (
                admission.compatibility
                or admission.definition.service.sdk_version != "1.3"
                or "installation.status.read"
                not in admission.definition.platform_permissions
            ):
                raise ValueError("Scoped installation status read is unavailable")
            current = db.get(Installation, installation_id, populate_existing=True)
            if current is None or current.instance_id != request["instance_id"]:
                raise ValueError("Installation status transport binding changed")
            resources = [
                item for item in admission.status_projections if item.link_id == link_id
            ]
            if len(resources) != 1:
                raise ValueError("Exact installation status resource is unavailable")
            resource = resources[0]
            expected = ExistingStatusBinding(
                module_id=resource.owner.module_id,
                **resource.model_dump(
                    exclude={
                        "owner",
                        "package_artifact_sha256",
                        "operation",
                        "sender_identity",
                        "receiver_identity",
                        "consent",
                    }
                ),
                sender_identity=resource.sender_identity,
                receiver_identity=resource.receiver_identity,
                consent=resource.consent,
            )
            # Consent is a set in v8 reviews, but compatibility keeps its original
            # presentation order. Compare canonical copies, not wider selections.
            result = bound_installation_projection(db, current, expected).model_dump(
                mode="json"
            )
            db.commit()
            admission()  # Nothing is returned until the guard transaction ends.
            return result
    except Exception:
        db.rollback()
        raise
