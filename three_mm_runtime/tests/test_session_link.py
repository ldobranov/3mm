"""Real TLS1.3 + SDK channel + transparent relay; disposable providers only.

These tests prove channel identity/streaming/fencing, not physical Node/OS
isolation. Real worker cgroup proof has its separate explicit Linux acceptance.
"""
import asyncio
import base64
from datetime import UTC,datetime,timedelta
import hashlib
from pathlib import Path
import secrets
import ssl
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.x509.oid import NameOID,ExtendedKeyUsageOID

from backend.services.installation_session_tls import installation_certificate
from three_mm_runtime.session_link import RemoteSessionProvider,SessionLinkServer
from three_mm_runtime.session_relay import SessionByteRelay
from three_mm_runtime.session_worker import read_packet,write_packet

DEVICE='dev_'+'a'*32
PROVIDER='org.example.counter'
CAPABILITY='org.example.counter.session'
ARTIFACT='c'*64
CONTEXT={'session_id':'ses_'+'d'*32,'device_id':DEVICE,'capability_id':CAPABILITY,'access_mode':'write','options':{'cols':80,'rows':24}}


def pem_key(key):
    return key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())


def node_certificate(key,name):
    now=datetime.now(UTC).replace(tzinfo=None)
    subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,name)])
    return (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True)
        .add_extension(x509.KeyUsage(True,False,False,False,False,True,True,False,False),critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),critical=False)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]),critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()),critical=False)
        .sign(key,algorithm=None).public_bytes(serialization.Encoding.PEM))


@pytest.fixture
def certificates(tmp_path):
    hub=Ed25519PrivateKey.generate();node=Ed25519PrivateKey.generate()
    public=hub.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    identity=SimpleNamespace(installation_id='inst_'+'b'*32,key_id=hashlib.sha256(public).hexdigest(),created_at=datetime.now(UTC))
    hub_pem=installation_certificate(identity,hub);node_pem=node_certificate(node,DEVICE)
    for name,data in [('hub.pem',hub_pem),('hub.key',pem_key(hub)),('node.pem',node_pem),('node.key',pem_key(node))]:
        path=tmp_path/name;path.write_bytes(data);path.chmod(0o600)
    server=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);server.minimum_version=ssl.TLSVersion.TLSv1_3
    server.load_cert_chain(str(tmp_path/'node.pem'),str(tmp_path/'node.key'))
    server.load_verify_locations(cadata=hub_pem.decode());server.verify_mode=ssl.CERT_REQUIRED
    def client(*,authenticate=True,certificate=node_pem):
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);context.minimum_version=ssl.TLSVersion.TLSv1_3
        context.load_verify_locations(cadata=certificate.decode())
        if authenticate:context.load_cert_chain(str(tmp_path/'hub.pem'),str(tmp_path/'hub.key'))
        return context
    return SimpleNamespace(server=server,client=client,node_pem=node_pem,hub_pem=hub_pem,
        sha256=hashlib.sha256(ssl.PEM_cert_to_DER_cert(node_pem.decode())).hexdigest())


class Counter:
    def __init__(self,fail_close=False):
        self.opened=[];self.inputs=[];self.controls=[];self.closed=[];self.fail_close=fail_close
        self.cgroup='/system.slice/system-3mm-session-worker-node.slice/3mm-session-worker-node@fixture.service'
    async def open(self,context):
        self.opened.append(context);self.queue=asyncio.Queue(maxsize=1);self.queue.put_nowait(b'counter ready')
    async def receive(self,sid,data):
        self.inputs.append(data);return b'counter:'+data
    async def read_output(self,sid):return await self.queue.get()
    async def control(self,sid,value):self.controls.append(value)
    async def close(self,sid,reason):
        self.closed.append(sid)
        if self.fail_close:raise RuntimeError('Fixture cleanup unknown')


