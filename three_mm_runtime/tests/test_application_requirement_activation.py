"""Dependency refusal precedes filesystem, key, database and supervisor effects."""
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import zipfile

import pytest

from three_mm_runtime.application_activation import activate_application_package, ApplicationActivationError
from three_mm_runtime.tests.test_application_activation import service_package, Supervisor, ReadyClient


def candidate(requirements):
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(service_package())) as old, zipfile.ZipFile(output, 'w') as new:
        for name in old.namelist():
            data = old.read(name)
            if name in {'manifest.json', 'application-extension.json'}:
                value = json.loads(data); value['version'] = '1.0.1'
                if name == 'application-extension.json':
                    value['service']['sdk_version'] = '1.3'
                    value['platform_requirements'] = requirements
                data = json.dumps(value).encode()
            new.writestr(name, data)
    return output.getvalue()


def disk(root):
    return {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()} if root.exists() else {}


@pytest.mark.parametrize('existing', [False, True])
@pytest.mark.parametrize('fault', ['operation', 'version'])
def test_installer_dependency_gate_preserves_existing_application_and_data(tmp_path, existing, fault):
    archive = tmp_path/'package.zip'; root = tmp_path/'apps'; keys = tmp_path/'keys'
    supervisor = Supervisor()
    if existing:
        blob = service_package(); archive.write_bytes(blob)
        active = activate_application_package(archive, hashlib.sha256(blob).hexdigest(),
            root=root, key_root=keys, supervisor=supervisor, client_factory=ReadyClient)
        connection = sqlite3.connect(root/active.instance_id/'data/state.sqlite3')
        connection.execute('CREATE TABLE owner_records(value TEXT)')
        connection.execute("INSERT INTO owner_records VALUES('preserve')")
        connection.commit(); connection.close()
    supervisor.calls.clear()
    before = disk(root), disk(keys)
    need = {'requirement_id':'needed_feature', 'operations':['future.not_implemented']}
    if fault == 'version': need.update(operations=['event.publish'], transport_contract_version=2)
    blob = candidate([need]); archive.write_bytes(blob)
    with pytest.raises(ApplicationActivationError, match='needed_feature'):
        activate_application_package(archive, hashlib.sha256(blob).hexdigest(),
            root=root, key_root=keys, supervisor=supervisor, client_factory=ReadyClient)
    assert (disk(root), disk(keys)) == before and supervisor.calls == []
    if not existing: assert not root.exists() and not keys.exists()


def test_optional_requirement_is_delivered_as_metadata_without_changing_activation(tmp_path):
    needs = [{'requirement_id':'optional_feature', 'operations':['future.not_implemented'], 'required':False}]
    blob = candidate(needs); path = tmp_path/'package.zip'; path.write_bytes(blob)
    supervisor = Supervisor()
    active = activate_application_package(path, hashlib.sha256(blob).hexdigest(), root=tmp_path/'apps',
        key_root=tmp_path/'keys', supervisor=supervisor, client_factory=ReadyClient)
    metadata = json.loads((tmp_path/'apps'/active.instance_id/'active.json').read_text())
    assert metadata['platform_requirements'][0]['required'] is False
    assert metadata['platform_requirements'][0]['requirement_id'] == 'optional_feature'
    assert supervisor.calls == [('restart', active.instance_id)]
