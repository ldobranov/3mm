"""Optional Node TLS executor, independent of Core and its database/private key.

Uses the existing paired Agent identity/credential and pinned Hub public identity.
Provider bytes/factory are root-owned reviewed configuration, not network input.
Every provider runs through the existing socket-activated OS-isolated worker.
"""
from __future__ import annotations
import argparse
import asyncio
import base64
from datetime import UTC,datetime
import hashlib
import json
import os
from pathlib import Path
import socket
import ssl
import stat
import subprocess
import time

from three_mm_protocol.device_authority import DeviceAuthorityStore
from three_mm_protocol.device_capabilities import CapabilityProviderReportV1
from three_mm_protocol.capability_availability import CapabilityAvailabilityReportV1,declaration_digest
from three_mm_protocol.application_sessions import SessionContractV1
from three_mm_runtime.session_link import SessionLinkServer,node_execution_empty
from three_mm_runtime.session_link_config import configuration,protected_bytes,unchanged
from three_mm_runtime.session_worker import validate_wheel
from three_mm_runtime.session_worker_client import SandboxedSessionProvider,SOCKET_PATH

SUPPORT = Path('/run/3mm-session-node/support.json')


def paired_hub_certificate(path,binding):
    certificate = protected_bytes(path,limit=8192)
    public = subprocess.run(['/usr/bin/openssl','x509','-pubkey','-noout'],input=certificate,
        capture_output=True,timeout=5,check=True).stdout
    der = subprocess.run(['/usr/bin/openssl','pkey','-pubin','-outform','DER'],input=public,
        capture_output=True,timeout=5,check=True).stdout
    expected = bytes.fromhex('302a300506032b6570032100') + base64.b64decode(binding.installation.public_key,validate=True)
    if der != expected:
        raise ValueError('TLS Hub certificate differs from existing authority pin')
    return certificate


def worker_available():
    try:
        for path in (SOCKET_PATH,*SOCKET_PATH.parents):
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & (0o002 if path==SOCKET_PATH else 0o022):
                return False
        return stat.S_ISSOCK(SOCKET_PATH.lstat().st_mode)
    except OSError:
        return False


