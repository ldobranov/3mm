"""Administrator-only redacted diagnostics API."""

from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
import asyncio
import threading
from sqlalchemy.orm import Session
from backend.storage.sessions import get_db
from starlette.concurrency import run_in_threadpool
from backend.system.diagnostics.workspace import observe
from packages.protocol.diagnostic_snapshot import read_export, timeline
from packages.protocol.diagnostics import OPERATIONS, MAX_EXPORT_BYTES
from pydantic import field_validator

from backend.config import get_settings
from backend.db.user import User
from backend.system.diagnostics.bundle import (
    DiagnosticPreview,
    build_diagnostic_bundle,
    build_diagnostic_preview,
    serialize_diagnostic_bundle,
)
from backend.system.diagnostics.alerts import (
    OperationalAlertSummary,
    build_operational_alert_summary,
)
from backend.accounts.dependencies import require_admin
from backend.system.diagnostics.operations import core_diagnostics
from backend.system.diagnostics.failures import recent_http_failures
from packages.protocol.diagnostics import (
    DEFAULT_TTL_SECONDS, MAX_TTL_SECONDS, DiagnosticBusy,
)
from backend.system.diagnostics.cases import build_cases
from fastapi import Query
import json


router = APIRouter(prefix="/api/v1/diagnostics", tags=["diagnostics"])
_merge_lock = threading.Lock()
_case_lock = threading.Lock()


def _case_snapshot(settings, lifecycle, trace_id):
    from backend.system.diagnostics.operations import core_diagnostics
    failures = recent_http_failures.snapshot()
    try:
        recording = core_diagnostics.snapshot(1000)
    except DiagnosticBusy:
        recording = {'status': 'busy', 'records': []}
    try:
        observations = observe(settings, lifecycle)
    except Exception:
        observations = {'probe_status': 'unavailable', 'components': []}
    return build_cases(failures, recording, observations, trace_id=trace_id)