async def stack(certificates,*,relay=False,fail_close=False):
    provider=Counter(fail_close)
    endpoint=SessionLinkServer(device_id=DEVICE,provider_id=PROVIDER,provider_version='1.0.0',capability_id=CAPABILITY,
        artifact_sha256=ARTIFACT,access_modes=('write',),control_actions=('resize',),provider_factory=lambda:provider,check_current=lambda:True,
        cleanup_status=lambda execution: execution in (None,provider.cgroup) and bool(provider.closed) and not provider.fail_close)
    server=await asyncio.start_server(endpoint.handle,'127.0.0.1',0,ssl=certificates.server,ssl_handshake_timeout=2)
    port=server.sockets[0].getsockname()[1];proxy=proxy_server=None
    if relay:
        proxy=SessionByteRelay('127.0.0.1',port)
        proxy_server=await asyncio.start_server(proxy.handle,'127.0.0.1',0)
        port=proxy_server.sockets[0].getsockname()[1]
    remote=RemoteSessionProvider(host='127.0.0.1',port=port,device_id=DEVICE,provider_id=PROVIDER,provider_version='1.0.0',
        capability_id=CAPABILITY,artifact_sha256=ARTIFACT,peer_sha256=certificates.sha256,tls=certificates.client(),current=lambda:True)
    async def stop():
        if proxy_server is not None:
            proxy_server.close();await proxy_server.wait_closed();await proxy.close()
        server.close();await server.wait_closed();await endpoint.close()
    return SimpleNamespace(provider=provider,endpoint=endpoint,remote=remote,port=port,stop=stop,proxy=proxy)


@pytest.mark.parametrize('relay',[False,True])
def test_real_tls_binary_delayed_output_resize_and_confirmed_close(certificates,relay):
    async def run():
        s=await stack(certificates,relay=relay)
        try:
            await s.remote.open(dict(CONTEXT))
            assert await s.remote.read_output(CONTEXT['session_id'])==b'counter ready'
            assert await s.remote.receive(CONTEXT['session_id'],b'one')==b'counter:one'
            read=asyncio.create_task(s.remote.read_output(CONTEXT['session_id']))
            await asyncio.sleep(.02);assert not read.done()
            s.provider.queue.put_nowait(b'delayed')
            assert await read==b'delayed'
            await s.remote.control(CONTEXT['session_id'],{'action':'resize','arguments':{'cols':99,'rows':31}})
            assert s.provider.controls==[{'action':'resize','arguments':{'cols':99,'rows':31}}]
            await s.remote.close(CONTEXT['session_id'],'test')
            assert s.provider.closed==[CONTEXT['session_id']] and s.remote.confirmed_empty
            assert not s.endpoint.active
        finally:await s.stop()
    asyncio.run(run())


def test_missing_hub_certificate_cannot_reach_provider(certificates):
    async def run():
        s=await stack(certificates)
        try:
            with pytest.raises((OSError,ConnectionError,ssl.SSLError,asyncio.IncompleteReadError)):
                reader,writer=await asyncio.open_connection('127.0.0.1',s.port,ssl=certificates.client(authenticate=False),server_hostname=DEVICE)
                try:
                    await write_packet(writer,{'session_link_version':1})
                    await asyncio.wait_for(read_packet(reader),2)
                finally:
                    writer.close()
            assert not s.provider.opened and not s.endpoint.spent
        finally:await s.stop()
    asyncio.run(run())


def test_wrong_node_certificate_or_pin_never_opens_provider(certificates):
    async def run():
        s=await stack(certificates)
        try:
            s.remote.peer_sha256='f'*64
            with pytest.raises(RuntimeError,match='peer changed'):await s.remote.open(dict(CONTEXT))
            assert not s.provider.opened
            with pytest.raises(RuntimeError,match='open unavailable'):await s.remote.open(dict(CONTEXT))
        finally:await s.stop()
    asyncio.run(run())


