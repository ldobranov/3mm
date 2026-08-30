import base64
from datetime import UTC, datetime
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import zipfile

from backend.services.module_packages import validate_module_package
from three_mm_application_sdk import (
    ApplicationContext,
    ApplicationStorage,
    OperationContext,
)


REFERENCE_ROOT = Path(__file__).parents[2] / "modules" / "application-reference"


class FixedClock:
    def now(self):
        return datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


class FakePlatform:
    def __init__(self):
        self.checkpoint = {"revision": 0, "value": {"next_page": 1}}
        self.requests = []
        self.mutation_outcome = "succeeded"

    def connector_request(self, connector_id, *, method, path, **kwargs):
        self.requests.append((connector_id, method, path, kwargs))
        if method == "POST":
            return {"outcome": self.mutation_outcome, "http_status": 201}
        page = int(path.rsplit("/", 1)[-1])
        response = {
            "items": [{"id": f"item-{page}", "label": f"Item {page}"}],
            "next_page": 2 if page == 1 else None,
        }
        return {
            "outcome": "succeeded",
            "status_code": 200,
            "body_base64": base64.b64encode(json.dumps(response).encode()).decode(),
        }

    def get_checkpoint(self, checkpoint_id):
        assert checkpoint_id == "catalog"
        return dict(self.checkpoint)

    def put_checkpoint(self, checkpoint_id, value, *, expected_revision):
        assert checkpoint_id == "catalog"
        assert expected_revision == self.checkpoint["revision"]
        self.checkpoint = {
            "revision": expected_revision + 1,
            "value": dict(value),
        }
        return dict(self.checkpoint)


