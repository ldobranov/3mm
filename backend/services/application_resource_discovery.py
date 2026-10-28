"""Read existing sealed resources, probe outside leases, then fence the result.

No registry, grant, namespace creation or business operation. Missing authority
returns redacted rows; provider observations never select a replacement resource.
"""
from datetime import UTC, datetime
import os
from pathlib import Path
import re
import stat

from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services import application_authority_management as authority
from backend.services.application_authority_sources import _read_snapshot, _package_pin
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services.authority_metadata import read_authority_guard, read_application_authority
from three_mm_protocol.application_resources import (
    ResourceDiscoveryRequestV1, ResourceDiscoveryV1, ResourceObservationV1, ResourceProviderV1,
)


def _redacted(scope, declared=None, *, required=True, reason=None):
    return ResourceObservationV1(scope=scope, declared=declared, configured=None,
        required=required, access='not_evaluated' if declared is False or reason == 'optional_resource_unavailable' else 'required',
        readiness='not_evaluated', reasons=(reason,) if reason else ('not_declared',) if declared is False else ('access_required',))


def _secret(instance_id):
    from backend.config import get_settings
    path = get_settings().applications.key_root / (instance_id + '.key')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size != 32: raise ValueError('Resource key unavailable')
        value = stream.read(33)
    if len(value) != 32: raise ValueError('Resource key unavailable')
    return value


def _binding(db, installation_id, prepared, subject, grant):
    return (read_authority_guard(db), read_application_authority(db, installation_id),
        _package_pin(db, installation_id), authority._resource_identity(subject), grant['revision'])


def _file_observation(runtime, declaration, prepared, secret, media):
    from three_mm_runtime.application_file_executor import call_file_executor
    from backend.services.application_files import ApplicationFileAuthorityError
    try:
        result = call_file_executor(runtime[1], secret, 'probe' if media else 'hello', {}, timeout=3)
        expected = {'instance_id', 'package_sha256', 'runtime_nonce', 'clock_ms', 'declaration'}
        if media: expected.add('media_provider')
        if (set(result) != expected or result['instance_id'] != runtime[0]
                or result['package_sha256'] != prepared.pin.sha256 or type(result['clock_ms']) is not int
                or type(result['runtime_nonce']) is not str or not re.fullmatch(r'[0-9a-f]{32}', result['runtime_nonce'])
                or authority._canonical_bytes(result['declaration']) != authority._canonical_bytes(declaration.model_dump(mode='json'))):
            raise ApplicationFileAuthorityError()
        provider = result.get('media_provider')
        if media and provider not in {'ready', 'unavailable', 'unknown'}: raise ApplicationFileAuthorityError()
        return provider if media else 'ready'
    except (FileNotFoundError, ConnectionRefusedError): return 'unavailable'
    except (OSError, ValueError, RuntimeError, TypeError, KeyError): return 'unknown'


