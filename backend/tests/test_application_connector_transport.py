"""Result integrity, current worker identity and durable completion fencing."""
import base64
import os
import socket
import threading
import time
import uuid

import pytest
from sqlalchemy import select
from backend.db.module import ApplicationConnectorAttempt as Attempt
from backend.services.application_connector_transport import (
    ConnectorDispatch, begin_connector, finish_connector, sign, result_key, expire_connector_attempts,
)
from backend.tests.test_application_connectors import connector_db, create_credential, bind_connector
from three_mm_platform_wire import read_frame

pytestmark=pytest.mark.skipif(os.name!='posix',reason='Actual Unix peer/boot identity')


@pytest.fixture
def admitted(connector_db,tmp_path):
    db,app=connector_db
    credential=create_credential(db,app,label='network',credential_kind='basic',value={'username':'u','password':'private'})
    bind_connector(db,app,'business_api','https://example.test',credential.secret_ref)
    (tmp_path/(app.instance_id+'.key')).write_bytes(b's'*32)
    path=tmp_path/'worker.sock';listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);listener.bind(str(path));listener.listen(1)
    captured=[]
    def accept():
        connection,_=listener.accept()
        with connection:captured.append(read_frame(connection,time.monotonic()+3))
    thread=threading.Thread(target=accept);thread.start()
    request={'request_id':'platform_'+uuid.uuid4().hex,'connector_request_id':'connector_'+uuid.uuid4().hex,
        'connector_id':'business_api','method':'POST','path':'/api/records','headers':{},'body_base64':'e30=','idempotency_key':'logical-1'}
    dispatch=begin_connector(db,app,request,secret=b's'*32,runtime_generation='a'*32,worker_path=path,worker_uid=os.geteuid())
    thread.join(timeout=3);listener.close();assert not thread.is_alive()
    assert isinstance(dispatch,ConnectorDispatch)
    dispatch.connection.close()
    response={'outcome':'succeeded','http_status':201,'error_category':None,'body_base64':'e30=','headers':{'Content-Type':'application/json'}}
    response=sign(response,bytes.fromhex(captured[0]['result_key']))
    return db,app,dispatch.receipt,response,tmp_path,captured[0],request


def finish(state,receipt=None,response=None,generation='a'*32):
    db,app,original,answer,root,plan,request=state
    return finish_connector(db,original if receipt is None else receipt,answer if response is None else response,
        key_root=root,runtime_generation=generation)


def test_valid_result_commits_once_without_any_authority_mutation(admitted):
    db,app,receipt,response,root,plan,request=admitted
    epoch=app.authority_epoch
    result=finish(admitted)
    assert result['request_id']==request['request_id'] and result['result']['outcome']=='succeeded'
    assert finish(admitted)['result']['duplicate']
    assert app.authority_epoch==epoch and len(list(db.scalars(select(Attempt))))==1
    assert plan['plan']['headers']['Authorization']=='Basic dTpwcml2YXRl'
    assert b's'*32 != bytes.fromhex(plan['result_key'])
    assert 'private' not in repr(receipt) and 'Authorization' not in repr(receipt)


@pytest.mark.parametrize('damage',['signature','body','status','headers','category','body_limit'])
def test_forged_or_invalid_worker_result_is_unconfirmed_and_cannot_be_replaced(admitted,damage):
    db,app,receipt,response,root,plan,request=admitted
    bad=dict(response)
    if damage=='signature':bad['signature']='0'*64
    else:
        if damage=='body':bad['body_base64']='!'
        elif damage=='status':bad['http_status']=True
        elif damage=='headers':bad['headers']={'Set-Cookie':'forbidden'}
        elif damage=='category':bad['error_category']='private error detail'
        elif damage=='body_limit':bad['body_base64']=base64.b64encode(b'x'*(receipt['max_response_bytes']+1)).decode()
        bad=sign(bad,bytes.fromhex(plan['result_key']))
    result=finish(admitted,response=bad)
    assert result['result']['outcome']=='ambiguous' and result['result']['error_category']=='execution_unconfirmed'
    assert finish(admitted)['result']['outcome']=='ambiguous'


@pytest.mark.parametrize('damage',['signature','owner','attempt','deadline'])
def test_tampered_receipt_never_settles_a_durable_attempt(admitted,damage):
    db,app,receipt,response,root,plan,request=admitted
    bad=dict(receipt)
    if damage=='signature':bad['signature']='0'*64
    elif damage=='owner':bad['instance_id']='2'*24
    elif damage=='attempt':bad['attempt_id']+=1
    else:bad['deadline_ms']=0
    with pytest.raises((ValueError,FileNotFoundError)):finish(admitted,receipt=bad)
    assert db.scalar(select(Attempt)).outcome=='in_progress'
    assert finish(admitted)['result']['outcome']=='succeeded'


