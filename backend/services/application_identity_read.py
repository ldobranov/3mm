"""Already-initialized PUBLIC Core identity through current scoped authority.

This is not signing, possession proof, enrollment or permission to initialize
an identity. The compatibility GET remains in the original platform branch.
"""

from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services.application_authority_management import effect_admission
from backend.version import core_version
from three_mm_protocol.installation_identity import InstallationIdentityResultV1
from three_mm_protocol.diagnostics import DiagnosticSpan


READ_SCOPE = "platform:installation.identity.read"
_TRANSPORT_FIELDS = {
    "version", "request_id", "timestamp", "instance_id", "action", "signature",
}


def read_application_identity(db, installation, request, *, diagnostics=None):
    """Called only after the signed, instance-authenticated socket boundary."""
    if (
        set(request) != _TRANSPORT_FIELDS
        or request.get("action") != "installation.identity.get"
        or type(request.get("version")) is not int
        or request["version"] != 1
    ):
        raise ValueError("Installation identity request fields are invalid")
    if db.new or db.dirty or db.deleted or db.in_nested_transaction():
        raise ValueError("Installation identity admission requires a clean session")
    version = core_version()
    installation_id = installation.id
    # End the gateway read before acquiring key -> authority guard. No private
    # key, identity creation, helper process or network call is admitted here.
    db.rollback()
    try:
        with DiagnosticSpan(diagnostics, request.get("request_id"), "authority.admission",
                failure_result="denied", failure_reason="authority_unavailable", instance_id=request["instance_id"]) as trace:
            with effect_admission(db, installation_id, READ_SCOPE) as admission:
                if (
                    admission.compatibility
                    or admission.definition.service.sdk_version != "1.3"
                    or "installation.identity.read" not in admission.definition.platform_permissions
                ):
                    raise ValueError("Scoped installation identity read is unavailable")
                current = db.get(Installation, installation_id, populate_existing=True)
                if current is None or request["instance_id"] != current.instance_id:
                    raise ValueError("Installation identity transport binding changed")
                # The lease exposes the validated, re-resolved public resource
                # from _require_grant, not caller data or a private-key row.
                resources = admission.identities
                if len(resources) != 1 or resources[0].operation != "installation.identity.read":
                    raise ValueError("Installation identity resource is unavailable")
                trace.end()
                with DiagnosticSpan(diagnostics, request.get("request_id"), "identity.read", instance_id=request["instance_id"]):
                    result = InstallationIdentityResultV1(
                        identity=resources[0].identity, core_version=version,
                    ).model_dump(mode="json")
                    db.commit()  # End the guard transaction before releasing its key.
                    admission()
                    return result
    except Exception:
        db.rollback()
        raise
