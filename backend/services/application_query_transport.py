"""Short Core admission/result gate; Runtime alone waits for a query response.

One-use, process-local pending results are NOT durable calls or retries. A crash
loses the outcome, never permission to send again. No credentials leave Core.
"""
from dataclasses import dataclass
import hashlib
import hmac
from pathlib import Path
import secrets
import socket
import threading
import time
import uuid

from sqlalchemy.orm import Session

from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services import application_authority_management as authority
from backend.services.authority_metadata import authority_transaction
from three_mm_platform_wire import ENVELOPE_FIELDS, canonical, remaining
from three_mm_protocol.application_composition import ApplicationQueryRequestV1, ApplicationQueryResultV1
from three_mm_protocol.capability_contracts import validate_value
from three_mm_protocol.node_security import validate_node_json
from three_mm_runtime.application_transport import sign_message, send_message, verify_message

QUERY_CONTRACT = 1
MAX_PENDING = 8
PER_CONSUMER = 4


@dataclass
class QueryDispatch:
    receipt: str
    connection: socket.socket
    deadline_ms: int
    max_response_bytes: int


@dataclass(frozen=True)
class QueryRuntimeProbe:
    """Marker only: do the metadata probe outside all authority/DB leases."""


def _secret(root, instance):
    value = (Path(root) / (instance + '.key')).read_bytes()
    if len(value) != 32:
        raise ValueError('Query transport key unavailable')
    return value


