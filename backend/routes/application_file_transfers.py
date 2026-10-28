"""CAP11 bounded raw streams; exact UI/user and separate service authority."""
import base64
import json
import re
import secrets
import uuid
from urllib.parse import parse_qs, quote

import anyio
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect
from starlette.responses import HTMLResponse, StreamingResponse

from backend.config import get_settings
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services.application_access import application_permission_ids, resolve_application_principal
from backend.services.application_file_transfers import BrowserFileCaller, PublicFileCaller, transfer_slot
from backend.services.application_files import ApplicationFileAuthorityError, execute_private_file, file_operation_status
from backend.utils.db_utils import get_db
from three_mm_application_sdk import media_wire

router = APIRouter(tags=['application-files'])
ID = r'^[0-9a-f]{32}$'
DIGEST = r'^[0-9a-f]{64}$'
NO_STORE = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer'}


def _secret(instance_id):
    value = (get_settings().applications.key_root / (instance_id + '.key')).read_bytes()
    if len(value) != 32:
        raise ValueError('Instance key is unavailable')
    return value


def _context(db, module_id, binding, authorization, operation):
    from backend.routes.application_extensions import ApplicationUiBinding, _installation, _active_package, _ui_route
    try:
        principal = resolve_application_principal(authorization, db)
        if principal.kind != 'user':
            raise HTTPException(403, 'A current user session is required')
        installation = _installation(db, module_id)
        package = _active_package(db, installation)
        binding = ApplicationUiBinding.model_validate(binding)
        permissions = application_permission_ids(db, installation.id, principal.user_id)
        definition, route = _ui_route(package, binding, principal, permissions, db=db, installation=installation)
        declaration = definition.storage.private_files
        if route.private_files is None or declaration is None or declaration.file_contract_version != 2:
            raise ValueError('Streaming files are not declared')
        caller = BrowserFileCaller(installation.id, installation.instance_id, installation.authority_incarnation,
            package.id, package.sha256, binding.built_ui_sha256, route, authorization, principal.user_id, operation, principal.subject_id)
        # Preflight is read-only; the final check serializes current session and
        # user rows inside the existing key -> guard admission transaction.
        caller.check_permissions(principal, permissions, module_id)
        return caller, declaration, _secret(installation.instance_id)
    except (ValueError, OSError):
        raise HTTPException(403, 'Current file access is unavailable') from None
    finally:
        db.rollback()


def _execute(db, caller, secret, value):
    try:
        result = execute_private_file(db, db.get(Installation, caller.installation_id), value, transport_secret=secret, caller=caller)
    except (ApplicationFileAuthorityError, ValueError):
        raise HTTPException(403, 'Current file access or runtime is unavailable') from None
    if result['receipt']['outcome'] != 'completed':
        raise HTTPException(409, {'code': 'execution_unconfirmed', 'request_id': value['request_id']})
    value = result.get('file_result', result['receipt'].get('result'))
    if not value or value.get('ok') is not True:
        code = (value or {}).get('error_code', 'recovery_required')
        raise HTTPException({'not_found': 404, 'expired': 410, 'quota': 413, 'denied': 403}.get(code, 409), {'code': code})
    return value


def _request(operation, **fields):
    return {'file_request_version': 2, 'request_id': uuid.uuid4().hex, 'operation': operation, **fields}


def _binding(entrypoint_id, artifact_sha256, built_ui_sha256):
    return {'host_version': 1, 'entrypoint_id': entrypoint_id, 'artifact_sha256': artifact_sha256, 'built_ui_sha256': built_ui_sha256}


