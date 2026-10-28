"""Data retirement plus a delivered public-SDK consumer, without owner writes."""
import hashlib,importlib.util,io,json,subprocess,sys,zipfile
from pathlib import Path
import pytest
import sqlalchemy as sa
from backend.tests.test_migration_history import _alembic
from backend.tests.test_core_product_extraction import seed,table
from backend.services.module_packages import validate_module_package

ROOT=Path(__file__).parents[2]

def builder():
    spec=importlib.util.spec_from_file_location('contacts_builder',ROOT/'modules/runtime-contacts/build_package.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def snapshot(engine,name):
    with engine.connect() as db:
        target=table(db,name)
        # Compare all original values across the additive subject migration.
        columns=[c for c in target.c if name!='users' or c.name!='subject_id']
        return db.execute(sa.select(*columns)).all()

def test_populated_crud_retirement_preserves_records_metadata_and_exact_package_pins(tmp_path):
    url='sqlite:///'+str(tmp_path/'retirement.db');_alembic(url,'upgrade','7c52d3a4eb42');engine=sa.create_engine(url)
    with engine.begin() as db:
        seed(db,'users',id=7,username='owner',email='owner@example.test')
        seed(db,'module_packages',id=7,module_id='org.example.directory',version='1.0.0')
        seed(db,'runtime_extension_definitions',id=7,module_id='org.example.directory',version='1.0.0',definition={'exact':['данни',1]},created_by=7)
        seed(db,'runtime_entity_records',id=7,module_id='org.example.directory',entity_id='contact',record_id='a'*32,data={'name':'Запазено'},created_by=7)
    before={name:snapshot(engine,name) for name in ('runtime_extension_definitions','runtime_entity_records','users','module_packages')}
    _alembic(url,'upgrade','head');_alembic(url,'check')
    for name in ('runtime_extension_definitions','runtime_entity_records'):
        assert snapshot(engine,'retired_'+name)==before[name]
        assert sa.inspect(engine).get_foreign_keys('retired_'+name)==[]
    for name in ('users','module_packages'):assert snapshot(engine,name)==before[name]
    refs=snapshot(engine,'module_package_retained_references')
    assert len(refs)==1 and refs[0].package_id==7
    with engine.connect() as db:
        db.exec_driver_sql('PRAGMA foreign_keys=ON');db.execute(sa.text('DELETE FROM users WHERE id=7'));db.commit()
        assert db.exec_driver_sql('PRAGMA foreign_key_check').all()==[]
    assert snapshot(engine,'retired_runtime_entity_records')==before['runtime_entity_records']
    with pytest.raises(subprocess.CalledProcessError):_alembic(url,'downgrade','7c52d3a4eb42')
    assert snapshot(engine,'retired_runtime_entity_records')==before['runtime_entity_records']
    _alembic(url,'upgrade','head');assert len(snapshot(engine,'module_package_retained_references'))==1
    engine.dispose()

def test_delivered_contacts_uses_only_public_sdk_own_data_and_recovery_import(tmp_path):
    blob=builder().build_package();validated=validate_module_package(blob)
    artifact=tmp_path/'contacts.whl'
    with zipfile.ZipFile(io.BytesIO(blob)) as package:artifact.write_bytes(package.read(validated.application_extension.service.artifact))
    assert hashlib.sha256(artifact.read_bytes()).hexdigest()==validated.application_extension.service.artifact_sha256
    script=r'''
import importlib.abc,json,sys
from pathlib import Path
class NoCore(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'backend','agent','three_mm_runtime'}:raise AssertionError('Private import: '+fullname)
sys.meta_path.insert(0,NoCore());sys.path.insert(0,sys.argv[1])
from contacts_app.service import create_service
from three_mm_crud.migrations import get_migrations
from three_mm_crud.descriptors import storage_declaration
from three_mm_application_sdk import ApplicationStorage,ApplicationContext,OperationContext
from three_mm_application_sdk.scoped_relational import ApplicationScopedStorage,_TransactionAdmission
from three_mm_protocol.application_extension import ApplicationRelationalStorageV1
data=Path(sys.argv[2]);ApplicationStorage(data).migrate(get_migrations(),'0001')
storage=ApplicationScopedStorage(data,declaration=ApplicationRelationalStorageV1.model_validate(storage_declaration()['relational']),schema_revision='0001',admit=lambda tid,mode,profile,deadline:_TransactionAdmission(tid,mode,profile,deadline))
service=create_service(ApplicationContext('org.3mm.contacts','1.0.0',data,{},storage))
assert service.handle('health',{},OperationContext('internal','test'))=={'status':'ready'}
context=OperationContext('administrator','test',user_id=7,idempotency_key='1'*32)
saved=service.handle('contact_import',dict(record_id='a'*32,data={'name':'Запазено','email':'example@example.test'},created_by='999',created_at='2026-01-01T00:00:00',updated_at='2026-01-02T00:00:00'),context)
assert saved['record']['record_id']=='a'*32 and saved['record']['created_by']=='999'
assert service.handle('contact_list',{},OperationContext('operator','test',user_id=8))['items'][0]==saved['record']
print(json.dumps({'own_data_import':True,'core_imports':False,'public_sdk_only':True}))
'''
    result=subprocess.run([sys.executable,'-c',script,str(artifact),str(tmp_path/'own')],cwd=ROOT,check=True,capture_output=True,text=True)
    assert json.loads(result.stdout)=={'own_data_import':True,'core_imports':False,'public_sdk_only':True}

def test_personal_data_policy_is_explicit_and_preserves_export_erasure_requirements():
    from three_mm_protocol.application_extension import ApplicationExtensionV1
    _,application,_=builder().descriptors()
    assert ApplicationExtensionV1.model_validate(application).storage.retention_policy=='until_explicit_erasure'
    for key in ('export_operation_id','erasure_operation_id','retention_policy'):
        altered=json.loads(json.dumps(application));altered['storage'].pop(key)
        with pytest.raises(ValueError):ApplicationExtensionV1.model_validate(altered)

def test_old_core_crud_endpoints_are_absent_from_the_live_registry():
    from backend.main import app
    assert not any(path.startswith('/api/v1/runtime-extensions') for path in app.openapi()['paths'])
    from backend.db.base import Base
    assert not {'runtime_extension_definitions','runtime_entity_records'}&set(Base.metadata.tables)
