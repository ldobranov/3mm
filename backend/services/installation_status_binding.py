"""Public-only local consent snapshot, NOT permission or peer possession proof.

The caller owns package/actor authorization and the transaction. Review readers
must not lock or mutate; effect callers must lock the outbound row and compare
the complete current binding before projecting data. No credential, private
key, network, initialization or transaction control belongs in this module.
"""

import re
from dataclasses import dataclass

from sqlalchemy import select

from backend.db.installation_peer import InstallationPeerOutbound
from backend.services.installation_identity import read_existing_installation_identity
from three_mm_protocol.installation_identity import (
    InstallationIdentityV1,
    InstallationProofRequestV1,
)
from three_mm_protocol.installation_peer import PEER_ID_PATTERN, ProjectionConsentV1
from three_mm_protocol.module_manifest import MODULE_ID_PATTERN


@dataclass(frozen=True)
class ExistingStatusBinding:
    link_id: str
    module_id: str
    application_instance_id: str
    sender_identity: InstallationIdentityV1
    receiver_identity: InstallationIdentityV1
    origin: str
    target_module_id: str
    consent_revision: int
    consent: ProjectionConsentV1


def _public_identity(value):
    # Stored JSON must be exact public metadata, not permissively coerced input
    # or an ORM row with encrypted_private_key attached to it.
    strings = {"installation_id", "algorithm", "key_id", "public_key", "created_at"}
    if (
        type(value) is not dict
        or set(value) != strings | {"identity_version", "key_generation"}
        or any(type(value[name]) is not str for name in strings)
        or len(value["created_at"]) > 64
        or type(value["identity_version"]) is not int
        or type(value["key_generation"]) is not int
    ):
        raise ValueError("Invalid public peer identity")
    return InstallationIdentityV1.model_validate(value)


def _consent(value):
    limits = {"summary_fields": 3, "node_ids": 64, "node_fields": 9}
    if (
        type(value) is not dict
        or set(value) - (set(limits) | {"consent_version"})
        or ("consent_version" in value and type(value["consent_version"]) is not int)
        or any(
            name in value
            and (
                type(value[name]) is not list
                or len(value[name]) > limit
                or any(type(item) is not str for item in value[name])
            )
            for name, limit in limits.items()
        )
    ):
        raise ValueError("Invalid local reporting consent")
    # Preserve the existing consent order in compatibility responses. A future
    # authority context must canonicalize sets without changing old versions.
    return ProjectionConsentV1.model_validate(value)


def read_existing_status_binding(
    db, application, link_id: str, *, allow_stopped=False
) -> ExistingStatusBinding:
    """Read one current installation-owned, locally consented outbound link.

    This is not an SDK admission entry point. In particular a binding alone
    cannot satisfy current Core grants or change the scoped platform allowlist.
    No private peer columns are selected, even if the session has cached rows.
    Core review readers may inspect a stopped installation's metadata; that
    explicit flag never permits a projection or a stopped runtime operation.
    """
    with db.no_autoflush:
        # Even validation can reload expired ORM attributes. Include it in the
        # read-only boundary so it cannot flush unrelated caller changes.
        if (
            type(allow_stopped) is not bool
            or not (
                (application.enabled is True and application.status == "active")
                or (
                    allow_stopped
                    and application.enabled is False
                    and application.status == "disabled"
                )
            )
            or type(application.module_id) is not str
            or len(application.module_id) > 160
            or re.fullmatch(MODULE_ID_PATTERN, application.module_id) is None
            or type(application.instance_id) is not str
            or re.fullmatch(r"[0-9a-f]{24}", application.instance_id) is None
            or type(link_id) is not str
            or re.fullmatch(PEER_ID_PATTERN, link_id) is None
        ):
            raise ValueError("Application status binding is unavailable")
        columns = InstallationPeerOutbound.__table__.c
        row = db.execute(
            select(
                columns.link_id,
                columns.module_id,
                columns.application_instance_id,
                columns.sender_identity,
                columns.receiver_identity,
                columns.origin,
                columns.target_module_id,
                columns.consent_revision,
                columns.consent,
            ).where(
                columns.link_id == link_id,
                columns.module_id == application.module_id,
                columns.application_instance_id == application.instance_id,
                columns.state.in_(("new", "pending", "active")),
            )
        ).one_or_none()
        if row is None:
            raise ValueError("Local reporting consent is unavailable or withdrawn")
        values = dict(row._mapping)
        if (
            type(values["consent_revision"]) is not int
            or not 1 <= values["consent_revision"] <= 2**53 - 1
            or type(values["origin"]) is not str
            or len(values["origin"]) > 255
            or type(values["target_module_id"]) is not str
            or len(values["target_module_id"]) > 160
            or re.fullmatch(MODULE_ID_PATTERN, values["target_module_id"]) is None
        ):
            raise ValueError("Local reporting binding is invalid")
        InstallationProofRequestV1.canonical_origin(values["origin"])
        values["sender_identity"] = _public_identity(values["sender_identity"])
        values["receiver_identity"] = _public_identity(values["receiver_identity"])
        values["consent"] = _consent(values["consent"])
        identity = read_existing_installation_identity(db)
        if identity != values["sender_identity"]:
            raise ValueError("Local installation identity changed")
        return ExistingStatusBinding(**values)