def test_network_cannot_supply_wheel_factory_or_target(certificates):
    async def run():
        s=await stack(certificates)
        try:
            reader,writer=await asyncio.open_connection('127.0.0.1',s.port,ssl=certificates.client(),server_hostname=DEVICE)
            await write_packet(writer,{'session_link_version':1,'provider_id':PROVIDER,'provider_version':'1.0.0',
                'artifact_sha256':ARTIFACT,'context':CONTEXT,'factory':'os:system'})
            with pytest.raises(asyncio.IncompleteReadError):await asyncio.wait_for(read_packet(reader),2)
            assert not s.provider.opened
            writer.close();await writer.wait_closed()
        finally:await s.stop()
    asyncio.run(run())


def test_unconfirmed_remote_cleanup_is_fenced_and_not_replayed(certificates):
    async def run():
        s=await stack(certificates,fail_close=True)
        try:
            await s.remote.open(dict(CONTEXT));assert await s.remote.read_output(CONTEXT['session_id'])==b'counter ready'
            with pytest.raises((RuntimeError,ConnectionError,asyncio.IncompleteReadError)):
                await s.remote.close(CONTEXT['session_id'],'test')
            assert not s.remote.confirmed_empty and s.endpoint.active
            assert len(s.provider.opened)==1 and not s.provider.inputs
        finally:await s.stop()
    asyncio.run(run())


def test_relay_loss_closes_node_without_reopening_or_replaying_input(certificates):
    async def run():
        s=await stack(certificates,relay=True)
        try:
            await s.remote.open(dict(CONTEXT));assert await s.remote.read_output(CONTEXT['session_id'])==b'counter ready'
            pending=asyncio.create_task(s.remote.read_output(CONTEXT['session_id']))
            await s.proxy.close()
            with pytest.raises(RuntimeError):await asyncio.wait_for(pending,2)
            for _ in range(20):
                if s.provider.closed:break
                await asyncio.sleep(.02)
            assert s.provider.closed==[CONTEXT['session_id']]
            assert len(s.provider.opened)==1 and not s.provider.inputs
            with pytest.raises(RuntimeError):await s.remote.close(CONTEXT['session_id'],'test')
            # A new TLS read-only query can confirm the old exact worker; no input/open replay.
            await s.remote.confirm_cleanup()
            assert s.remote.confirmed_empty and len(s.provider.opened)==1 and not s.provider.inputs
        finally:await s.stop()
    asyncio.run(run())


def test_tls_failure_before_any_open_is_confirmed_empty_without_fencing(certificates):
    async def run():
        s=await stack(certificates)
        try:
            s.remote.peer_sha256='f'*64
            with pytest.raises(RuntimeError):await s.remote.open(dict(CONTEXT))
            assert not s.remote.bootstrap_sent and not s.provider.opened
            await s.remote.close(CONTEXT['session_id'],'test')
            assert s.remote.confirmed_empty and not s.endpoint.active
        finally:await s.stop()
    asyncio.run(run())


def test_read_only_os_proof_releases_the_same_node_fence_without_restarting(certificates):
    async def run():
        s=await stack(certificates,fail_close=True)
        try:
            await s.remote.open(dict(CONTEXT));await s.remote.read_output(CONTEXT['session_id'])
            with pytest.raises(RuntimeError):await s.remote.close(CONTEXT['session_id'],'test')
            assert s.endpoint.active
            s.provider.fail_close=False  # Fixture now supplies OS-empty evidence.
            await s.remote.confirm_cleanup()
            assert not s.endpoint.active and s.remote.confirmed_empty
            assert len(s.provider.opened)==1 and not s.provider.inputs
        finally:await s.stop()
    asyncio.run(run())


def test_lost_startup_execution_id_requires_global_node_worker_absence(certificates):
    async def run():
        s=await stack(certificates,relay=True)
        try:
            await s.remote.open(dict(CONTEXT));await s.remote.read_output(CONTEXT['session_id'])
            await s.proxy.close()
            await asyncio.sleep(.03)
            s.remote.execution_id=None
            await s.remote.confirm_cleanup()
            assert s.remote.confirmed_empty and s.provider.closed==[CONTEXT['session_id']]
            assert len(s.provider.opened)==1
        finally:await s.stop()
    asyncio.run(run())


