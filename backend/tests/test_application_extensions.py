from pathlib import Path

import pytest

import backend.database  # Register all ORM relationships for standalone runs.
from backend.config import ApplicationRuntimeSettings
from backend.db.module import ApplicationExtensionInstallation
from backend.services import application_extensions
from backend.services.application_extensions import (
    ApplicationGatewayError,
    invoke_application,
)
from backend.services.module_packages import validate_module_package
from backend.tests.test_module_packages import application_package


class Record:
    pass


def records(tmp_path: Path):
    blob = application_package()
    package_path = tmp_path / "application.zip"
    package_path.write_bytes(blob)
    validated = validate_module_package(blob)
    package = Record()
    package.file_path = str(package_path)
    package.sha256 = validated.sha256
    package.module_id = validated.manifest.module_id
    package.version = validated.manifest.version
    installation = ApplicationExtensionInstallation()
    installation.authority_mode = "compatibility"
    installation.enabled = True
    installation.status = "active"
    installation.instance_id = "a" * 24
    installation.socket_path = str(tmp_path / "service.sock")
    key_root = tmp_path / "keys"
    key_root.mkdir()
    (key_root / f"{installation.instance_id}.key").write_bytes(b"s" * 32)
    settings = ApplicationRuntimeSettings(
        root=tmp_path / "apps",
        key_root=key_root,
        helper_socket=tmp_path / "helper.sock",
    )
    return installation, package, settings


def test_stage_two_gateway_allows_only_declared_administrator_operations(
    monkeypatch, tmp_path
):
    installation, package, settings = records(tmp_path)

    class Client:
        def __init__(self, *_args):
            pass

        def invoke(self, operation_id, payload, context):
            return {}

    monkeypatch.setattr(application_extensions, "ApplicationServiceClient", Client)

    assert invoke_application(
        installation,
        package,
        settings,
        "approve",
        {},
        {
            "audience": "administrator",
            "correlation_id": "test",
            "user_id": 1,
            "idempotency_key": "request-0001",
        },
        required_audience="administrator",
    ) == {}

    with pytest.raises(ApplicationGatewayError, match="not available"):
        invoke_application(
            installation,
            package,
            settings,
            "register",
            {},
            {
                "audience": "administrator",
                "correlation_id": "test",
                "idempotency_key": "request-0002",
            },
            required_audience="administrator",
        )


def test_gateway_enforces_idempotency_and_strict_input_schema(tmp_path):
    installation, package, settings = records(tmp_path)

    with pytest.raises(ApplicationGatewayError, match="idempotency"):
        invoke_application(
            installation,
            package,
            settings,
            "approve",
            {},
            {"audience": "administrator", "correlation_id": "test"},
            required_audience="administrator",
        )
    with pytest.raises(ApplicationGatewayError, match="unknown fields"):
        invoke_application(
            installation,
            package,
            settings,
            "approve",
            {"unexpected": True},
            {
                "audience": "administrator",
                "correlation_id": "test",
                "idempotency_key": "request-0003",
            },
            required_audience="administrator",
        )


def test_public_relational_descriptor_is_denied_before_host_metadata_io(monkeypatch,tmp_path):
    from backend.tests.test_application_public_web import definition
    from three_mm_protocol.tests.test_application_relational_storage import relational_request
    from three_mm_runtime.application_transport import DispatchPhase
    import backend.services.application_relational as relational
    installation,package,settings=records(tmp_path)
    value=definition(package.module_id,'/public').model_dump(mode='json')
    value['service']['sdk_version']='1.3'
    value['storage']['relational']=relational_request()
    blob=application_package(definition=value)
    package.sha256=validate_module_package(blob).sha256
    Path(package.file_path).write_bytes(blob)
    monkeypatch.setattr(relational,'prepare_host_invocation',lambda *a,**k:pytest.fail('Unsupported public path performed host IPC'))
    with pytest.raises(ApplicationGatewayError,match='relational grant') as error:
        invoke_application(installation,package,settings,'render_public',{},
            {'audience':'public'},required_audience='public')
    assert error.value.phase==DispatchPhase.NOT_DISPATCHED
