import json
import zipfile
import pytest

from three_mm_application_sdk import OperationContext
from three_mm_runtime.application_host import _load_service


@pytest.mark.parametrize('declared', [False, True])
def test_host_loads_reviewed_wheel_outside_core_and_passes_sdk_context(tmp_path, declared):
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

    if declared:
        metadata['platform_requirements'] = [{'requirement_id':'optional_feature',
            'operations':['future.not_implemented'], 'required':False}]
    service = _load_service(metadata, instance_root)
    requirements = service.application_context.platform_requirements
    assert bool(requirements) == declared
    if declared:
        assert requirements[0].requirement_id == 'optional_feature' and requirements[0].required is False
    result = service.handle(
        "inspect",
        {},
        OperationContext(audience="internal", correlation_id="test"),
    )

    assert result == {
        "module_id": "org.3mm.isolated-test",
        "audience": "internal",
    }


@pytest.mark.parametrize('fault', ['binding', 'duplicates', 'not_list'])
def test_bad_requirement_metadata_is_rejected_before_import_or_migration(tmp_path, monkeypatch, fault):
    import three_mm_runtime.application_host as host
    release = tmp_path/'releases'/('a'*64); release.mkdir(parents=True)
    (release/'service.whl').write_bytes(b'not imported')
    need = {'requirement_id':'feature', 'operations':['event.publish']}
    needs = [need]
    if fault == 'binding': need['binding_id'] = 'output'
    elif fault == 'duplicates': needs.append(dict(need))
    else: needs = 'invalid'
    metadata = {'sha256':'a'*64, 'wheel':'service.whl', 'entrypoint':'unused:create_service',
        'storage':{'schema_revision':'0001','migration_entrypoint':'unused:get_migrations'},
        'platform_requirements':needs}
    def forbidden(*args): pytest.fail('Malformed metadata imported application code')
    monkeypatch.setattr(host.importlib, 'import_module', forbidden)
    with pytest.raises((ValueError, RuntimeError)): host._load_service(metadata, tmp_path)
    assert not (tmp_path/'data').exists()