def test_cleanup_cannot_confirm_before_pending_open_creates_its_worker(certificates):
    async def run():
        s=await stack(certificates)
        entered,continue_open=asyncio.Event(),asyncio.Event()
        original=s.provider.open
        async def delayed_open(context):
            entered.set()
            await continue_open.wait()
            await original(context)
        s.provider.open=delayed_open
        s.endpoint.cleanup_status=lambda execution:True  # No cgroup exists yet.
        opening=asyncio.create_task(s.remote.open(dict(CONTEXT)))
        try:
            await asyncio.wait_for(entered.wait(),2)
            with pytest.raises(RuntimeError,match='unconfirmed'):
                await s.remote.confirm_cleanup()
            assert not s.remote.confirmed_empty and not s.provider.opened
            continue_open.set()
            await opening
            await s.remote.close(CONTEXT['session_id'],'test')
        finally:
            continue_open.set()
            await asyncio.gather(opening,return_exceptions=True)
            await s.stop()
    asyncio.run(run())


def test_cleanup_barrier_blocks_a_late_hello_for_the_same_identity(certificates):
    async def run():
        s=await stack(certificates)
        s.endpoint.cleanup_status=lambda execution:True
        try:
            # The caller lost startup confirmation; its original hello can still
            # be buffered/unparsed when this separate cleanup connection arrives.
            s.remote.session_id=CONTEXT['session_id'];s.remote.bootstrap_sent=True
            await s.remote.confirm_cleanup()
            assert s.remote.confirmed_empty
            reader,writer=await asyncio.open_connection('127.0.0.1',s.port,ssl=certificates.client(),server_hostname=DEVICE)
            try:
                await write_packet(writer,{'session_link_version':1,'provider_id':PROVIDER,'provider_version':'1.0.0',
                    'artifact_sha256':ARTIFACT,'context':CONTEXT})
                with pytest.raises(asyncio.IncompleteReadError):
                    await asyncio.wait_for(read_packet(reader),2)
            finally:
                writer.close();await writer.wait_closed()
            assert not s.provider.opened and not s.endpoint.active
        finally:await s.stop()
    asyncio.run(run())


def test_uncertain_local_start_without_execution_identity_cannot_clear_node_fence(certificates):
    async def run():
        s=await stack(certificates,fail_close=True)
        s.provider.cgroup=None
        async def failed_open(context):
            s.provider.opened.append(context)
            raise RuntimeError('Local socket startup unconfirmed')
        s.provider.open=failed_open
        s.endpoint.cleanup_status=lambda execution:True  # Does not see queued jobs.
        try:
            with pytest.raises(asyncio.IncompleteReadError):await s.remote.open(dict(CONTEXT))
            assert s.endpoint.active and s.endpoint._fenced and s.remote.execution_id is None
            with pytest.raises(RuntimeError,match='unconfirmed'):await s.remote.confirm_cleanup()
            assert s.endpoint.active and not s.remote.confirmed_empty
            assert len(s.provider.opened)==1
        finally:await s.stop()
    asyncio.run(run())


def test_missing_remote_execution_identity_uses_known_fenced_node_execution(certificates):
    async def run():
        s=await stack(certificates,fail_close=True)
        observed=[]
        try:
            await s.remote.open(dict(CONTEXT));await s.remote.read_output(CONTEXT['session_id'])
            with pytest.raises(RuntimeError):await s.remote.close(CONTEXT['session_id'],'test')
            s.remote.execution_id=None
            s.endpoint.cleanup_status=lambda execution:observed.append(execution) or True
            await s.remote.confirm_cleanup()
            assert observed==[s.provider.cgroup]
            assert s.remote.confirmed_empty and not s.endpoint.active
        finally:await s.stop()
    asyncio.run(run())


