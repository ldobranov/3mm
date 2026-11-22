"""Separate bootstrap/machine endpoints and human-only local consent controls."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.db.module import ApplicationExtensionInstallation
from backend.installation import peers
from backend.installation.identity import installation_identity
from backend.accounts.dependencies import require_admin
from backend.storage.sessions import get_db
from packages.protocol.installation_identity import InstallationIdentityV1
from packages.protocol.installation_peer import PEER_MAX_BYTES, ProjectionConsentV1
from packages.protocol.installation_peer_v2 import PeerApprovalReviewV2, PeerOutboundConsentRequestV2
from packages.protocol.module_manifest import MODULE_ID_PATTERN
from sqlalchemy import select

router = APIRouter(prefix="/api/v1/installation-peers", tags=["installation-peers"])


class OriginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    origin: str = Field(max_length=255)


class OutboundConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    origin: str = Field(max_length=255)
    receiver_identity: InstallationIdentityV1
    target_module_id: str = Field(pattern=MODULE_ID_PATTERN, max_length=160)
    consent: ProjectionConsentV1


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_generation: int = Field(ge=1)


class MetadataReviewRequest(GenerationRequest):
    expected_metadata_revision: int | None = Field(default=None, ge=1)
    expected_metadata_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class IncomingReportDecision(PeerApprovalReviewV2):
    expected_receiver_artifact: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_receiver_incarnation: str = Field(pattern=r"^[0-9a-f]{32}$")


class SenderDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_review_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    # Allow and withdrawal use the same exact displayed snapshot.
    allow: bool


class ConsentUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: int = Field(ge=1)
    consent: ProjectionConsentV1


def _run(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except peers.InstallationPeerError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        # Never echo an invalid proof, credential, key or extension response.
        raise HTTPException(
            409, "Installation peer validation or operation failed"
        ) from exc


async def _run_async(function,db,*args,**kwargs):
    try:return await function(db,*args,**kwargs)
    except peers.InstallationPeerError as exc:raise HTTPException(409,str(exc)) from exc
    except (ValueError,RuntimeError) as exc:raise HTTPException(409,"Installation peer validation or operation failed") from exc
    finally:await run_in_threadpool(db.rollback)


def _application(db, module_id):
    application = db.scalar(
        select(ApplicationExtensionInstallation).where(
            ApplicationExtensionInstallation.module_id == module_id
        )
    )
    if application is None:
        raise HTTPException(404, "Application installation was not found")
    return application


def _https_origin(request: Request, db):
    # Scheme comes from ASGI server's trusted transport/proxy configuration.
    # This code does not trust arbitrary Forwarded/X-Forwarded headers.
    if request.url.scheme != "https" or request.url.query:
        raise HTTPException(
            403, "Installation peer endpoints require HTTPS without a query"
        )
    origin = f"https://{request.url.netloc}"
    if origin != _run(peers.configured_origin, db):
        raise HTTPException(
            403, "Installation peer origin is not configured or does not match"
        )
    return origin


async def _body(request: Request, *, authenticated=False):
    authorization = request.headers.get("authorization")
    if (authenticated and authorization != "ThreeMM-Peer") or (
        not authenticated and authorization is not None
    ):
        raise HTTPException(
            401, "The dedicated installation peer authentication scheme is required"
        )
    content = b""
    async for chunk in request.stream():
        content += chunk
        if len(content) > PEER_MAX_BYTES:
            raise HTTPException(413, "Installation peer request is too large")
    import json

    try:
        value = json.loads(content)
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(400, "Installation peer body is invalid") from exc


@router.put("/origin")
def configure_origin(
    request: OriginRequest, admin=Depends(require_admin), db: Session = Depends(get_db)
):
    return _run(peers.configure_origin, db, request.origin, user_id=admin.id)


@router.get("/origin")
def get_origin(_admin=Depends(require_admin), db: Session = Depends(get_db)):
    return {"origin": _run(peers.configured_origin, db)}


@router.get("/applications/{module_id}")
def list_peers(
    module_id: str, _admin=Depends(require_admin), db: Session = Depends(get_db)
):
    return peers.list_peers(db, _application(db, module_id))


@router.post("/applications/{module_id}/outbound", status_code=201)
def create_outbound(
    module_id: str,
    request: OutboundConsentRequest,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _run(
        peers.create_outbound,
        db,
        _application(db, module_id),
        origin=request.origin,
        receiver_identity=request.receiver_identity,
        target_module_id=request.target_module_id,
        consent=request.consent,
        user_id=admin.id,
    )


@router.get("/applications/{module_id}/outbound/report-references")
def local_report_references(module_id: str, response: Response, after: str | None = None, _admin=Depends(require_admin),
                            db: Session = Depends(get_db)):
    """Discover only the current local references; no pairing, destination list or report payload."""
    from sqlalchemy.exc import SQLAlchemyError
    from backend.installation.report_receipts import current_references, valid_owner
    response.headers["Cache-Control"] = "no-store"
    if not valid_owner(module_id):
        raise HTTPException(400, "Expected an application ID", headers={"Cache-Control": "no-store"})
    try:
        return current_references(db, module_id, after)
    except ValueError:
        raise HTTPException(400, "Expected an original link ID as the page cursor",
                            headers={"Cache-Control": "no-store"}) from None
    except SQLAlchemyError:
        raise HTTPException(503, "Local peer report references are unavailable",
                            headers={"Cache-Control": "no-store"}) from None


@router.get("/applications/{module_id}/outbound/{link_id}/reports/{report_id}")
def local_report_outcome(module_id: str, link_id: str, report_id: str, response: Response,
                         _admin=Depends(require_admin), db: Session = Depends(get_db)):
    """Administrator-only journal read; neither contacts the peer nor submits work."""
    from sqlalchemy.exc import SQLAlchemyError
    from backend.installation.report_receipts import identifiers, observe_report
    response.headers["Cache-Control"] = "no-store"
    if not identifiers(module_id, link_id, report_id):
        raise HTTPException(400, "Expected an application, original link and original report ID",
                            headers={"Cache-Control": "no-store"})
    try:
        return observe_report(db, module_id, link_id, report_id)
    except SQLAlchemyError:
        raise HTTPException(503, "Local peer report observation is unavailable",
                            headers={"Cache-Control":"no-store"}) from None


@router.post("/applications/{module_id}/inbound/{binding_id}/approve")
def approve_peer(
    module_id: str,
    binding_id: str,
    request: MetadataReviewRequest,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _run(
        peers.approve_inbound,
        db,
        _application(db, module_id),
        binding_id,
        request.expected_generation,
        user_id=admin.id,
        expected_metadata_revision=request.expected_metadata_revision,
        expected_metadata_hash=request.expected_metadata_hash,
    )


@router.post("/applications/{module_id}/outbound/v2", status_code=201)
def create_outbound_v2(
    module_id: str,
    request: PeerOutboundConsentRequestV2,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _run(
        peers.create_outbound,
        db,
        _application(db, module_id),
        origin=request.origin,
        receiver_identity=request.receiver_identity,
        target_module_id=request.target_module_id,
        consent=request.consent,
        application_intent=request.application_intent,
        peer_version=2,
        user_id=admin.id,
    )


@router.post("/applications/{module_id}/outbound/{link_id}/enroll")
def enroll_report_link(module_id: str, link_id: str, _admin=Depends(require_admin), db: Session = Depends(get_db)):
    return _run(peers.enroll_outbound, db, _application(db, module_id), link_id, report_operator=True)


@router.get("/applications/{module_id}/outbound/{link_id}/sender-approval")
def sender_review(module_id: str, link_id: str, response: Response, _admin=Depends(require_admin),
                  db: Session = Depends(get_db)):
    from backend.installation.sender_consent import review
    response.headers["Cache-Control"] = "no-store"
    return _run(review, db, _application(db, module_id), link_id)


@router.post("/applications/{module_id}/outbound/{link_id}/rotate")
def rotate_report_link(module_id: str, link_id: str, request: GenerationRequest, _admin=Depends(require_admin),
                       db: Session = Depends(get_db)):
    return _run(peers.rotate_outbound, db, _application(db, module_id), link_id,
                expected_generation=request.expected_generation, report_operator=True)


@router.get("/applications/{module_id}/sender-links")
def sender_links(module_id: str, response: Response, _admin=Depends(require_admin), db: Session = Depends(get_db)):
    from backend.db.installation_peer import InstallationPeerOutbound as Link
    app = _application(db, module_id)
    response.headers["Cache-Control"] = "no-store"
    ids = db.scalars(select(Link.link_id).where(Link.module_id == module_id,
        Link.application_instance_id == app.instance_id, Link.state == "active",
        Link.start_request["peer_version"].as_integer() == 2).order_by(Link.link_id).limit(32)).all()
    return {"module_id": module_id, "links": ids}


@router.post("/applications/{module_id}/outbound/{link_id}/sender-approval", status_code=204, response_class=Response)
def sender_decision(module_id: str, link_id: str, request: SenderDecision, admin=Depends(require_admin),
                    db: Session = Depends(get_db)):
    from backend.installation.sender_consent import review
    _run(review, db, _application(db, module_id), link_id, user_id=admin.id,
         expected=request.expected_review_hash, decision="allow" if request.allow else "withdraw")
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/applications/{module_id}/incoming-report-requests")
def incoming_report_requests(module_id: str, response: Response, _admin=Depends(require_admin),
                             db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return _run(peers.pending_report_reviews, db, _application(db, module_id))


@router.post("/applications/{module_id}/incoming-report-requests/{binding_id}/approve",
             status_code=204, response_class=Response)
def approve_incoming_report(module_id: str, binding_id: str, request: IncomingReportDecision,
                            admin=Depends(require_admin), db: Session = Depends(get_db)):
    # This is the same human decision as the established v2 approval. The
    # browser needs a receipt, not the machine credential or report contents.
    _run(peers.approve_inbound, db, _application(db, module_id), binding_id,
         request.expected_generation, user_id=admin.id,
         expected_metadata_revision=request.expected_metadata_revision,
         expected_metadata_hash=request.expected_metadata_hash,
         expected_receiver=(request.expected_receiver_artifact, request.expected_receiver_incarnation))
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.put("/applications/{module_id}/outbound/{link_id}/consent")
def update_consent(
    module_id: str,
    link_id: str,
    request: ConsentUpdateRequest,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _run(
        peers.update_consent,
        db,
        _application(db, module_id),
        link_id,
        request.consent,
        request.expected_revision,
        user_id=admin.id,
    )


@router.post("/applications/{module_id}/inbound/{binding_id}/reopen")
def reopen_peer(
    module_id: str,
    binding_id: str,
    request: GenerationRequest,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _run(
        peers.reopen_inbound,
        db,
        _application(db, module_id),
        binding_id,
        request.expected_generation,
        user_id=admin.id,
    )


@router.delete("/applications/{module_id}/{direction}/{peer_id}")
def revoke_peer(
    module_id: str,
    direction: str,
    peer_id: str,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _run(
        peers.revoke_peer,
        db,
        _application(db, module_id),
        peer_id,
        direction,
        user_id=admin.id,
    )


@router.get("/v1/identity")
@router.get("/v2/identity")
def public_peer_identity(
    request: Request, response: Response, db: Session = Depends(get_db)
):
    _https_origin(request, db)
    response.headers["Cache-Control"] = "no-store"
    return _run(installation_identity, db).model_dump(mode="json")


@router.get("/v2/capabilities")
def peer_capabilities(
    request: Request, response: Response, db: Session = Depends(get_db)
):
    _https_origin(request, db)
    response.headers["Cache-Control"] = "no-store"
    return peers.peer_capabilities()


@router.post("/v1/enrollments/start")
@router.post("/v2/enrollments/start")
async def start_enrollment(request: Request, db: Session = Depends(get_db)):
    origin = _https_origin(request, db)
    value = await _body(request)
    result = await run_in_threadpool(
        _run,
        peers.enrollment_start,
        db,
        value,
        origin=origin,
        peer_version=2 if "/v2/" in request.url.path else 1,
    )
    return result.model_dump(mode="json")


@router.post("/v1/enrollments/complete")
@router.post("/v2/enrollments/complete")
async def complete_enrollment(request: Request, db: Session = Depends(get_db)):
    origin = _https_origin(request, db)
    value = await _body(request)
    result = await run_in_threadpool(
        _run,
        peers.enrollment_complete,
        db,
        value,
        origin=origin,
        peer_version=2 if "/v2/" in request.url.path else 1,
    )
    await _run_async(peers.notify_bootstrap, db, result.binding_id)
    # Owner callback might approve. The same completion now reads its receipt.
    result = await run_in_threadpool(
        _run,
        peers.enrollment_complete,
        db,
        value,
        origin=origin,
        peer_version=2 if "/v2/" in request.url.path else 1,
    )
    return result.model_dump(mode="json")


@router.post("/v1/report")
@router.post("/v2/report")
async def report_status(request: Request, db: Session = Depends(get_db)):
    origin = _https_origin(request, db)
    value = await _body(request, authenticated=True)
    return await _run_async(peers.receive_report, db, value, origin=origin, path=request.url.path)


@router.post("/v1/rotate")
@router.post("/v2/rotate")
async def rotate_credential(request: Request, db: Session = Depends(get_db)):
    origin = _https_origin(request, db)
    value = await _body(request, authenticated=True)
    result = await run_in_threadpool(
        _run, peers.rotate_inbound, db, value, origin=origin, path=request.url.path
    )
    return result.model_dump(mode="json")