@router.get('/cases')
async def diagnostic_cases(request: Request, response: Response,
                           trace_id: str | None = Query(default=None, pattern=r'^(platform|invoke)_[0-9a-f]{32}$'),
                           _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """The same safe evidence for people, the CLI and an explicitly authorized AI."""
    response.headers['Cache-Control'] = 'no-store'
    db.rollback()  # Never keep an authentication transaction across optional probes.
    if not _case_lock.acquire(blocking=False):
        raise HTTPException(409, 'Diagnostic case collector is busy')
    try:
        components = getattr(request.app.state, 'core_components', None)
        lifecycle = components.snapshot() if components is not None else {'status': 'not_started', 'components': {}}
        return await run_in_threadpool(_case_snapshot, get_settings(), lifecycle, trace_id)
    finally:
        _case_lock.release()


@router.get('/cases/export')
async def export_cases(request: Request,
                       trace_id: str | None = Query(default=None, pattern=r'^(platform|invoke)_[0-9a-f]{32}$'),
                       _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    response = Response()
    value = await diagnostic_cases(request, response, trace_id, _admin, db)
    return Response(json.dumps(value, ensure_ascii=True, allow_nan=False), media_type='application/json',
                    headers={'Cache-Control': 'no-store',
                             'Content-Disposition': 'attachment; filename="diagnostic-cases.json"'})


@router.get('/failures')
def recent_failures(response: Response, _admin: User = Depends(require_admin)):
    """Current Core process only. This does not start detailed recording."""
    response.headers['Cache-Control'] = 'no-store'
    return recent_http_failures.snapshot()


@router.get('/failures/export')
def export_recent_failures(_admin: User = Depends(require_admin)):
    import json
    snapshot = recent_http_failures.snapshot()
    if snapshot['status'] != 'ready':
        raise HTTPException(503, 'Recent failure snapshot is temporarily unavailable')
    return Response(content=json.dumps(snapshot, ensure_ascii=True, allow_nan=False),
        media_type='application/json', headers={
            'Cache-Control': 'no-store',
            'Content-Disposition': 'attachment; filename="3mm-recent-http-failures.json"',
        })


@router.get("/components")
def component_status(request: Request, response: Response, _admin: User = Depends(require_admin)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    components = getattr(request.app.state, "core_components", None)
    if components is None:
        return {"schema_version": 1, "status": "not_started", "components": {}}
    return components.snapshot()


@router.get("/preview", response_model=DiagnosticPreview)
def diagnostics_preview(_admin: User = Depends(require_admin)) -> DiagnosticPreview:
    return build_diagnostic_preview(get_settings())


@router.get("/bundle")
def diagnostics_bundle(_admin: User = Depends(require_admin)) -> Response:
    bundle = build_diagnostic_bundle(get_settings())
    filename = f"3mm-diagnostics-{bundle.generated_at:%Y%m%dT%H%M%SZ}.json"
    return Response(
        content=serialize_diagnostic_bundle(bundle),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/alerts", response_model=OperationalAlertSummary)
def operational_alerts(_admin: User = Depends(require_admin)) -> OperationalAlertSummary:
    return build_operational_alert_summary(get_settings())


class DiagnosticSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ttl_seconds: int = Field(default=DEFAULT_TTL_SECONDS, strict=True, ge=1, le=MAX_TTL_SECONDS)
    profile: Literal['diagnostic','development'] = 'diagnostic'
    operation: str | None = Field(default=None, max_length=64)
    instance_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{24}$')
    trace_id: str | None = Field(default=None, pattern=r'^(platform|invoke)_[0-9a-f]{32}$')

    @field_validator('operation')
    @classmethod
    def supported_operation(cls,value):
        if value is not None and value not in OPERATIONS: raise ValueError('Unsupported diagnostic operation')
        return value


@router.post("/session")
def start_diagnostic_session(request: DiagnosticSessionRequest, response: Response,
                             _admin: User = Depends(require_admin)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    try:
        return core_diagnostics.start(**request.model_dump())
    except DiagnosticBusy as exc:
        raise HTTPException(status_code=409, detail="Diagnostic session or export is in use") from exc


@router.get("/session")
def diagnostic_session_status(response: Response, _admin: User = Depends(require_admin)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return core_diagnostics.status()


@router.delete("/session")
def stop_diagnostic_session(response: Response, _admin: User = Depends(require_admin)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return core_diagnostics.stop()


class DiagnosticRecordsResponse(StreamingResponse):
    """Release the snapshot even when streaming fails or the client disconnects."""

    def __init__(self, session):
        self._snapshot = session.export()
        chunks = self._snapshot.__enter__()
        super().__init__(chunks, media_type="application/x-ndjson", headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'attachment; filename="3mm-operation-records.ndjson"',
        })

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self._snapshot.__exit__(None, None, None)


@router.get("/session/records")
def diagnostic_session_records(_admin: User = Depends(require_admin)) -> StreamingResponse:
    try:
        return DiagnosticRecordsResponse(core_diagnostics)
    except DiagnosticBusy as exc:
        raise HTTPException(status_code=409, detail="Diagnostic export is in use") from exc


@router.get('/workspace')
async def diagnostic_workspace(request: Request, response: Response, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    response.headers['Cache-Control']='no-store'
    components=getattr(request.app.state,'core_components',None)
    state=components.snapshot() if components is not None else {'status':'not_started','components':{}}
    db.rollback()  # No authentication read transaction spans optional probes.
    return await run_in_threadpool(observe,get_settings(),state)


@router.get('/timeline')
def diagnostic_timeline(response: Response, _admin: User = Depends(require_admin)):
    response.headers['Cache-Control']='no-store'
    try: return timeline(core_diagnostics.snapshot(1000))
    except DiagnosticBusy as exc: raise HTTPException(409,'Diagnostic export is in use') from exc


def _merge_records(body):
    return timeline(core_diagnostics.snapshot(1000),read_export(body))


@router.post('/timeline/merge')
async def merge_diagnostic_timeline(request: Request, response: Response, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    response.headers['Cache-Control']='no-store'
    db.rollback()
    if not _merge_lock.acquire(blocking=False): raise HTTPException(409,'Diagnostic collector is busy')
    try:
        data=bytearray()
        async with asyncio.timeout(5):
            async for chunk in request.stream():
                if len(data)+len(chunk)>MAX_EXPORT_BYTES: raise HTTPException(413,'Diagnostic import exceeds budget')
                data.extend(chunk)
        return await run_in_threadpool(_merge_records,bytes(data))
    except TimeoutError: raise HTTPException(408,'Diagnostic import deadline expired') from None
    except DiagnosticBusy as exc: raise HTTPException(409,'Diagnostic export is in use') from exc
    except (ValueError,TypeError,KeyError,RecursionError): raise HTTPException(422,'Diagnostic metadata is invalid') from None
    finally: _merge_lock.release()