def _builder_module():
    spec = importlib.util.spec_from_file_location(
        "application_reference_builder",
        REFERENCE_ROOT / "build_reference_package.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _context(audience, key=None):
    return OperationContext(
        audience=audience,
        correlation_id=f"correlation-{key or audience}",
        idempotency_key=key,
    )


def test_reference_package_is_deterministic_and_exercises_full_workflow(tmp_path):
    builder = _builder_module()
    device_id = "dev_3b867082895a4771857b8bc6b56674a5"
    package = builder.build_package(device_id, "http://127.0.0.1:9911")
    assert package == builder.build_package(device_id, "http://127.0.0.1:9911")

    validated = validate_module_package(package, architecture="aarch64")
    assert validated.manifest.module_id == "org.3mm.application-reference"
    assert validated.manifest.version == "1.0.1"
    assert validated.application_extension is not None
    broken_upgrade = builder.build_package(
        device_id,
        "http://127.0.0.1:9911",
        version="1.0.2",
        broken_health=True,
    )
    broken_validated = validate_module_package(broken_upgrade, architecture="aarch64")
    assert broken_validated.manifest.version == "1.0.2"
    assert broken_validated.sha256 != validated.sha256

    with zipfile.ZipFile(__import__("io").BytesIO(package)) as archive:
        wheel_name = validated.application_extension.service.artifact
        wheel = archive.read(wheel_name)
    assert hashlib.sha256(wheel).hexdigest() == (
        validated.application_extension.service.artifact_sha256
    )
    wheel_path = tmp_path / Path(wheel_name).name
    wheel_path.write_bytes(wheel)

    sys.path.insert(0, str(wheel_path))
    try:
        migrations = importlib.import_module("reference_application.migrations")
        service_module = importlib.import_module("reference_application.service")
        storage = ApplicationStorage(tmp_path / "data")
        storage.migrate(migrations.get_migrations(), "0001")
        platform = FakePlatform()
        service = service_module.create_service(
            ApplicationContext(
                module_id=validated.manifest.module_id,
                version=validated.manifest.version,
                data_dir=tmp_path / "data",
                configuration=validated.manifest.configuration_defaults,
                storage=storage,
                platform=platform,
                clock=FixedClock(),
            )
        )

        registered = service.handle(
            "register", {"label": "Reference record"}, _context("kiosk", "register-1")
        )
        assert registered == service.handle(
            "register", {"label": "Reference record"}, _context("kiosk", "register-1")
        )
        record_id = registered["record_id"]
        assert service.handle(
            "approve", {"record_id": record_id}, _context("operator", "approve-1")
        ) == {"status": "approved"}
        assert service.handle(
            "assign_identifier",
            {"record_id": record_id, "opaque_identifier": "stage7-identifier"},
            _context("operator", "assign-1"),
        ) == {"status": "assigned"}
        assert service.handle(
            "add_item",
            {"record_id": record_id, "quantity": 2},
            _context("operator", "item-1"),
        ) == {"item_count": 2}

        def scan(event_id, occurred_at):
            return {
                "event_id": event_id,
                "device_id": device_id,
                "event_type": "identifier.scan.v1",
                "occurred_at": occurred_at,
                "payload": {"opaque_identifier": "stage7-identifier"},
            }

        assert service.handle(
            "process_scan",
            scan("evt_11111111111111111111111111111111", "2026-08-29T12:01:00+00:00"),
            _context("internal", "evt-1"),
        ) == {"status": "started"}
        assert service.handle(
            "process_scan",
            scan("evt_22222222222222222222222222222222", "2026-08-29T12:02:00+00:00"),
            _context("internal", "evt-2"),
        ) == {"status": "closed"}
        assert storage.status()["outbox"] == {"pending": 1}
        assert service.handle(
            "deliver_outbox", {}, _context("internal", "job-outbox-1")
        ) == {"delivered": 1, "retrying": 0, "manual_review": 0}
        assert storage.status()["outbox"] == {"succeeded": 1}

        with storage.transaction() as connection:
            storage.enqueue_outbox(
                connection,
                outbox_id="out-retry",
                event_type="record.finalized",
                payload={"record_id": "retry-record"},
                idempotency_key="reference-finalize:retry-record",
            )
        platform.mutation_outcome = "retryable"
        service.handle("deliver_outbox", {}, _context("internal", "job-outbox-2"))
        first_retry_request = platform.requests[-1][3]
        storage.update_outbox(
            "out-retry",
            state="retrying",
            attempts=1,
            next_attempt_at=FixedClock().now(),
        )
        platform.mutation_outcome = "succeeded"
        service.handle("deliver_outbox", {}, _context("internal", "job-outbox-3"))
        second_retry_request = platform.requests[-1][3]
        assert first_retry_request["idempotency_key"] == second_retry_request["idempotency_key"]
        assert first_retry_request["request_id"] != second_retry_request["request_id"]

        with storage.transaction() as connection:
            storage.enqueue_outbox(
                connection,
                outbox_id="out-ambiguous",
                event_type="record.finalized",
                payload={"record_id": "ambiguous-record"},
                idempotency_key="reference-finalize:ambiguous-record",
            )
        platform.mutation_outcome = "ambiguous"
        assert service.handle(
            "deliver_outbox", {}, _context("internal", "job-outbox-4")
        ) == {"delivered": 0, "retrying": 0, "manual_review": 1}
        assert storage.status()["outbox"] == {"ambiguous": 1, "succeeded": 2}
        platform.mutation_outcome = "succeeded"

        assert service.handle(
            "sync_catalog", {}, _context("internal", "job-sync-1")
        ) == {"status": "retrying", "items": 1}
        assert service.handle(
            "sync_catalog", {}, _context("internal", "job-sync-2")
        ) == {"status": "completed", "items": 1}
        with sqlite3.connect(storage.database_path) as connection:
            assert connection.execute(
                "SELECT item_id, published_revision FROM catalog_items ORDER BY item_id"
            ).fetchall() == [("item-1", 2), ("item-2", 2)]
    finally:
        sys.path.remove(str(wheel_path))
        for name in list(sys.modules):
            if name == "reference_application" or name.startswith("reference_application."):
                sys.modules.pop(name)
