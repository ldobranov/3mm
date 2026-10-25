"""Closed diagnostic imports and passive component inventory; no Core or service control."""
import json
import math
import os
from pathlib import Path
import re
import stat
from three_mm_protocol.diagnostics import (
    DiagnosticSession, COMPONENTS, OPERATIONS, RESULTS, REASONS, STAGES, SETUP_STAGES, TRACE_ID,
    SETUP_TRACE_ID, INSTANCE_ID, VERSION, MAX_EVENT_BYTES, MAX_EXPORT_BYTES,
)

ROOTS = {role: Path('/opt/3mm-' + role) for role in
         ('platform-runtime', 'connector-worker', 'agent', 'public-web', 'session-worker')}
ROOTS['application-host'] = Path('/opt/3mm-application-hosts/default')
DIGEST = re.compile(r'[0-9a-f]{64}\Z')
RECORD_FIELDS = {'schema_version','timestamp','component','version','operation','instance_id',
                 'trace_id','span_id','parent_span_id','result','reason','duration_ms'}


def _unique(pairs):
    result = {}
    for k,v in pairs:
        if k in result: raise ValueError('Duplicate diagnostic field')
        result[k] = v
    return result


def decode(data):
    def reject(_): raise ValueError('Non-finite diagnostic value')
    return json.loads(data,object_pairs_hook=_unique,parse_constant=reject)


def validate_record(value):
    if type(value) is not dict or set(value) != RECORD_FIELDS:
        raise ValueError('Diagnostic record fields are invalid')
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ValueError('Diagnostic record version is invalid')
    for key,choices in [('component',COMPONENTS),('operation',OPERATIONS),('result',RESULTS),('reason',REASONS)]:
        if type(value[key]) is not str or value[key] not in choices: raise ValueError('Diagnostic labels are invalid')
    if type(value['version']) is not str or not VERSION.fullmatch(value['version']): raise ValueError('Diagnostic version is invalid')
    if value['instance_id'] is not None and (type(value['instance_id']) is not str or not INSTANCE_ID.fullmatch(value['instance_id'])):
        raise ValueError('Diagnostic instance is invalid')
    setup = value['component']=='setup' and value['operation']=='device.setup'
    stages = SETUP_STAGES if setup else STAGES
    trace = SETUP_TRACE_ID if setup else TRACE_ID
    if (type(value['trace_id']) is not str or not trace.fullmatch(value['trace_id'])
            or type(value['span_id']) is not str or value['span_id'] not in stages
            or value['parent_span_id'] != stages[value['span_id']]): raise ValueError('Diagnostic span is invalid')
    for key,limit in [('timestamp',4102444800),('duration_ms',86400000)]:
        v=value[key]
        if type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=limit: raise ValueError('Diagnostic measurement is invalid')
    if len(json.dumps(value,separators=(',',':'),allow_nan=False).encode())>MAX_EVENT_BYTES:
        raise ValueError('Diagnostic event exceeds budget')
    return dict(value)


def validate_session(value):
    fields={'schema_version','session_id','component','version','active','scope','remaining_seconds',
            'buffer_bytes','max_buffer_bytes','records','accepted','dropped','events_per_second','spool_bytes'}
    if type(value) is not dict or set(value)!=fields: raise ValueError('Diagnostic session fields are invalid')
    if type(value['schema_version']) is not int or value['schema_version']!=1 or type(value['active']) is not bool:
        raise ValueError('Diagnostic session state is invalid')
    if (type(value['component']) is not str or value['component'] not in COMPONENTS
            or type(value['version']) is not str or not VERSION.fullmatch(value['version'])
            or value['session_id'] is not None and (type(value['session_id']) is not str or re.fullmatch('[0-9a-f]{32}',value['session_id']) is None)):
        raise ValueError('Diagnostic session identity is invalid')
    scope=value['scope']
    if type(scope) is not dict or set(scope)!={'profile','operation','instance_id','trace_id'} or scope['profile'] not in ('diagnostic','development'):
        raise ValueError('Diagnostic scope is invalid')
    for key,pattern in [('instance_id',INSTANCE_ID),('trace_id',TRACE_ID)]:
        if scope[key] is not None and (type(scope[key]) is not str or not pattern.fullmatch(scope[key])): raise ValueError('Diagnostic scope is invalid')
    if scope['operation'] is not None and (type(scope['operation']) is not str or scope['operation'] not in OPERATIONS): raise ValueError('Diagnostic operation is invalid')
    for key,limit in [('remaining_seconds',1800),('buffer_bytes',1048576),('max_buffer_bytes',1048576),('events_per_second',10),('spool_bytes',0),('records',2**63-1),('accepted',2**63-1)]:
        if type(value[key]) is not int or not 0<=value[key]<=limit: raise ValueError('Diagnostic counter is invalid')
    if type(value['dropped']) is not dict or set(value['dropped'])!={'full','rate','invalid','busy'}:
        raise ValueError('Diagnostic drop counters are invalid')
    if any(type(v) is not int or not 0<=v<=2**63-1 for v in value['dropped'].values()): raise ValueError('Diagnostic drop count is invalid')
    return value