def discover_resources(engine, installation_id, instance_id, scopes, *, transport_secret=None):
    query = ResourceDiscoveryRequestV1(scopes=tuple(scopes))
    manager = authority.configured_manager(engine)
    prepared = manager._prepare(installation_id)
    optional = set(prepared.package.application_extension.optional_resources)
    rows = {scope:_redacted(scope, True if scope in optional else None, required=scope not in optional) for scope in query.scopes}
    file_probe = sql_probe = None
    host_probe = None
    provider_kinds = set()
    try:
        with manager.keys.locked() as key, _read_snapshot(engine) as db:
            app = db.get(Installation, installation_id)
            if app is None or app.instance_id != instance_id or not app.enabled or app.status != 'active':
                raise ValueError('Resource installation is not active')
            subject = manager._subject(db, key, installation_id, prepared)
            declared = authority._subject_scopes(subject)
            rows = {scope:_redacted(scope, scope in declared or scope in optional, required=scope not in optional,
                reason='optional_resource_unavailable' if scope in optional and scope not in declared else None) for scope in query.scopes}
            grant = manager._require_current_grant(db, key, installation_id, prepared)
            selected = set(grant['data']['selection']['scopes'])
            fence = _binding(db, installation_id, prepared, subject, grant)
            for scope in query.scopes:
                if scope not in selected or scope not in declared: continue
                if not authority.optional_scope_current(subject, grant, scope):
                    rows[scope] = _redacted(scope, True, required=False, reason='resource_changed_review_required')
                    continue
                resource = declared[scope]
                row = dict(scope=scope, required=scope not in optional, declared=True, configured=True, access='granted',
                    readiness='unknown', reasons=('runtime_not_observed',))
                if scope.startswith('command:'):
                    from backend.db.device import Device
                    from backend.services.application_command_discovery import _candidate
                    from sqlalchemy import select
                    device = db.scalar(select(Device).where(Device.device_id == resource.target_device_id))
                    candidate = _candidate(db, resource.declaration, device, datetime.now(UTC))
                    row.update(readiness=candidate.readiness, reasons=tuple(candidate.blockers or
                        ([candidate.readiness_reason] if candidate.readiness_reason else [])), selected_resource_id=device.device_id)
                    if candidate.provider_id is not None:
                        row['provider'] = ResourceProviderV1(provider_type=candidate.provider_type,
                            provider_id=candidate.provider_id, provider_version=candidate.provider_version,
                            contract_version=candidate.contract_version)
                    if candidate.blockers: row.update(readiness='unavailable')
                elif scope.startswith('storage:private_files_'):
                    from backend.services.application_files import _runtime
                    file_probe = (_runtime(db, installation_id), resource.declaration)
                elif scope.startswith('storage:relational_'):
                    from backend.services.application_relational import runtime_status_binding
                    sql_probe = runtime_status_binding(db, installation_id, prepared, grant)
                elif scope.startswith('connector:'):
                    provider_kinds.add('connector')
                    row['provider'] = ResourceProviderV1(provider_type='platform_runtime', provider_id='http_connector', contract_version='1')
                elif scope.startswith('query:'):
                    provider_kinds.add('query')
                    row.update(selected_resource_id=resource.provider_instance_id,
                        provider=ResourceProviderV1(provider_type='application_query',
                            provider_id=resource.provider.module_id, provider_version=resource.provider_artifact.version,
                            contract_version=resource.declaration.contract.contract_version))
                elif scope.startswith(('event:', 'task:')):
                    from backend.services.application_files import _runtime
                    host_probe = (_runtime(db, installation_id), dict(app.configuration or {}))
                    kind = 'event' if scope.startswith('event:') else 'task'
                    provider_kinds.add(kind)
                    if kind == 'task':
                        row['provider'] = ResourceProviderV1(provider_type='platform_runtime', provider_id='bounded_task_v1', contract_version='1')
                    else:
                        from backend.db.device import Device
                        from backend.services.device_capability_registry import capability_catalog
                        from sqlalchemy import select
                        device = db.scalar(select(Device).where(Device.device_id == resource.source_device_id))
                        offers = [offer for offer in capability_catalog(db, device)
                            if offer.capability_id == resource.declaration.capability_id and offer.registered]
                        row['selected_resource_id'] = resource.source_device_id
                        if len(offers) == 1:
                            offer = offers[0]
                            state = 'ready' if offer.available is True else 'unknown' if offer.unavailable_reason in {'health_missing','health_stale','legacy_health_unknown'} else 'unavailable'
                            row.update(readiness=state, reasons=() if state == 'ready' else (offer.unavailable_reason or 'source_unavailable',),
                                provider=ResourceProviderV1(provider_type=offer.provider_type,provider_id=offer.provider_id,
                                    provider_version=offer.provider_version,contract_version=offer.contract_version))
                        else: row.update(readiness='unavailable', reasons=('provider_ambiguous',))
                elif scope.startswith(('publication:', 'status:', 'peer:')):
                    row.update(readiness='ready', reasons=(), provider=ResourceProviderV1(
                        provider_type='core', provider_id='core_event_journal' if scope.startswith('publication:') else 'core_local_projection', contract_version='1'))
                    if scope.startswith('status:'): row['selected_resource_id'] = resource.link_id
                    elif scope.startswith('peer:'): row['selected_resource_id'] = resource.peer_id
                elif scope.startswith(('checkpoint:', 'platform:installation.identity.read')):
                    row.update(readiness='ready', reasons=(), provider=ResourceProviderV1(
                        provider_type='core', provider_id='core_metadata', contract_version='1'))
                elif scope.startswith('session:'):
                    from backend.services.application_session_runtimes import session_runtimes
                    available = session_runtimes(engine).available(db, resource.model_dump(mode='json'))
                    row.update(readiness='ready' if available else 'unavailable',
                        reasons=() if available else ('session_runtime_not_connected',),
                        selected_resource_id=resource.target_device_id,
                        provider=ResourceProviderV1(provider_type='session', provider_id=resource.declaration.provider_id,
                            provider_version=resource.provider_version, contract_version=str(resource.contract.contract_version)))
                rows[scope] = ResourceObservationV1(**row)
    except (authority.AuthorityManagementError, AuthorityReviewKeyError):
        return ResourceDiscoveryV1(instance_id=instance_id, artifact_sha256=prepared.pin.sha256,
            observed_at=datetime.now(UTC), resources=tuple(_redacted(scope, row.declared, required=row.required)
                for scope,row in rows.items())).model_dump(mode='json')

    # No key/SQL lease or caller's routing transaction spans provider IPC.
    file_states = {}
    from backend.config import get_settings
    from backend.services.application_resource_providers import observe, observe_host
    settings = get_settings().applications
    provider_states = {kind:observe(kind, settings) for kind in sorted(provider_kinds)}
    host_state = 'unknown'
    if host_probe is not None:
        try:
            secret = transport_secret if transport_secret is not None else _secret(instance_id)
            host_state = observe_host(host_probe[0], secret, prepared, host_probe[1])
        except (OSError, ValueError): pass
    if file_probe is not None:
        try:
            secret = transport_secret if transport_secret is not None else _secret(instance_id)
            if type(secret) is not bytes or len(secret) != 32: raise ValueError('Resource key unavailable')
            media = any(scope == 'storage:private_files_transform' and row.access == 'granted' for scope,row in rows.items())
            state = _file_observation(*file_probe, prepared, secret, media=False)
            file_states['ordinary'] = state
            if media: file_states['media'] = _file_observation(*file_probe, prepared, secret, media=True)
        except (OSError, ValueError): file_states = {'ordinary':'unknown', 'media':'unknown'}
    if sql_probe is not None:
        from backend.services.application_relational import observe_runtime_status
        sql_hello = observe_runtime_status(sql_probe)
    fresh = manager._prepare(installation_id)
    with manager.keys.locked() as key, _read_snapshot(engine) as db:
        app = db.get(Installation, installation_id)
        if (fresh.pin != prepared.pin or app is None or app.instance_id != instance_id
                or not app.enabled or app.status != 'active'): raise ValueError('Resource observation changed')
        subject = manager._subject(db, key, installation_id, fresh)
        grant = manager._require_current_grant(db, key, installation_id, fresh)
        if _binding(db, installation_id, fresh, subject, grant) != fence:
            raise ValueError('Resource authority changed during observation')
        if file_probe is not None:
            from backend.services.application_files import _runtime
            if _runtime(db, installation_id) != file_probe[0]: raise ValueError('Resource runtime changed')
        if host_probe is not None:
            from backend.services.application_files import _runtime
            if _runtime(db, installation_id) != host_probe[0]: raise ValueError('Resource runtime changed')
        sql_ready = False
        if sql_probe is not None:
            from backend.services.application_relational import require_runtime_status
            try:
                require_runtime_status(db, installation_id, fresh, grant, (sql_probe, sql_hello)); sql_ready = True
            except (ValueError, RuntimeError): pass
        for scope,row in list(rows.items()):
            if row.access != 'granted': continue
            if scope.startswith('storage:private_files_'):
                media = scope == 'storage:private_files_transform'
                state = file_states.get('media' if media else 'ordinary', 'unknown')
                reason = ('provider_unavailable' if media else 'runtime_unavailable') if state == 'unavailable' else 'runtime_not_observed'
                rows[scope] = ResourceObservationV1(**{**row.model_dump(), 'readiness':state,
                    'reasons':() if state == 'ready' else (reason,), 'provider':ResourceProviderV1(
                        provider_type='application_host', provider_id='image_provider_v1' if media else 'application_files',
                        contract_version='1' if media else str(file_probe[1].file_contract_version))})
            elif scope.startswith('storage:relational_') and sql_ready:
                rows[scope] = ResourceObservationV1(**{**row.model_dump(), 'readiness':'ready', 'reasons':(),
                    'provider':ResourceProviderV1(provider_type='application_host', provider_id='prepared_relational', contract_version='1')})
            elif scope.startswith('query:'):
                # Executor support is observed, but no business handler/host
                # health call is made merely by discovering a read permission.
                state = provider_states['query']
                rows[scope] = ResourceObservationV1(**{**row.model_dump(),
                    'readiness':'unavailable' if state == 'unavailable' else 'unknown',
                    'reasons':('query_runtime_unavailable' if state == 'unavailable'
                        else 'provider_not_observed' if state == 'ready' else 'runtime_not_observed',)})
            elif scope.startswith(('connector:', 'event:', 'task:')):
                kind = scope.split(':',1)[0]
                states = [provider_states[kind]] + ([host_state] if kind in {'event','task'} else [])
                if kind == 'event': states.append(row.readiness)
                state = 'unavailable' if 'unavailable' in states else 'unknown' if 'unknown' in states else 'ready'
                rows[scope] = ResourceObservationV1(**{**row.model_dump(), 'readiness':state,
                    'reasons':() if state == 'ready' else ('provider_unavailable' if state == 'unavailable' else 'runtime_not_observed',)})
    return ResourceDiscoveryV1(instance_id=instance_id, artifact_sha256=prepared.pin.sha256,
        observed_at=datetime.now(UTC), resources=tuple(rows.values())).model_dump(mode='json')
