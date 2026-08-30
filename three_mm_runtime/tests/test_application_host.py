import json
import zipfile

from three_mm_application_sdk import OperationContext
from three_mm_runtime.application_host import _load_service


def test_host_loads_reviewed_wheel_outside_core_and_passes_sdk_context(tmp_path):
    instance_root = tmp_path / "instance"
    release = instance_root / "releases" / ("a" * 64)
    release.mkdir(parents=True)
    (instance_root / "data").mkdir()
    wheel = release / "service.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("isolated_m12_app/__init__.py", "")
        archive.writestr(
            "isolated_m12_app/service.py",
            """
class Service:
    def __init__(self, application_context):
        self.application_context = application_context
    def handle(self, operation_id, payload, context):
        return {"module_id": self.application_context.module_id, "audience": context.audience}
def create_service(application_context):
    return Service(application_context)
""",
        )
        archive.writestr(
            "isolated_m12_app/migrations.py",
            """
from three_mm_application_sdk import ApplicationMigration
def apply_0001(connection):
    connection.execute('CREATE TABLE records (id INTEGER PRIMARY KEY)')
def get_migrations():
    return [ApplicationMigration('0001', apply_0001)]
""",
        )
    metadata = {
        "module_id": "org.3mm.isolated-test",
        "version": "1.0.0",
        "sha256": "a" * 64,
        "wheel": "service.whl",
        "entrypoint": "isolated_m12_app.service:create_service",
        "configuration": {},
        "storage": {
            "schema_revision": "0001",
            "migration_entrypoint": "isolated_m12_app.migrations:get_migrations",
        },
    }

    service = _load_service(metadata, instance_root)
    result = service.handle(
        "inspect",
        {},
        OperationContext(audience="internal", correlation_id="test"),
    )

    assert result == {
        "module_id": "org.3mm.isolated-test",
        "audience": "internal",
    }
