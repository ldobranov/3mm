"""Real seals: connector first registration -> staged immutable upgrade -> review."""
import io
import json
import os
import zipfile

import pytest
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.module import ModulePackage
from backend.routes.application_extensions import StageApplicationPackageRequest
from backend.services import application_consent as consent
from backend.services import application_configuration_provenance as provenance
from backend.services.application_package_staging import stage_application_package, registration_id
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_connector_settings import (
    fresh, managed, source_subject, source_installed, repack, save, inspect, identity,
)

pytestmark=pytest.mark.skipif(os.name!='posix',reason='Real Core-owned seals and SQLite authority locks')


def test_connector_first_registration_survives_staging_review_and_reconfiguration(fresh):
    s=fresh
    repack(s,authentication='none')
    save(s,create_credential=False,credential=None)
    old=s.validated
    with Session(s.engine) as db:
        first_id=provenance.registration_id(db,1)
        first_payload=db.get(Action,first_id).payload
    buffer=io.BytesIO()
    with zipfile.ZipFile(s.archive) as source,zipfile.ZipFile(buffer,'w') as target:
        for name in source.namelist():
            value=source.read(name)
            if name in {'manifest.json','application-extension.json'}:
                data=json.loads(value);data['version']='1.0.1';value=json.dumps(data).encode()
            target.writestr(name,value)
    blob=buffer.getvalue();candidate=validate_module_package(blob)
    archive=s.root/'modules'/(candidate.sha256+'.zip');archive.write_bytes(blob)
    with Session(s.engine) as db,db.begin():
        row=ModulePackage(module_id=candidate.manifest.module_id,version=candidate.manifest.version,
            manifest=candidate.manifest.model_dump(mode='json'),sha256=candidate.sha256,
            size_bytes=len(blob),file_path=str(archive),registrations=[])
        db.add(row);db.flush();package_id=row.id
    stage_application_package(s.engine,candidate.sha256,StageApplicationPackageRequest(
        request_id=identity(),expected_artifact_sha256=old.sha256,configuration={}),s.token)
    with Session(s.engine) as db:
        assert db.get(Action,first_id).payload==first_payload
        assert db.get(Action,registration_id(db,1,package_id,candidate.sha256)) is not None
    s.validated=candidate;s.archive=archive
    # Read-only settings and fresh consent work with the old historical marker retained.
    state=inspect(s)
    assert state['connectors'][0]['state']=='configured'
    reviewed=consent.preview(s.manager,1,actor_token=s.token,request_id=identity())
    assert reviewed['artifact_sha256']==candidate.sha256
    assert reviewed['scopes']==['connector:business_api']
    # A configuration overlay must attach to the new package-specific proof.
    save(s,state=state,destination_origin='http://127.0.0.1:9998',create_credential=False,credential=None)
    reviewed=consent.preview(s.manager,1,actor_token=s.token,request_id=identity())
    result=consent.allow(s.manager,1,actor_token=s.token,request_id=identity(),
        preview_id=reviewed['preview_id'],expected_revision=reviewed['revision'],fingerprint=reviewed['fingerprint'],
        scopes=reviewed['selected_scopes'],user_permissions=reviewed['selected_user_permissions'],accept_native_code=True)
    assert result['saved']
    with Session(s.engine) as db:
        assert db.get(Action,first_id).payload==first_payload
