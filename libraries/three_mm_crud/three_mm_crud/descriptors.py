"""Generate ordinary application operations; no Core plugin or special loader."""
from .schema import CrudDefinition

def obj(properties,required=None):
    return dict(type='object',properties=properties,required=list(properties) if required is None else required,additionalProperties=False)

ID={'type':'string','pattern':'^[0-9a-f]{32}$'}
def data_schema(entity,*,partial=False):
    properties={}
    for field in entity.fields:
        kind=field.kind
        value={'type':{'text':'string','multiline':'string','date':'string','datetime':'string'}.get(kind,kind)}
        if kind in {'text','multiline','date','datetime'}:value['maxLength']=1024
        if not field.required:value['type']=[value['type'],'null']
        properties[field.field_id]=value
    return obj(properties,[] if partial else [f.field_id for f in entity.fields if f.required and not f.read_only])

def declarations(definition):
    definition=CrudDefinition.model_validate(definition)
    generic_record=obj({'record_id':ID,'data':{'type':'object'},'revision':{'type':'integer','minimum':1},
        'created_by':{'type':'string','maxLength':32},'created_at':{'type':'string','maxLength':64},'updated_at':{'type':'string','maxLength':64}})
    result=obj({'status':{'type':'string','enum':['stored','deleted','missing','conflict','erased','not_found','invalid','request_conflict','full']},'record':{'anyOf':[generic_record,{'type':'null'}]}})
    listing=obj({'items':{'type':'array','maxItems':10,'items':generic_record},'next':{'type':['string','null']}})
    operations=[];permissions=[]
    def add(name,kind,schema,output,permission=None,audiences=None):
        operations.append(dict(operation_id=name,kind=kind,audiences=audiences or ['operator','administrator'],
            required_permission=permission,idempotency='forbidden' if kind=='query' else 'required',
            input_schema=schema,output_schema=output,audit='redacted'))
    add('health','query',obj({}),obj({'status':{'type':'string','enum':['ready']}}),audiences=['internal'])
    for entity in definition.entities:
        read=entity.entity_id+'_read';write=entity.entity_id+'_write'
        for identifier,verb in ((read,'Read'),(write,'Change')):
            permissions.append(dict(permission_id=identifier,label={'en':verb+' '+entity.label.en},description={'en':verb+' records belonging to this application.'}))
        add(entity.entity_id+'_list','query',obj({'after':{'type':'string','pattern':'^(|[0-9a-f]{32})$'}},[]),listing,read)
        add(entity.entity_id+'_outcome','query',obj({'request_id':ID}),result,write)
        add(entity.entity_id+'_create','command',obj({'data':data_schema(entity)}),result,write)
        add(entity.entity_id+'_update','command',obj({'record_id':ID,'expected_revision':{'type':'integer','minimum':1},'data':data_schema(entity,partial=True)}),result,write)
        add(entity.entity_id+'_delete','command',obj({'record_id':ID,'expected_revision':{'type':'integer','minimum':1}}),result,write)
        recovery=obj({'record_id':ID,'data':data_schema(entity),'created_by':{'type':'string','pattern':'^[0-9]{1,32}$'},'created_at':{'type':'string','maxLength':64},'updated_at':{'type':'string','maxLength':64}})
        add(entity.entity_id+'_import','command',recovery,result,audiences=['administrator'])
    add('export_data','command',obj({'entity_id':{'type':'string','enum':[e.entity_id for e in definition.entities]},'after':{'type':'string','pattern':'^(|[0-9a-f]{32})$'}},['entity_id']),listing,audiences=['administrator'])
    add('erase_data','command',obj({'confirm':{'type':'boolean','enum':[True]}}),result,audiences=['administrator'])
    return permissions,operations

def storage_declaration():
    return dict(schema_revision='0001',migration_entrypoint='three_mm_crud.migrations:get_migrations',classifications=['private'],
        contains_personal_data=True,retention_policy='until_explicit_erasure',export_operation_id='export_data',erasure_operation_id='erase_data',
        relational=dict(contract_version=1,mode='read_write',limit_class='cooperative_v1',max_database_bytes=16*1024*1024,
            auxiliary_pause_bytes=1024*1024,max_statement_bytes=4096,max_value_bytes=32768,max_result_bytes=65536,
            max_result_rows=16,max_transaction_ms=5000,max_busy_ms=500))
