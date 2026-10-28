import hashlib
import importlib.util
import io
from pathlib import Path
import zipfile
from backend.services.module_packages import validate_module_package


def builder():
    path=Path(__file__).resolve().parents[2]/'modules/file-probe/build_package.py'
    spec=importlib.util.spec_from_file_location('file_probe_builder',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_neutral_consumer_is_deterministic_and_uses_only_public_contracts():
    module=builder()
    blob=module.build_package()
    assert blob==module.build_package()
    package=validate_module_package(blob)
    app=package.application_extension
    assert app.service.sdk_version=='1.3' and app.storage.private_files.file_contract_version==2
    assert app.storage.private_files.operations()==('read','write','publish','transform')
    assert not app.command_bindings and not app.connectors and not app.tasks
    assert app.routes[0].private_files.publish_permission=='files_publish'
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        source=archive.read('source/frontend/Files.vue').decode()
        assert "'@3mm/application-ui/v1'" in source and "'@3mm/ui/v1'" in source
        assert 'fetch(' not in source and 'axios' not in source and '/api/' not in source
        assert 'files.uploadStatus' in source and 'files.finalize' in source and 'files.revokeLink' in source
        assert hashlib.sha256(archive.read(app.service.artifact)).hexdigest()==app.service.artifact_sha256
