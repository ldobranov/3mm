"""Root-configured exact Node routes behind the common M20 runtime boundary.

A route is an executor connection, never an authority grant. Device/provider/
wheel/TLS declarations must also be current in the ONE capability registry and
sealed into the M20 session resource. No user payload selects an address/cert.
"""
import hashlib
import os
from pathlib import Path
import re
import ssl

from sqlalchemy import select

from backend.db.device import Device
from backend.services.device_capability_registry import registered_capabilities
from backend.services.application_session_runtimes import ReviewedSessionRuntime
from backend.services.installation_session_tls import installation_client_context,current_installation_identity
from three_mm_runtime.session_link import RemoteSessionProvider
from three_mm_runtime.session_link_config import configuration, protected_bytes, unchanged

CONFIGURATION = Path('/etc/3mm/session-links.json')


class RemoteSessionRuntime:
    def __init__(self, config_path, config_digest, value):
        if set(value) != {'device_id','provider_id','provider_version','capability_id',
                          'artifact_sha256','certificate','host','port'}:
            raise ValueError('Invalid session link route fields')
        for field, pattern in (('device_id', r'dev_[0-9a-f]{32}'),
                               ('provider_id', r'[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,159}'),
                               ('capability_id', r'[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,159}'),
                               ('artifact_sha256', r'[0-9a-f]{64}')):
            if type(value[field]) is not str or re.fullmatch(pattern,value[field]) is None:
                raise ValueError('Invalid session link identity')
        if (type(value['host']) is not str or not value['host'] or len(value['host']) > 255
            or any(c in value['host'] for c in '/\\@?#\x00')
            or type(value['port']) is not int or not 1 <= value['port'] <= 65535
            or type(value['provider_version']) is not str or not 1 <= len(value['provider_version']) <= 64):
            raise ValueError('Invalid fixed session link endpoint')
        self.config_path, self.config_digest, self.value = config_path, config_digest, dict(value)
        self.certificate = protected_bytes(value['certificate'],limit=8192).decode('ascii')
        self.peer_sha256 = hashlib.sha256(ssl.PEM_cert_to_DER_cert(self.certificate)).hexdigest()

    def current(self):
        try:
            return unchanged(self.config_path,self.config_digest) and protected_bytes(
                self.value['certificate'],limit=8192).decode('ascii') == self.certificate
        except (OSError,ValueError):
            return False

    def available(self, db, resource):
        v = self.value
        if not self.current() or (
            resource['target_device_id'],resource['declaration']['provider_id'],
            resource['provider_version'],resource['declaration']['capability_id'],
        ) != (v['device_id'],v['provider_id'],v['provider_version'],v['capability_id']):
            return False
        device = db.scalar(select(Device).where(Device.device_id == v['device_id']))
        if device is None:
            return False
        return any(row['provider_id'] == v['provider_id'] and row['provider_version'] == v['provider_version']
                   and row['capability_id'] == v['capability_id']
                   and row.get('metadata',{}).get('session_link_sha256') == self.peer_sha256
                   and row.get('metadata',{}).get('session_provider_sha256') == v['artifact_sha256']
                   and row.get('metadata',{}).get('session_profile') == 'isolated_session_v1'
                   for row in registered_capabilities(db,device))

    def resolve(self, engine, resource):
        v = self.value
        tls, identity = installation_client_context(engine,self.certificate)
        current = lambda: self.current() and current_installation_identity(engine,identity)
        provider = RemoteSessionProvider(host=v['host'],port=v['port'],device_id=v['device_id'],
            provider_id=v['provider_id'],provider_version=v['provider_version'],
            capability_id=v['capability_id'],artifact_sha256=v['artifact_sha256'],
            peer_sha256=self.peer_sha256,tls=tls,current=current)
        return ReviewedSessionRuntime(v['device_id'],v['provider_id'],v['provider_version'],
            resource['control_revision'],provider,provider.is_current)


class ConfiguredRemoteSessions:
    """Hot reload ROOT declarations; old per-session generations remain pinned."""
    def _entries(self):
        value, digest = configuration(CONFIGURATION)
        peers = value.get('peers')
        if set(value) != {'version','peers'} or type(peers) is not list or not 1 <= len(peers) <= 7:
            raise ValueError('Invalid session link configuration')
        return tuple(RemoteSessionRuntime(CONFIGURATION,digest,peer) for peer in peers)

    def _select(self, db, resource):
        matches = [entry for entry in self._entries() if entry.available(db,resource)]
        if len(matches)>1:
            raise ValueError('Ambiguous configured Node routes')
        return matches[0] if matches else None

    def available(self, db, resource):
        return self._select(db, resource) is not None

    def resolve(self, engine, resource):
        from sqlalchemy.orm import Session
        with Session(engine) as db:
            entry = self._select(db, resource)
        return entry.resolve(engine, resource) if entry is not None else None


def configured_remote_sources():
    # The directory is stable; root config and certificate changes invalidate old
    # sessions and are re-read for NEW requests, without restarting Core.
    return (ConfiguredRemoteSessions(),) if os.getenv('THREE_MM_SESSION_LINKS')=='1' else ()
