"""Explicit matching provider selection, never a grant or automatic fallback."""
import os
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services.application_configuration import resolve_device_selection, ApplicationConfigurationError
from backend.tests.test_application_composition_authority import pair, installed, source_subject, source_installed

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Real M20 package/key fixture')


def test_configuration_route_offers_exact_matching_export_without_selecting_or_approving_it(pair):
    from backend.routes.application_extensions import router
    from backend.utils.db_utils import get_db
    app = FastAPI(); app.include_router(router)
    def database():
        with Session(pair.engine) as db: yield db
    app.dependency_overrides[get_db] = database
    url = f'/api/v1/application-extensions/packages/{pair.consumer.sha256}/configuration'
    with TestClient(app) as client:
        assert client.get(url).status_code in (401, 403)
        response = client.get(url, headers={'Authorization': 'Bearer '+pair.token})
    assert response.status_code == 200, response.text
    field, = response.json()['fields']
    assert field['kind'] == 'application_query' and field['key'] == 'DIRECTORY_INSTANCE'
    assert field['export_key'] == 'DIRECTORY_EXPORT'
    assert field['choices'] == [dict(instance_id='a'*24, export_id='lookup',
        module_id=pair.provider.manifest.module_id, version='1.0.0', artifact_sha256=pair.provider.sha256)]
    assert not field['choices_truncated']


def test_query_configuration_requires_both_explicit_fields_preserves_saved_selection_and_refuses_arbitrary_values(pair):
    definition = pair.consumer.application_extension
    manifest = pair.consumer.manifest
    schema, defaults = manifest.configuration_schema, manifest.configuration_defaults
    selection = {'DIRECTORY_INSTANCE': 'a'*24, 'DIRECTORY_EXPORT': 'lookup'}
    assert resolve_device_selection(schema, defaults, definition, selection=selection) == selection
    assert resolve_device_selection(schema, defaults, definition, existing=selection) == selection
    for bad in ({}, {'DIRECTORY_INSTANCE': 'a'*24}, selection | {'ARBITRARY': 'value'}):
        with pytest.raises(ApplicationConfigurationError): resolve_device_selection(schema, defaults, definition, selection=bad)
    # Catalog disappearance cannot select a replacement or mutate saved config.
    from backend.services.application_query_configuration import configuration_fields
    with Session(pair.engine) as db, db.begin():
        db.execute(update(Installation).where(Installation.id == 1).values(enabled=False))
    field, = configuration_fields(pair.engine, definition, selection)
    assert field['choices'] == [] and field['value'] == 'a'*24 and field['export_value'] == 'lookup'


def test_scoped_sql_provider_is_explicitly_outside_first_query_execution_profile(pair):
    from backend.tests.test_application_checkpoint_authority import store_checkpoint_package
    from three_mm_protocol.tests.test_application_relational_storage import relational_request
    from backend.tests.test_application_composition_authority import preview
    from backend.services.application_authority_management import AuthorityManagementError
    app = pair.provider.application_extension.model_dump(mode='json')
    app['storage']['relational'] = relational_request()
    # Replace only the provider's real test ZIP, not an invented DTO.
    pair.archive = pair.root/'modules'/(pair.provider.sha256+'.zip')
    store_checkpoint_package(pair, app, pair.provider.manifest.model_dump(mode='json'))
    with pytest.raises(AuthorityManagementError, match='unsupported_authority'): preview(pair)
    from backend.services.application_composition_authority import resolve_queries
    prepared = pair.manager._prepare(2)
    with pair.manager.keys.locked() as key, Session(pair.engine) as db, db.begin():
        with pytest.raises(AuthorityManagementError, match='query_profile_unsupported'):
            resolve_queries(pair.manager, db, key, 2, prepared)