async def _body(request, limit):
    length = request.headers.get('content-length')
    if length is not None and (len(length) > 10 or not length.isdecimal() or int(length) > limit):
        raise HTTPException(413, 'Request exceeds its bound')
    content = bytearray()
    try:
        with anyio.fail_after(15):
            async for chunk in request.stream():
                if len(content) + len(chunk) > limit:
                    raise HTTPException(413, 'Request exceeds its bound')
                content.extend(chunk)
    except TimeoutError:
        raise HTTPException(408, 'Ingress timed out before admission') from None
    except ClientDisconnect:
        raise HTTPException(400, 'Ingress was interrupted before admission') from None
    if length is not None and int(length) != len(content):
        raise HTTPException(400, 'Incomplete request')
    return bytes(content)


@router.post('/{module_id}/files/control')
async def control(module_id: str, request: Request, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    with transfer_slot():
        resolve_application_principal(authorization, db)
        db.rollback()
        try:
            raw = json.loads(await _body(request, 8192))
            if type(raw) is not dict or set(raw) != {'ui_context', 'file_request'}:
                raise ValueError()
            value = media_wire.parse_media_request(raw['file_request'])
            if value['operation'] in {'append', 'read', 'public_read', 'public_stat'}:
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise HTTPException(422, 'Invalid file control request') from None
        caller, _, secret = await run_in_threadpool(_context, db, module_id, raw['ui_context'], authorization, media_wire.SCOPES[value['operation']])
        result = await run_in_threadpool(_execute, db, caller, secret, value)
        return Response(json.dumps(result), media_type='application/json', headers=NO_STORE)


@router.post('/{module_id}/files/uploads/{upload_id}/chunks')
async def append(module_id: str, upload_id: str, request: Request, entrypoint_id: str,
        artifact_sha256: str = Query(pattern=DIGEST), built_ui_sha256: str = Query(pattern=DIGEST),
        offset: int = Query(ge=0, le=1024**3), authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    if not re.fullmatch(ID, upload_id):
        raise HTTPException(422, 'Invalid upload identity')
    if request.headers.get('content-type', '').lower() != 'application/octet-stream':
        raise HTTPException(415, 'Raw application/octet-stream is required')
    with transfer_slot():
        caller, _, secret = await run_in_threadpool(_context, db, module_id, _binding(entrypoint_id, artifact_sha256, built_ui_sha256), authorization, 'write')
        content = await _body(request, media_wire.CHUNK_BYTES)
        value = _request('append', upload_id=upload_id, offset=offset, content_base64=base64.b64encode(content).decode('ascii'))
        result = await run_in_threadpool(_execute, db, caller, secret, value)
        return Response(json.dumps(result), media_type='application/json', headers=NO_STORE)


def _download(db, caller, secret, metadata, request_factory):
    engine = db.get_bind().engine
    def chunks():
        with transfer_slot():
            offset = 0
            if metadata['size_bytes'] == 0:
                with Session(engine) as session:
                    _execute(session, caller, secret, request_factory(0))
            while offset < metadata['size_bytes']:
                with Session(engine) as session:
                    value = _execute(session, caller, secret, request_factory(offset))
                data = base64.b64decode(value['content_base64'], validate=True)
                if not data:
                    raise RuntimeError('Incomplete file stream')
                offset += len(data)
                yield data
    return StreamingResponse(chunks(), media_type='application/octet-stream', headers={**NO_STORE,
        'Content-Length': str(metadata['size_bytes']), 'ETag': '"' + metadata['sha256'] + '"',
        'X-Content-SHA256': metadata['sha256'],
        'Content-Disposition': "attachment; filename*=UTF-8''" + quote(metadata['filename'], safe=''),
        'Content-Security-Policy': "default-src 'none'; sandbox",
    })


@router.get('/{module_id}/files/{file_id}/content')
def download(module_id: str, file_id: str, entrypoint_id: str, artifact_sha256: str = Query(pattern=DIGEST),
        built_ui_sha256: str = Query(pattern=DIGEST), authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    with transfer_slot():
        caller, _, secret = _context(db, module_id, _binding(entrypoint_id, artifact_sha256, built_ui_sha256), authorization, 'read')
        metadata = _execute(db, caller, secret, _request('stat', file_id=file_id))['file']
        return _download(db, caller, secret, metadata, lambda offset: _request('read', file_id=file_id, sha256=metadata['sha256'], offset=offset, length=media_wire.CHUNK_BYTES))


@router.get('/{module_id}/files/{file_id}/chunks')
def read_chunk(module_id: str, file_id: str, entrypoint_id: str, artifact_sha256: str = Query(pattern=DIGEST),
        built_ui_sha256: str = Query(pattern=DIGEST), sha256: str = Query(pattern=DIGEST),
        offset: int = Query(ge=0, le=1024**3), length: int = Query(ge=1, le=media_wire.CHUNK_BYTES),
        authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    with transfer_slot():
        caller, _, secret = _context(db, module_id, _binding(entrypoint_id, artifact_sha256, built_ui_sha256), authorization, 'read')
        value = _execute(db, caller, secret, _request('read', file_id=file_id, sha256=sha256, offset=offset, length=length))
        return Response(base64.b64decode(value['content_base64'], validate=True), media_type='application/octet-stream', headers={**NO_STORE,
            'X-Chunk-SHA256': value['chunk_sha256'], 'X-Content-SHA256': value['sha256']})


@router.get('/{module_id}/files/requests/{request_id}')
def receipt(module_id: str, request_id: str, entrypoint_id: str, artifact_sha256: str = Query(pattern=DIGEST),
        built_ui_sha256: str = Query(pattern=DIGEST), authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    with transfer_slot():
        caller, _, _ = _context(db, module_id, _binding(entrypoint_id, artifact_sha256, built_ui_sha256), authorization, 'read')
        try:
            value = file_operation_status(db, db.get(Installation, caller.installation_id), request_id, caller=caller)
            return Response(json.dumps(value), media_type='application/json', headers=NO_STORE)
        except ValueError:
            raise HTTPException(403, 'File receipt is unavailable for this user') from None


@router.get('/{module_id}/files/links/{link_id}/open')
def public_link(link_id: str, module_id: str):
    if not re.fullmatch(ID, link_id):
        raise HTTPException(404)
    nonce = secrets.token_hex(16)
    html = '<!doctype html><meta name="viewport" content="width=device-width"><title>File download</title><h1>File download</h1><form method="post" action="content"><input type="hidden" name="token"><button disabled>Download</button></form>'
    html += '<script nonce="' + nonce + '">const t=location.hash.slice(1);history.replaceState(null,"",location.pathname);if(/^[0-9a-f]{64}$/.test(t)){document.querySelector("input").value=t;document.querySelector("button").disabled=false}</script>'
    return HTMLResponse(html, headers={**NO_STORE, 'Content-Security-Policy': "default-src 'none'; script-src 'nonce-" + nonce + "'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"})


@router.post('/{module_id}/files/links/{link_id}/content')
async def public_content(module_id: str, link_id: str, request: Request, db: Session = Depends(get_db)):
    from backend.routes.application_extensions import _installation, _active_package
    with transfer_slot():
        try:
            data = parse_qs((await _body(request, 80)).decode('ascii'), strict_parsing=True)
            if set(data) != {'token'} or len(data['token']) != 1:
                raise ValueError()
            value = media_wire.parse_media_request(_request('public_stat', link_id=link_id, token=data['token'][0]))
            installation = _installation(db, module_id)
            package = _active_package(db, installation)
            caller = PublicFileCaller(installation.id, installation.instance_id, installation.authority_incarnation, package.id, package.sha256)
            secret = _secret(installation.instance_id)
            metadata = await run_in_threadpool(_execute, db, caller, secret, value)
        except (ValueError, KeyError, OSError):
            raise HTTPException(403, 'File link is unavailable') from None
        identifier = uuid.uuid4().hex
        return _download(db, caller, secret, metadata['file'], lambda offset: _request('public_read', link_id=link_id, token=data['token'][0], download_id=identifier,
            sha256=metadata['file']['sha256'], offset=offset, length=media_wire.CHUNK_BYTES))