def test_hub_tls_disconnect_cancels_and_joins_pending_node_startup(certificates):
    async def run():
        s=await stack(certificates)
        entered,cancelled=asyncio.Event(),asyncio.Event()
        attempts=[]
        async def pending_open(context):
            attempts.append(context['session_id']);entered.set()
            try:await asyncio.Event().wait()
            finally:cancelled.set()
        s.provider.open=pending_open
        opening=asyncio.create_task(s.remote.open(dict(CONTEXT)))
        try:
            await asyncio.wait_for(entered.wait(),2)
            opening.cancel()
            await asyncio.gather(opening,return_exceptions=True)
            await asyncio.wait_for(cancelled.wait(),3)
            for _ in range(100):
                if s.provider.closed:break
                await asyncio.sleep(.01)
            assert attempts==[CONTEXT['session_id']] and not s.provider.opened and not s.provider.inputs
            assert s.provider.closed==[CONTEXT['session_id']]
            assert not s.endpoint.active
            with pytest.raises(RuntimeError):await s.remote.close(CONTEXT['session_id'],'test')
            await s.remote.confirm_cleanup()
            assert s.remote.confirmed_empty and attempts==[CONTEXT['session_id']]
        finally:
            opening.cancel();await asyncio.gather(opening,return_exceptions=True)
            await s.stop()
    asyncio.run(run())


def test_node_currentness_drift_cancels_pending_startup_without_replay(certificates):
    async def run():
        s=await stack(certificates)
        current=[True];s.endpoint.check_current=lambda:current[0]
        entered,cancelled=asyncio.Event(),asyncio.Event()
        attempts=[]
        async def pending_open(context):
            attempts.append(context['session_id']);entered.set()
            try:await asyncio.Event().wait()
            finally:cancelled.set()
        s.provider.open=pending_open
        opening=asyncio.create_task(s.remote.open(dict(CONTEXT)))
        try:
            await asyncio.wait_for(entered.wait(),2)
            current[0]=False
            await asyncio.wait_for(cancelled.wait(),3)
            with pytest.raises(asyncio.IncompleteReadError):await asyncio.wait_for(opening,3)
            assert attempts==[CONTEXT['session_id']] and not s.provider.opened and not s.provider.inputs
            assert s.provider.closed==[CONTEXT['session_id']] and not s.endpoint.active
            current[0]=True  # Explicitly restored Node state, not a replay.
            await s.remote.confirm_cleanup()
            assert s.remote.confirmed_empty and attempts==[CONTEXT['session_id']]
        finally:
            opening.cancel();await asyncio.gather(opening,return_exceptions=True)
            await s.stop()
    asyncio.run(run())


def test_premature_tls_input_aborts_pending_node_startup(certificates):
    async def run():
        s=await stack(certificates)
        entered,cancelled=asyncio.Event(),asyncio.Event()
        attempts=[]
        async def pending_open(context):
            attempts.append(context['session_id']);entered.set()
            try:await asyncio.Event().wait()
            finally:cancelled.set()
        s.provider.open=pending_open
        writer=None
        try:
            reader,writer=await asyncio.open_connection('127.0.0.1',s.port,ssl=certificates.client(),server_hostname=DEVICE)
            await write_packet(writer,{'session_link_version':1,'provider_id':PROVIDER,'provider_version':'1.0.0',
                'artifact_sha256':ARTIFACT,'context':CONTEXT})
            await asyncio.wait_for(entered.wait(),2)
            writer.write(b'x');await writer.drain()
            await asyncio.wait_for(cancelled.wait(),3)
            with pytest.raises(asyncio.IncompleteReadError):await asyncio.wait_for(read_packet(reader),3)
            assert attempts==[CONTEXT['session_id']] and not s.provider.inputs
            assert s.provider.closed==[CONTEXT['session_id']] and not s.endpoint.active
        finally:
            if writer is not None:
                writer.close();await writer.wait_closed()
            await s.stop()
    asyncio.run(run())