def test_foreign_runtime_generation_cannot_finish_original_attempt(admitted):
    with pytest.raises(ValueError,match='owner'):finish(admitted,generation='b'*32)
    assert finish(admitted)['result']['outcome']=='succeeded'


def test_expired_or_rebooted_attempt_becomes_unknown_without_resending(admitted,monkeypatch):
    from backend.services import application_connector_transport as transport
    db,app,receipt,response,root,plan,request=admitted
    monkeypatch.setattr(transport,'clock',lambda:('different-boot',0))
    expire_connector_attempts(db,app.id)
    assert db.scalar(select(Attempt)).outcome=='ambiguous'
    assert finish(admitted)['result']['outcome']=='ambiguous'


def test_key_rotation_cannot_validate_an_old_result(admitted):
    db,app,receipt,response,root,plan,request=admitted
    (root/(app.instance_id+'.key')).write_bytes(b'z'*32)
    with pytest.raises(ValueError,match='signature'):finish(admitted)
    assert db.scalar(select(Attempt)).outcome=='in_progress'


def test_wrong_kernel_worker_identity_receives_no_target_credential(connector_db,tmp_path):
    db,app=connector_db
    credential=create_credential(db,app,label='network',credential_kind='basic',value={'username':'u','password':'private'})
    bind_connector(db,app,'business_api','https://example.test',credential.secret_ref)
    path=tmp_path/'wrong.sock';listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);listener.bind(str(path));listener.listen(1)
    captured=[]
    def accept():
        connection,_=listener.accept()
        with connection:captured.append(connection.recv(1024))
    thread=threading.Thread(target=accept);thread.start()
    result=begin_connector(db,app,{'request_id':'sdk_one','connector_request_id':'connector_'+uuid.uuid4().hex,
        'connector_id':'business_api','method':'POST','path':'/api/records','headers':{},'body_base64':'','idempotency_key':'one'},
        secret=b's'*32,runtime_generation='a'*32,worker_path=path,worker_uid=os.geteuid()+1)
    thread.join(timeout=3);listener.close()
    assert result['outcome']=='ambiguous' and captured==[b'']


def test_expired_duplicate_is_reconciled_even_behind_full_unexpired_status_batch(connector_db,tmp_path):
    from backend.services.application_connector_transport import clock
    db,app=connector_db;boot,now=clock()
    for index in range(101):
        db.add(Attempt(request_id='connector_'+f'{index:032x}',application_installation_id=app.id,
            connector_id='business_api',method='POST',path_hash='a'*64,outcome='in_progress',
            dispatch_metadata={'boot_id':boot,'deadline_ms':now-1 if index==100 else now+100000}))
    db.commit()
    result=begin_connector(db,app,{'request_id':'sdk_duplicate','connector_request_id':'connector_'+f'{100:032x}',
        'connector_id':'business_api','method':'POST','path':'/api/check','headers':{},'body_base64':'','idempotency_key':'one'},
        secret=b's'*32,runtime_generation='a'*32,worker_path=tmp_path/'absent.sock',worker_uid=os.geteuid())
    assert result['duplicate'] and result['outcome']=='ambiguous'
    assert len(list(db.scalars(select(Attempt))))==101


def test_network_executor_rejects_an_untrusted_tls_certificate_before_http(tmp_path):
    from datetime import datetime,UTC,timedelta
    import ssl
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from three_mm_platform_runtime.connector_worker import execute
    key=ec.generate_private_key(ec.SECP256R1());name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')])
    now=datetime.now(UTC)
    certificate=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1))
        .not_valid_after(now+timedelta(minutes=5)).sign(key,hashes.SHA256()))
    cert=tmp_path/'server.crt';cert.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    private=tmp_path/'server.pem';private.write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,private)
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1);listener.settimeout(3)
    received=[]
    def accept():
        connection,_=listener.accept()
        with connection:
            try:
                with context.wrap_socket(connection,server_side=True) as secured:received.append(secured.recv(1024))
            except ssl.SSLError:pass
    worker=threading.Thread(target=accept);worker.start()
    try:
        result=execute({'method':'POST','url':f'https://127.0.0.1:{listener.getsockname()[1]}/api/check',
            'body_base64':'','headers':{'Authorization':'Basic private'},'timeout_seconds':1,'max_response_bytes':1024})
        assert result['outcome']=='ambiguous' and result['body_base64']=='' and received==[]
    finally:worker.join(timeout=3);listener.close()