class SessionNode:
    def __init__(self,path):
        self.path=Path(path);value,self.digest=configuration(path)
        if set(value) != {'version','device_id','data_dir','hub_certificate','certificate','key','listen','port','provider'}:
            raise ValueError('Invalid Node session configuration fields')
        self.value=value
        data=Path(value['data_dir'])
        # Existing credential is consumed only by the existing signed device HTTP adapter.
        from agent.credentials import DeviceCredentialStore
        self.credential=DeviceCredentialStore(data).load(read_only=True)
        if self.credential is None or not (self.credential.api_endpoint or self.credential.hub_endpoint):
            raise ValueError('Existing paired Hub endpoint required')
        if self.credential.device_id != value['device_id']:
            raise ValueError('Node identity differs from paired credential')
        self.authority=DeviceAuthorityStore(data,value['device_id'],self.credential.credential_id)
        binding=self.authority.check_current()
        if binding is None or binding.installation is None or str(binding.lifecycle) not in {'active','degraded'}:
            raise ValueError('Existing paired Hub authority required')
        hub_certificate=paired_hub_certificate(value['hub_certificate'],binding)
        self.tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.tls.minimum_version=ssl.TLSVersion.TLSv1_3
        self.tls.verify_mode=ssl.CERT_REQUIRED
        self.tls.load_verify_locations(cadata=hub_certificate.decode('ascii'))
        protected_bytes(value['certificate'],limit=8192);protected_bytes(value['key'],limit=8192)
        self.tls.load_cert_chain(value['certificate'],value['key'])
        provider=value['provider']
        if set(provider) != {'id','version','capability_id','wheel','sha256','factory','contract'}:
            raise ValueError('Invalid configured provider fields')
        self.contract=SessionContractV1.model_validate_json(json.dumps(provider['contract']),strict=True)
        self.wheel=protected_bytes(provider['wheel'],limit=10*1024*1024)
        validate_wheel(self.wheel,provider['sha256'])
        self.cert=protected_bytes(value['certificate'],limit=8192)
        self.peer_sha256=hashlib.sha256(ssl.PEM_cert_to_DER_cert(self.cert.decode('ascii'))).hexdigest()
        self.provider=provider
        self.server=SessionLinkServer(device_id=value['device_id'],provider_id=provider['id'],provider_version=provider['version'],
            capability_id=provider['capability_id'],artifact_sha256=provider['sha256'],access_modes=self.contract.access_modes,
            control_actions=self.contract.control_actions,provider_factory=self.create_provider,check_current=self.current,cleanup_status=node_execution_empty)
        self.stop=asyncio.Event()

    def current(self):
        try:
            binding=self.authority.check_current()
            return (unchanged(self.path,self.digest) and binding is not None
                and str(binding.lifecycle) in {'active','degraded'} and worker_available()
                and protected_bytes(self.value['certificate'],limit=8192)==self.cert)
        except (OSError,ValueError):
            return False

    def create_provider(self):
        if not self.current():
            raise ValueError('Node session execution is unavailable')
        return SandboxedSessionProvider(wheel=self.wheel,factory=self.provider['factory'],provider_id=self.provider['id'])

    def _support(self):
        if not self.current():
            SUPPORT.unlink(missing_ok=True)
            return
        SUPPORT.parent.mkdir(exist_ok=True,mode=0o755)
        from three_mm_runtime.component_identity import component_health
        identity=component_health()
        if identity is None or identity.get('component')!='session-node':
            raise ValueError('Installed Session Node component identity required')
        value={'version':1,'device_id':self.value['device_id'],'generation':self.server.generation,'expires_at':time.time()+10,**identity}
        temporary=SUPPORT.with_suffix('.tmp')
        fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o644)
        try:
            with os.fdopen(fd,'w') as stream:json.dump(value,stream)
            os.replace(temporary,SUPPORT)
        finally:
            temporary.unlink(missing_ok=True)

    def report(self,transport,*,register=False):
        provider=self.provider
        metadata={'interactive_session_contract':json.dumps(self.contract.model_dump(mode='json'),sort_keys=True,separators=(',',':')),
                  'session_link_sha256':self.peer_sha256,'session_provider_sha256':provider['sha256'],'session_profile':'isolated_session_v1'}
        capabilities=[{'capability_id':provider['capability_id'],'metadata':metadata}]
        if register:
            suffix='capability-providers/session_runtime/'+provider['id']
            prior=transport._request('get',suffix,legacy_missing=True)
            revision=prior.json()['revision'] if prior is not None else 0
            report=CapabilityProviderReportV1(schema_version=1,device_id=self.value['device_id'],provider_type='session_runtime',
                provider_id=provider['id'],provider_version=provider['version'],expected_revision=revision,capabilities=capabilities)
            transport.publish(report)
        health=CapabilityAvailabilityReportV1(device_id=self.value['device_id'],provider_type='session_runtime',
            provider_id=provider['id'],provider_version=provider['version'],
            declaration_digest=declaration_digest('session_runtime',provider['id'],provider['version'],capabilities),
            observed_at=datetime.now(UTC),valid_for_seconds=10,
            capabilities=[{'capability_id':provider['capability_id'],'healthy':self.current()}])
        transport.publish(health)

    async def publish(self):
        from agent.device_transport import HttpDeviceTransport
        endpoint=self.credential.api_endpoint or self.credential.hub_endpoint
        transport=HttpDeviceTransport(endpoint,self.credential,authority_store=self.authority)
        registered=False
        while not self.stop.is_set():
            self._support()
            try:
                await asyncio.to_thread(self.report,transport,register=not registered)
                registered=True
            except Exception:
                pass  # Missing health expires; never log credential/provider exception text.
            try:await asyncio.wait_for(self.stop.wait(),3)
            except TimeoutError:pass

    async def run(self):
        server=await asyncio.start_server(self.server.handle,self.value['listen'],self.value['port'],ssl=self.tls,
            ssl_handshake_timeout=5,limit=65536)
        publisher=asyncio.create_task(self.publish())
        try:
            async with server:await server.serve_forever()
        finally:
            self.stop.set();publisher.cancel()
            await asyncio.gather(publisher,return_exceptions=True)
            await self.server.close()
            SUPPORT.unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='/etc/3mm-session-node/config.json')
    args=parser.parse_args()
    asyncio.run(SessionNode(args.config).run())


if __name__=='__main__':
    main()