class QueryBroker:
    def __init__(self):
        self.lock = threading.Lock()
        self.pending = {}

    def _reserve(self, installation_id, runtime_generation, core_generation, secret, request_id):
        with self.lock:
            now = time.monotonic()
            self.pending = {k: v for k, v in self.pending.items() if v['expires'] > now}
            if (len(self.pending) >= MAX_PENDING
                    or sum(v['installation_id'] == installation_id for v in self.pending.values()) >= PER_CONSUMER):
                raise ValueError('Query capacity unavailable')
            receipt = secrets.token_hex(32)
            self.pending[receipt] = dict(installation_id=installation_id,
                runtime_generation=runtime_generation, core_generation=core_generation,
                secret=secret, request_id=request_id, expires=now+8, admitted=False)
            return receipt, self.pending[receipt]

    def begin(self, db, installation, request, *, secret, runtime_generation, core_generation, key_root):
        if (type(runtime_generation) is not str or type(core_generation) is not str
                or set(request) != ENVELOPE_FIELDS | {'binding_id', 'arguments'}):
            raise ValueError('Queries require the current dedicated Runtime transport')
        query = ApplicationQueryRequestV1(binding_id=request['binding_id'], arguments=request['arguments'])
        identifier, engine = installation.id, db.get_bind().engine
        if db.new or db.dirty or db.deleted:
            raise ValueError('Query admission requires a clean transaction')
        db.rollback()
        manager = authority.configured_manager(engine)
        prepared = manager._prepare(identifier)  # Verify both packages before key/guard locks.
        receipt, pending = self._reserve(identifier, runtime_generation, core_generation, secret, request['request_id'])
        connection = None
        try:
            scope = f'query:{query.binding_id}:read'
            with manager.keys.locked() as key, authority_transaction(db):
                grant = manager._require_grant(db, key, identifier, prepared, scope)
                subject = manager._subject(db, key, identifier, prepared)
                resource = authority._subject_scopes(subject)[scope]
                consumer = db.get(Installation, identifier, populate_existing=True)
                provider = db.get(Installation, int(resource.provider.application_installation_id), populate_existing=True)
                if (not consumer.enabled or consumer.status != 'active'
                        or not hmac.compare_digest(_secret(key_root, consumer.instance_id), secret)):
                    raise ValueError('Query caller changed')
                contract = resource.declaration.contract
                validate_value(query.arguments, contract.input_schema)
                provider_secret = _secret(key_root, provider.instance_id)
                operation_request_id = uuid.uuid4().hex
                message = sign_message(dict(version=1, request_id=operation_request_id,
                    timestamp=int(time.time()), operation_id=resource.export.handler_operation_id,
                    payload=query.arguments, context=dict(audience='internal', correlation_id=request['request_id'],
                        application_caller=dict(instance_id=consumer.instance_id, module_id=consumer.module_id,
                            artifact_sha256=prepared.pin.sha256, binding_id=query.binding_id,
                            contract_digest=resource.contract_digest))), provider_secret)
                pending.update(scope=scope, instance_id=consumer.instance_id,
                    grant_revision=grant['revision'], resource=resource,
                    provider_secret=provider_secret, operation_request_id=operation_request_id)
                # The guard linearizes one short send against revoke/disable.
                # Never read provider output in Core or hand off a writable FD.
                pending['expires'] = time.monotonic() + contract.timeout_seconds
                connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                short = min(pending['expires'], time.monotonic()+1)
                connection.settimeout(remaining(short)); connection.connect(provider.socket_path)
                connection.settimeout(remaining(short)); send_message(connection, message)
                connection.shutdown(socket.SHUT_WR)
            pending['admitted'] = True  # The guard transaction committed before FD release.
            return QueryDispatch(receipt, connection, int(pending['expires']*1000), contract.max_response_bytes)
        except BaseException:
            if connection is not None: connection.close()
            with self.lock: self.pending.pop(receipt, None)
            raise

    def finish(self, engine, receipt, response, *, runtime_generation, core_generation, key_root):
        if type(receipt) is not str or len(receipt) != 64:
            raise ValueError('Query receipt invalid')
        with self.lock:
            pending = self.pending.get(receipt)
            if (pending is None or pending['runtime_generation'] != runtime_generation
                    or pending['core_generation'] != core_generation):
                raise ValueError('Query result owner changed')
            self.pending.pop(receipt)  # Exactly one completion, including refusal/timeout.
        result = dict(ok=False, reason='operation_denied', error='Query result unavailable; no retry was sent')
        try:
            if not pending['admitted'] or time.monotonic() >= pending['expires']:
                raise ValueError('Query deadline exceeded')
            secret = pending['secret']
            resource = pending['resource']
            if (not hmac.compare_digest(_secret(key_root, pending['instance_id']), secret)
                    or not hmac.compare_digest(_secret(key_root, resource.provider_instance_id), pending['provider_secret'])):
                raise ValueError('Query transport changed')
            verified = verify_message(response, pending['provider_secret'], expected_request_id=pending['operation_request_id'])
            if (set(verified) != {'version', 'request_id', 'timestamp', 'ok', 'result', 'signature'}
                    or type(verified.get('version')) is not int or verified['version'] != 1
                    or verified.get('ok') is not True or type(verified.get('result')) is not dict):
                raise ValueError('Query provider response invalid')
            output = verified['result']
            contract = resource.declaration.contract
            validate_node_json(output, max_bytes=contract.max_response_bytes)
            validate_value(output, contract.output_schema)
            manager = authority.configured_manager(engine)
            prepared = manager._prepare(pending['installation_id'])
            with manager.keys.locked() as key, Session(engine) as db, authority_transaction(db):
                grant = manager._require_grant(db, key, pending['installation_id'], prepared, pending['scope'])
                subject = manager._subject(db, key, pending['installation_id'], prepared)
                current = authority._subject_scopes(subject)[pending['scope']]
                consumer = db.get(Installation, pending['installation_id'], populate_existing=True)
                if (grant['revision'] != pending['grant_revision'] or not consumer.enabled or consumer.status != 'active'
                        or authority._canonical_bytes(current.model_dump(mode='json')) != authority._canonical_bytes(resource.model_dump(mode='json'))
                        or time.monotonic() >= pending['expires']):
                    raise ValueError('Query authority changed')
                answer = ApplicationQueryResultV1(binding_id=resource.declaration.binding_id,
                    provider_instance_id=resource.provider_instance_id, contract_digest=resource.contract_digest, output=output)
                result = dict(ok=True, result=answer.model_dump(mode='json'))
        except Exception:
            pass  # Do not expose provider data/error, paths, keys or stale output.
        answer = dict(version=1, request_id=pending['request_id'], timestamp=int(time.time()), **result)
        # Service RPC uses UTF-8 canonical JSON; the SDK wire escapes Unicode.
        # Sign for the actual recipient, not with the provider RPC convention.
        answer['signature'] = hmac.new(pending['secret'], canonical(answer), hashlib.sha256).hexdigest()
        return answer
