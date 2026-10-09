"""Scoped application publications in Core's existing durable event journal.

Signed platform transport supplies the installed service, never a caller-owned
producer. A committed historical receipt is not current authority or a request
to replay consumers. No device identity or cross-application stream is inferred.
"""

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.db.device import DeviceEvent
from backend.db.module import ApplicationExtensionInstallation
from backend.services.application_authority_management import effect_admission
from backend.services.application_authority_sources import _core_identity
from three_mm_protocol.application_event_publication import (
    ApplicationEventProducerV1, ApplicationEventPublicationReceiptV1,
    ApplicationEventPublicationV1, PlatformEventV1,
    parse_application_publication_request, prepare_application_event,
)


def _producer(db, installation_id):
    installation = db.get(ApplicationExtensionInstallation, installation_id, populate_existing=True)
    if installation is None:
        raise ValueError('Application publication producer is unavailable')
    return ApplicationEventProducerV1(core_installation_id=_core_identity(db),
        application_installation_id=str(installation.id),
        incarnation=installation.authority_incarnation, module_id=installation.module_id)


def _historical(db, producer, request):
    row = db.scalar(select(DeviceEvent).where(DeviceEvent.event_id == request.event_id)
        .execution_options(populate_existing=True))
    if row is None:
        return None
    conflict = ValueError('Publication event identity has different owner or content')
    if row.producer_kind != 'application':
        raise conflict
    try:
        receipt = ApplicationEventPublicationReceiptV1.model_validate(row.publication_receipt)
        declaration = ApplicationEventPublicationV1.model_validate(row.publication_declaration)
        original = PlatformEventV1(event_id=row.event_id,
            producer=ApplicationEventProducerV1.model_validate(row.application_producer),
            publication_id=declaration.publication_id, event_type=row.event_type,
            payload=row.payload, occurred_at=row.occurred_at.replace(tzinfo=UTC)
                if row.occurred_at.tzinfo is None else row.occurred_at)
        retry = PlatformEventV1(event_id=request.event_id, producer=producer,
            publication_id=request.publication_id, event_type=original.event_type,
            payload=request.payload, occurred_at=request.occurred_at)
        if declaration.event_type != row.event_type or not receipt.matches(original) or not receipt.matches(retry):
            raise conflict
        return receipt.model_dump(mode='json')
    except (ValueError, TypeError, AttributeError):
        raise conflict from None


def publish_application_event(db, installation, payload):
    try:
        request = parse_application_publication_request(json.dumps(payload, ensure_ascii=False, allow_nan=False))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ValueError('Application publication request is invalid') from None
    installation_id = installation.id
    producer = _producer(db, installation_id)
    receipt = _historical(db, producer, request)
    if receipt is not None:
        return receipt  # Exact owned history, even after revoke/disable/schema update.
    mode = db.scalar(select(ApplicationExtensionInstallation.authority_mode)
        .where(ApplicationExtensionInstallation.id == installation_id))
    if mode != 'enforced':
        raise ValueError('Application publication requires an applied resource grant')
    try:
        with effect_admission(db, installation_id, f'publication:{request.publication_id}') as admission:
            # Re-read current principal AND receipt under the key/guard lease.
            producer = _producer(db, installation_id)
            receipt = _historical(db, producer, request)
            if receipt is not None:
                db.commit()
                return receipt
            contract = admission.publications
            if contract is None:
                raise ValueError('Application publication is not declared')
            event = prepare_application_event(request, authenticated_producer=producer,
                contract=contract, application=admission.definition)
            declaration = next(item for item in contract.publications if item.publication_id == request.publication_id)
            receipt = ApplicationEventPublicationReceiptV1(publication_receipt_version=1,
                event_id=event.event_id, publication_id=event.publication_id, producer=producer,
                content_sha256=event.content_digest(), committed_at=datetime.now(UTC)).model_dump(mode='json')
            current = db.get(ApplicationExtensionInstallation, installation_id)
            db.add(DeviceEvent(device_id=None, producer_kind='application',
                application_producer=producer.model_dump(mode='json'),
                publication_declaration=declaration.model_dump(mode='json'), publication_receipt=receipt,
                authority_epoch=current.authority_epoch, event_id=event.event_id,
                event_type=event.event_type, payload=event.payload, occurred_at=event.occurred_at))
            db.commit()  # ACK only AFTER durable commit, no external I/O under lease.
            return receipt
    except (IntegrityError, ValueError):
        # A concurrent commit can also invalidate SQLite's earlier read snapshot
        # before guard admission. Re-read OWNED committed history after rollback,
        # without retrying admission or treating a denial as a new publication.
        db.rollback()
        receipt = _historical(db, _producer(db, installation_id), request)
        if receipt is None:
            raise
        return receipt
