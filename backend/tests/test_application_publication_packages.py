"""Optional immutable publication sidecar, no implicit permission upgrades."""

import io
import json
import zipfile

import pytest

from backend.services.module_packages import validate_module_package, ModulePackageError
from backend.tests.test_module_packages import application_package
from three_mm_protocol.application_event_publication import parse_application_publications


def contract():
    app = validate_module_package(application_package()).application_extension
    return {'publication_contract_version': 1, 'module_id': app.module_id, 'version': app.version,
        'service_artifact_sha256': app.service.artifact_sha256,
        'publications': [{'publication_id': 'approved', 'operation_id': 'approve',
            'event_type': 'workflow.record.approved',
            'payload_schema': {'type': 'object', 'properties': {'id': {'type': 'integer', 'minimum': 1, 'maximum': 100}},
                'required': ['id'], 'additionalProperties': False}}]}


def packaged(data):
    stream = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(application_package())) as source, zipfile.ZipFile(stream, 'w') as target:
        for item in source.infolist():
            target.writestr(item.filename, source.read(item.filename))
        target.writestr('application-event-publications.json', data)
    return stream.getvalue()


def test_old_application_and_descriptor_stay_unchanged_optional_sidecar_validates():
    old = validate_module_package(application_package())
    new = validate_module_package(packaged(json.dumps(contract())))
    assert old.application_publications is None
    assert old.application_extension == new.application_extension
    assert new.application_publications.publications[0].publication_id == 'approved'
    assert old.sha256 != new.sha256


@pytest.mark.parametrize('field,value', [('module_id', 'org.example.other'), ('version', '2.0.0'),
    ('service_artifact_sha256', 'f' * 64), ('publication_contract_version', True)])
def test_sidecar_cannot_replace_artifact_or_contract_identity(field, value):
    declaration = {**contract(), field: value}
    with pytest.raises(ModulePackageError, match='publication declaration'):
        validate_module_package(packaged(json.dumps(declaration)))


@pytest.mark.parametrize('field,value', [('operation_id', 'register'), ('event_type', 'core.audit'),
    ('event_type', 'example.undeclared.v1'), ('max_payload_bytes', 100000), ('publication_id', '*')])
def test_publication_requires_exact_declaring_operation_event_and_bounds(field, value):
    declaration = contract()
    declaration['publications'][0][field] = value
    with pytest.raises(ModulePackageError, match='publication declaration'):
        validate_module_package(packaged(json.dumps(declaration)))


@pytest.mark.parametrize('data', [
    '{"publication_contract_version":1,"publication_contract_version":1}',
    json.dumps(contract()).replace('"maximum": 100', '"maximum": 100, "maximum": 100'),
    ' ' * 65537, '{"invalid":"\ud800"}',
], ids=['duplicate-version', 'duplicate-schema', 'oversize', 'unicode'])
def test_declaration_raw_parser_rejects_ambiguous_oversize_or_invalid_json(data):
    with pytest.raises((ValueError, UnicodeError)):
        parse_application_publications(data)


def test_sidecar_reports_all_authority_changes_not_just_permissions():
    from backend.services.application_authority_review import review_application_authority
    old = validate_module_package(application_package())
    new = validate_module_package(packaged(json.dumps(contract())))
    review = review_application_authority(new, previous=old)
    assert any(change.scope == 'publication:approved' for change in review.changes)
