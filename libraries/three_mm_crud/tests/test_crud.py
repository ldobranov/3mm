"""Real own-SQLite transactions; admission callbacks are an explicit unit seam."""
from types import SimpleNamespace
import json,uuid
import pytest
from three_mm_application_sdk import ApplicationStorage,OperationContext
from three_mm_application_sdk.scoped_relational import ApplicationScopedStorage,_TransactionAdmission,ApplicationRelationalStorageError,ApplicationRelationalExecutionUnconfirmed
from three_mm_protocol.application_extension import ApplicationRelationalStorageV1
from three_mm_crud import CrudService
from three_mm_crud.schema import CrudError
from three_mm_crud.descriptors import storage_declaration
from three_mm_crud.migrations import get_migrations

def identity():return uuid.uuid4().hex
def definition(entity='person'):
    return dict(crud_version=1,name={'en':'Directory'},entities=[dict(entity_id=entity,label={'en':'Person'},fields=[
        dict(field_id='name',kind='text',label={'en':'Name'},required=True),
        dict(field_id='age',kind='integer',label={'en':'Age'}),
        dict(field_id='active',kind='boolean',label={'en':'Active'}),
        dict(field_id='day',kind='date',label={'en':'Day'})])])

def service(path,*,admit=True,entity='person'):
    ApplicationStorage(path).migrate(get_migrations(),'0001')
    storage=ApplicationScopedStorage(path,declaration=ApplicationRelationalStorageV1.model_validate(storage_declaration()['relational']),schema_revision='0001',
        admit=(lambda tid,mode,profile,deadline:_TransactionAdmission(tid,mode,profile,deadline)) if admit else None)
    return CrudService(SimpleNamespace(storage=storage),definition(entity))

def context(key=None,user=7,audience='operator'):return OperationContext(audience,'test',user_id=user,idempotency_key=key)
def create(s,name='Ана',key=None):return s.handle('person_create',{'data':{'name':name}},context(key or identity()))
def listing(s):return s.handle('person_list',{},context())

def test_crud_revision_conflicts_restart_and_no_duplicate_replay(tmp_path):
    s=service(tmp_path/'own');key=identity();first=create(s,key=key);row=first['record']
    assert create(s,key=key)==first
    assert create(s,'changed',key)['status']=='request_conflict'
    updated=s.handle('person_update',dict(record_id=row['record_id'],expected_revision=1,data={'name':'Ива'}),context(identity()))
    assert updated['record']['revision']==2
    stale=s.handle('person_delete',dict(record_id=row['record_id'],expected_revision=1),context(identity()))
    assert stale['status']=='conflict'
    restarted=service(tmp_path/'own');assert listing(restarted)['items'][0]['data']=={'name':'Ива'}
    assert restarted.handle('person_outcome',{'request_id':key},context())==first
    assert restarted.handle('person_outcome',{'request_id':key},context(user=8))['status']=='not_found'
    assert restarted.handle('person_delete',dict(record_id=row['record_id'],expected_revision=2),context(identity()))['status']=='deleted'
    assert listing(restarted)['items']==[]

@pytest.mark.parametrize('data',[{}, {'name':None},{'name':7},{'name':'x','age':True},{'name':'x','active':1},{'name':'x','day':'bad'},{'name':'x','extra':1},{'name':'x'*1025}])
def test_invalid_data_is_a_confirmed_refusal_without_partial_records(tmp_path,data):
    s=service(tmp_path/'own')
    key=identity()
    assert s.handle('person_create',{'data':data},context(key))=={'status':'invalid','record':None}
    assert s.handle('person_outcome',{'request_id':key},context())['status']=='invalid'
    assert listing(s)['items']==[]

def test_scope_boundaries_no_storage_fallback_and_factory_has_no_effects(tmp_path):
    class Forbidden:
        def __getattribute__(self,name):raise AssertionError('Factory opened storage')
    s=CrudService(SimpleNamespace(storage=Forbidden()),definition())
    assert s.handle('health',{},OperationContext('internal','health'))=={'status':'ready'}
    missing=service(tmp_path/'missing',admit=False)
    with pytest.raises(ApplicationRelationalStorageError):create(missing)
    first=service(tmp_path/'first');second=service(tmp_path/'second');create(first)
    assert listing(second)['items']==[]
    for actor in (context(audience='public'),context(user=None),context(audience='internal')):
        with pytest.raises(CrudError):first.handle('person_list',{},actor)
    with pytest.raises(CrudError):first.handle('other_list',{},context())

def test_pagination_import_conflicts_and_principal_provenance(tmp_path):
    s=service(tmp_path/'own')
    for i in range(12):create(s,str(i))
    page=listing(s);assert len(page['items'])==10 and page['next']
    assert len(s.handle('person_list',{'after':page['next']},context())['items'])==2
    row={'record_id':'a'*32,'data':{'name':'Запазен'},'created_by':'999','created_at':'2026-01-01T00:00:00','updated_at':'2026-01-02T00:00:00'}
    with pytest.raises(CrudError):s.handle('person_import',row,context(identity()))
    result=s.handle('person_import',row,context(identity(),audience='administrator'))
    assert result['record']['created_by']=='999'
    assert s.handle('person_import',row,context(identity(),audience='administrator'))==result
    assert s.handle('person_import',{**row,'data':{'name':'overwrite'}},context(identity(),audience='administrator'))['status']=='conflict'

def test_erasure_removes_payloads_and_actor_refs_without_replaying_old_commands(tmp_path):
    s=service(tmp_path/'own');key=identity();create(s,'private-person',key)
    with pytest.raises(CrudError):s.handle('erase_data',{'confirm':True},context(identity()))
    s.handle('erase_data',{'confirm':True},context(identity(),audience='administrator'))
    assert listing(s)['items']==[]
    assert create(s,'private-person',key)=={'status':'erased','record':None}
    with s.application.storage.read_transaction() as db:
        rows=db.execute('SELECT fingerprint,result,actor_id,operation_id FROM crud_requests').fetchall()
    assert all(row[0] is None and row[2] is None and row[3] is None for row in rows)
    assert 'private-person' not in json.dumps([tuple(row) for row in rows])

def test_entity_prefixes_are_not_ambiguous(tmp_path):
    s=service(tmp_path/'own',entity='person_note')
    assert s.handle('person_note_create',{'data':{'name':'note'}},context(identity()))['status']=='stored'

def test_full_command_journal_cannot_block_administrator_erasure(tmp_path,monkeypatch):
    import three_mm_crud.engine as engine
    monkeypatch.setattr(engine,'MAX_COMMAND_RECEIPTS',2)
    s=service(tmp_path/'own');create(s);create(s)
    assert create(s)['status']=='full'
    key=identity()
    assert s.handle('erase_data',{'confirm':True},context(key,audience='administrator'))['status']=='erased'
    assert listing(s)['items']==[]
    assert s.handle('erase_data',{'confirm':True},context(key,audience='administrator'))['status']=='erased'