def read_export(data):
    if type(data) is not bytes or not 1<=len(data)<=MAX_EXPORT_BYTES: raise ValueError('Diagnostic import exceeds budget')
    lines=data.splitlines()
    if not lines or any(not line or len(line)>MAX_EVENT_BYTES for line in lines): raise ValueError('Diagnostic framing is invalid')
    header=decode(lines[0])
    if type(header) is not dict or set(header)!={'session'}: raise ValueError('Diagnostic header is invalid')
    session=validate_session(header['session']);records=[]
    for line in lines[1:]:
        record=validate_record(decode(line))
        if record['component']!=session['component'] or record['version']!=session['version']: raise ValueError('Diagnostic producer changed')
        records.append(record)
    if len(records)>session['records']: raise ValueError('Diagnostic count is invalid')
    return {'session':session,'records':records,'truncated':len(records)<session['records']}


def timeline(local, imported=None, *, limit=500):
    if type(limit) is not int or not 1<=limit<=1000: raise ValueError('Invalid timeline limit')
    sources=([('local',local)] if local is not None else []) + ([('imported',imported)] if imported is not None else [])
    records=[];seen=set()
    for source,snapshot in sources:
        for value in snapshot['records']:
            record=validate_record(value);key=json.dumps(record,sort_keys=True,separators=(',',':'))
            if key in seen: continue
            seen.add(key);records.append({**record,'source':source})
    records.sort(key=lambda v:(v['timestamp'],v['trace_id'],v['span_id']))
    return {'schema_version':1,'sessions':[{'source':source,**validate_session(item['session'])} for source,item in sources],
            'records':records[:limit],'truncated':len(records)>limit or any(item.get('truncated') for _,item in sources),
            'missing_components':sorted(COMPONENTS-{item['session']['component'] for _,item in sources}),
            'clock_note':'Wall-clock ordering is observational; trace IDs correlate a hop, not authorization.'}


def read_regular(path,limit):
    flags=os.O_RDONLY | getattr(os,'O_NOFOLLOW',0) | getattr(os,'O_NONBLOCK',0)
    fd=os.open(path,flags)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>limit: raise ValueError('Diagnostic source is not bounded regular metadata')
        with os.fdopen(fd,'rb',closefd=False) as stream: data=stream.read(limit+1)
        if len(data)>limit: raise ValueError('Diagnostic source exceeds budget')
        return data
    finally: os.close(fd)


def component_inventory(roots=None):
    result=[]
    for role,root in (ROOTS if roots is None else roots).items():
        if role not in ROOTS: raise ValueError('Unknown component role')
        item={'component':role,'build_id':None,'state':'unavailable','reason':'metadata_unavailable','health':'unknown'}
        try:
            root=Path(root);current=(root/'current').resolve(strict=True)
            releases=(root.parent/'releases' if role=='application-host' else root/'releases').resolve(strict=True)
            if current.parent!=releases or not DIGEST.fullmatch(current.name): raise ValueError('Invalid component pin')
            metadata=decode(read_regular(current/'component.json',2*1024*1024))
            if metadata['build_id']!=current.name or not DIGEST.fullmatch(metadata['build_id']): raise ValueError('Invalid component metadata')
            if metadata.get('component') not in {role,'platform-runtime' if role=='connector-worker' else role}: raise ValueError('Foreign component role')
            item.update(build_id=current.name,state='installed',reason='passive_metadata')
        except (OSError,ValueError,KeyError,TypeError,RecursionError): pass
        result.append(item)
    return result


def snapshot(records=None):
    local=None
    result={'schema_version':1,'core_connection':'not_requested','components':component_inventory(),
            'timeline':timeline(local,read_export(records) if records is not None else None),
            'limitations':['Passive installed metadata; process health is unknown.',
                           'Imported records are observations; they confer no authority.']}
    return result


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records',type=Path,help='One bounded NDJSON producer export')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=snapshot(read_regular(args.records,MAX_EXPORT_BYTES) if args.records else None)
    data=json.dumps(result,sort_keys=True,indent=2,allow_nan=False).encode()+b'\n'
    # A diagnostic command never replaces an existing report or follows a symlink.
    with args.output.open('xb') as output:output.write(data)
    print('Wrote metadata-only diagnostic snapshot.')




if __name__=='__main__':main()
