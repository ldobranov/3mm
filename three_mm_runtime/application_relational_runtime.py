"""Normal service adapter for an already protected/prepared own database.

This creates no namespace, schema, key or grant. Pending lifecycle evidence is
never bypassed. First install/upgrade still belong to the protected coordinator.
"""

import hashlib
from pathlib import Path

from three_mm_application_sdk.relational_receipts import _RelationalReceiptStore
from three_mm_application_sdk.relational_wire import accept_permit, canonical
from three_mm_application_sdk.scoped_relational import (
    ApplicationRelationalStorageError,
    ApplicationScopedStorage,
)
from three_mm_protocol.application_extension import ApplicationRelationalStorageV1
from three_mm_runtime.application_relational_session import (
    _decode,
    _prepared,
    _RelationalHostSession,
)


class PreparedRelationalRuntime:
    """Trusted host dependency, never a package-selected maintenance mode."""

    def __init__(self, instance_root, metadata, secret, group_id=None):
        self.root, self.metadata, self.secret = Path(instance_root), metadata, secret
        self.session = _RelationalHostSession(self.root, secret, group_id)
        # Bind the caller's entire active metadata to the protected source, not
        # just its declaration. Validation/import cannot use an altered copy.
        saved = _decode((self.root / "active.json").read_bytes(), limit=131072)
        if canonical(saved) != canonical(metadata):
            raise ValueError("Relational active metadata changed")

    def __enter__(self):
        self.session.__enter__()
        return self

    def __exit__(self, *args):
        self.session.__exit__(*args)

    def require_metadata(self, metadata, instance_root):
        if (
            Path(instance_root) != self.root
            or canonical(metadata) != canonical(self.metadata)
            or self.session._server is None
            or self.session._stop.is_set()
        ):
            raise ValueError("Relational host session is unavailable")

    def storage(self, platform):
        if platform is None:
            raise ValueError("Relational storage requires signed platform transport")
        definition = self.metadata["storage"]
        declaration = ApplicationRelationalStorageV1.model_validate(
            definition["relational"]
        )
        revision = definition["schema_revision"]

        def admit(identifier, mode, digest, deadline):
            # Check the host-owned invocation BEFORE IPC. Factory/health calls
            # cannot acquire an implicit DB grant, even if Core is reachable.
            try:
                expected = self.session._permit_expectations(identifier, mode)
            except ValueError as error:
                raise ApplicationRelationalStorageError(
                    "No active relational host invocation"
                ) from error
            if expected["profile_sha256"] != digest:
                raise ApplicationRelationalStorageError("Relational profile changed")
            permit = platform._call(
                "relational.admit", {"transaction_id": identifier, "mode": mode}
            )
            return accept_permit(
                permit, secret=self.secret, expected=expected, local_deadline=deadline
            )

        def complete(receipt):
            result = platform._call("relational.complete", {"receipt": receipt})
            if (
                result.get("transaction_id") != receipt["transaction_id"]
                or result.get("outcome") != "committed"
                or result.get("historical") is not True
            ):
                raise ValueError("Relational completion does not match")

        return ApplicationScopedStorage(
            self.root / "data",
            declaration=declaration,
            schema_revision=revision,
            admit=admit,
            complete=complete,
            receipts=_RelationalReceiptStore(
                database_lineage=self.session._record["database_lineage"],
                schema_revision=revision,
                secret=self.secret,
            ),
        )

    def readiness(self):
        # Reserved host health inspects only SDK/lifecycle metadata. Empty
        # outbox below is explicitly uninspected, not a fabricated queue count.
        record = _prepared(self.root, self.secret)
        if (
            hashlib.sha256(canonical(record)).digest()
            != hashlib.sha256(canonical(self.session._record)).digest()
        ):
            raise ValueError("Relational lifecycle changed; restart required")
        return {
            "revision": record["schema_revision"],
            "outbox": {},
            "outbox_inspected": False,
            "storage_profile": "relational",
        }
