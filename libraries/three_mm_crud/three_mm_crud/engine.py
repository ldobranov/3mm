"""Shared CRUD over the current scoped SDK, with no Core SQL or HTTP access."""
from datetime import UTC,datetime
import hashlib,json,re,uuid
from three_mm_application_sdk.scoped_relational import ApplicationScopedStorage
from .schema import CrudDefinition,CrudError

MAX_COMMAND_RECEIPTS=5000

def encoded(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)

def record(row):
    return dict(record_id=row[0],data=json.loads(row[1]),revision=row[2],created_by=row[3],created_at=row[4],updated_at=row[5])

class CrudService:
    def __init__(self,application,definition):
        self.application=application
        self.definition=CrudDefinition.model_validate(definition)

    def handle(self,operation_id,payload,context):
        if operation_id=='health' and context.audience=='internal':return {'status':'ready'}
        storage=self.application.storage
        if not isinstance(storage,ApplicationScopedStorage):raise CrudError('Scoped relational storage is required')
        if context.audience not in {'administrator','operator'} or type(context.user_id) is not int or context.user_id<1:
            raise CrudError('A Core-authenticated human is required')
        if not isinstance(payload,dict):raise CrudError('Invalid CRUD request')
        if operation_id in {'export_data','erase_data'}:
            if context.audience!='administrator':raise CrudError('Administrator data management is required')
            if operation_id=='export_data':
                return self._list(storage,payload,export=True)
            if payload!={'confirm':True}:raise CrudError('Explicit erasure confirmation is required')
            def erase(db):
                db.execute('DELETE FROM crud_records')
                # Keep random request tombstones, with no payload, actor, data or
                # fingerprint, so a delayed old command cannot recreate erased data.
                db.execute('UPDATE crud_requests SET fingerprint=NULL,actor_id=NULL,operation_id=NULL,result=?',(encoded({'status':'erased','record':None}),))
                return {'status':'erased','record':None}
            return self._command(storage,context,operation_id,payload,erase)
        entity_name,_,action=operation_id.rpartition('_')
        entity=next((e for e in self.definition.entities if e.entity_id==entity_name),None)
        if entity is None:raise CrudError('Unknown CRUD operation')
        if action=='outcome':
            identifier=payload.get('request_id')
            if set(payload)!={'request_id'} or not isinstance(identifier,str) or not re.fullmatch('[0-9a-f]{32}',identifier):raise CrudError('Invalid command identity')
            with storage.read_transaction() as db:
                row=db.execute('SELECT result,actor_id,operation_id FROM crud_requests WHERE request_id=?',(identifier,)).fetchone()
            if row and (row[1] is None or (row[1]==str(context.user_id) and row[2] in {entity.entity_id+'_'+a for a in ('create','update','delete','import')})):
                return json.loads(row[0])
            return {'status':'not_found','record':None}
        if action=='list':return self._list(storage,{**payload,'entity_id':entity.entity_id})
        if action not in {'create','update','delete','import'}:raise CrudError('Unknown CRUD operation')
        if action=='import' and context.audience!='administrator':raise CrudError('Administrator recovery is required')
        def mutate(db):return self._mutate(db,entity,action,payload,context)
        return self._command(storage,context,operation_id,payload,mutate)

    def _command(self,storage,context,operation,payload,handler):
        key=context.idempotency_key
        if not isinstance(key,str) or not re.fullmatch(r'[0-9a-f]{32}',key):raise CrudError('Persist a 32-hex command request ID')
        fingerprint=hashlib.sha256(encoded([operation,payload,context.user_id]).encode()).hexdigest()
        with storage.transaction() as db:
            existing=db.execute('SELECT fingerprint,result FROM crud_requests WHERE request_id=?',(key,)).fetchone()
            if existing:
                if existing[0] is None:return {'status':'erased','record':None}
                result=json.loads(existing[1]) if existing[0]==fingerprint else {'status':'request_conflict','record':None}
            else:
                if operation!='erase_data' and db.execute('SELECT COUNT(*) FROM crud_requests').fetchone()[0]>=MAX_COMMAND_RECEIPTS:
                    result={'status':'full','record':None}
                else:
                    # Domain validation happens before business writes. Refusals
                    # finish the scoped transaction too, yielding a durable SDK
                    # receipt instead of an ambiguous aborted invocation.
                    try:result=handler(db)
                    except CrudError:result={'status':'invalid','record':None}
                    db.execute('INSERT INTO crud_requests VALUES (?,?,?,?,?)',(key,None if operation=='erase_data' else fingerprint,encoded(result),None if operation=='erase_data' else str(context.user_id),None if operation=='erase_data' else operation))
        # No success is returned before the scoped transaction completion.
        return result

    def _list(self,storage,payload,export=False):
        allowed={'entity_id','after'}
        if set(payload)-allowed:raise CrudError('Unknown list argument')
        entity_id=payload.get('entity_id')
        if entity_id not in {e.entity_id for e in self.definition.entities}:raise CrudError('Unknown entity')
        after=payload.get('after','')
        if not isinstance(after,str) or (after and not re.fullmatch('[0-9a-f]{32}',after)):raise CrudError('Invalid record cursor')
        with storage.read_transaction() as db:
            rows=db.execute('SELECT record_id,data,revision,created_by,created_at,updated_at FROM crud_records WHERE entity_id=? AND record_id>? ORDER BY record_id LIMIT 11',(entity_id,after)).fetchall()
        return {'items':[record(row) for row in rows[:10]],'next':rows[9][0] if len(rows)>10 else None}

    def _mutate(self,db,entity,action,payload,context):
        now=datetime.now(UTC).isoformat()
        if action=='create':
            if set(payload)!={'data'}:raise CrudError('Invalid create request')
            data=entity.validate_data(payload['data']);identifier=uuid.uuid4().hex
            if db.execute('SELECT COUNT(*) FROM crud_records').fetchone()[0]>=1000:raise CrudError('Record limit reached')
            db.execute('INSERT INTO crud_records VALUES (?,?,?,?,?,?,?)',(entity.entity_id,identifier,encoded(data),1,str(context.user_id),now,now))
        else:
            identifier=payload.get('record_id')
            if not isinstance(identifier,str) or not re.fullmatch('[0-9a-f]{32}',identifier):raise CrudError('Invalid record identity')
            existing=db.execute('SELECT record_id,data,revision,created_by,created_at,updated_at FROM crud_records WHERE entity_id=? AND record_id=?',(entity.entity_id,identifier)).fetchone()
            if action=='import':
                if set(payload)!={'record_id','data','created_by','created_at','updated_at'}:raise CrudError('Invalid recovery record')
                data=entity.validate_data(payload['data'],restored=True)
                for name in ('created_at','updated_at'):
                    if not isinstance(payload[name],str) or len(payload[name])>64:raise CrudError('Invalid recovery timestamp')
                    try:datetime.fromisoformat(payload[name])
                    except ValueError:raise CrudError('Invalid recovery timestamp') from None
                if not isinstance(payload['created_by'],str) or not payload['created_by'].isdigit() or len(payload['created_by'])>32:raise CrudError('Invalid historical actor reference')
                expected=(identifier,encoded(data),1,payload['created_by'],payload['created_at'],payload['updated_at'])
                if existing:
                    if tuple(existing)!=expected:return {'status':'conflict','record':record(existing)}
                else:
                    if db.execute('SELECT COUNT(*) FROM crud_records').fetchone()[0]>=1000:raise CrudError('Record limit reached')
                    db.execute('INSERT INTO crud_records VALUES (?,?,?,?,?,?,?)',(entity.entity_id,*expected))
            else:
                keys={'record_id','expected_revision'}|({'data'} if action=='update' else set())
                if set(payload)!=keys or type(payload.get('expected_revision')) is not int:raise CrudError('A current record revision is required')
                if not existing:return {'status':'missing','record':None}
                if existing[2]!=payload['expected_revision']:return {'status':'conflict','record':record(existing)}
                if action=='delete':
                    db.execute('DELETE FROM crud_records WHERE entity_id=? AND record_id=?',(entity.entity_id,identifier))
                    return {'status':'deleted','record':None}
                changes=entity.validate_data(payload['data'],partial=True)
                data=entity.validate_data({**json.loads(existing[1]),**changes},restored=True)
                db.execute('UPDATE crud_records SET data=?,revision=revision+1,updated_at=? WHERE entity_id=? AND record_id=?',(encoded(data),now,entity.entity_id,identifier))
        row=db.execute('SELECT record_id,data,revision,created_by,created_at,updated_at FROM crud_records WHERE entity_id=? AND record_id=?',(entity.entity_id,identifier)).fetchone()
        return {'status':'stored','record':record(row)}
