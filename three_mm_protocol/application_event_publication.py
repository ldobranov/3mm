"""Additive event-publication contracts; no ingestion, grants or SDK transport.

An application request deliberately contains no producer/user/device identity.
Core must derive the producer from the authenticated installed service. Preparing
an envelope or comparing a receipt is pure validation, never durable admission.
The existing DeviceEventV1 and ApplicationExtensionV1 wire shapes stay unchanged.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Annotated, ClassVar, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from three_mm_protocol.application_extension import (
    APPLICATION_EVENT_PATTERN,
    SHA256_PATTERN,
    ApplicationExtensionV1,
)
from three_mm_protocol.capability_contracts import validate_schema, validate_value
from three_mm_protocol.device_event import DeviceEventV1
from three_mm_protocol.installation_identity import INSTALLATION_ID_PATTERN
from three_mm_protocol.module_manifest import MODULE_ID_PATTERN, SEMVER_PATTERN
from three_mm_protocol.node_security import (
    CORE_DEVICE_AUDIT_EVENTS,
    NODE_MESSAGE_BYTES,
    validate_node_json,
)
from three_mm_protocol.runtime_extension import IDENTIFIER_PATTERN

MAX_PUBLICATION_PAYLOAD_BYTES = NODE_MESSAGE_BYTES - 4096


def _json_data(value, *, max_bytes=NODE_MESSAGE_BYTES):
    """Bound before traversal; reject Python-only containers instead of coercing."""
    validate_node_json(value, max_bytes=max_bytes)

    def visit(item):
        if type(item) is tuple:
            raise ValueError("Publication data must contain JSON values only")
        if type(item) is dict:
            for child in item.values():
                visit(child)
        elif type(item) is list:
            for child in item:
                visit(child)

    visit(value)
    return value


def _application_event_type(value):
    if value.startswith("core.") or value in CORE_DEVICE_AUDIT_EVENTS:
        raise ValueError("Application publication cannot use a Core-owned event type")
    return value


class PublicationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    _message_bytes_limit: ClassVar[int] = NODE_MESSAGE_BYTES

    @field_validator(
        "publication_contract_version",
        "publication_request_version",
        "publication_receipt_version",
        "event_contract_version",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def exact_integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("Publication version must be an integer")
        return value

    @model_validator(mode="after")
    def bounded(self):
        validate_node_json(
            self.model_dump(mode="json"), max_bytes=self._message_bytes_limit
        )
        return self


class DeviceEventProducerV1(PublicationModel):
    kind: Literal["device"] = "device"
    device_id: str = Field(pattern=r"^dev_[0-9a-f]{32}$")


class ApplicationEventProducerV1(PublicationModel):
    kind: Literal["application"] = "application"
    core_installation_id: str = Field(pattern=INSTALLATION_ID_PATTERN)
    application_installation_id: str = Field(pattern=r"^[1-9][0-9]{0,18}$")
    incarnation: str = Field(pattern=r"^[0-9a-f]{32}$")
    module_id: str = Field(pattern=MODULE_ID_PATTERN, max_length=160)

    @field_validator("application_installation_id")
    @classmethod
    def bounded_installation_id(cls, value):
        if int(value) > 2**63 - 1:
            raise ValueError("Application installation identity is outside bounds")
        return value


EventProducerV1 = Annotated[
    DeviceEventProducerV1 | ApplicationEventProducerV1, Field(discriminator="kind")
]


class ApplicationEventPublicationV1(PublicationModel):
    publication_id: str = Field(pattern=IDENTIFIER_PATTERN)
    operation_id: str = Field(pattern=IDENTIFIER_PATTERN)
    event_type: str = Field(pattern=APPLICATION_EVENT_PATTERN, max_length=160)
    payload_schema: dict
    max_payload_bytes: int = Field(
        default=8192, strict=True, ge=1, le=MAX_PUBLICATION_PAYLOAD_BYTES
    )

    _event_type = field_validator("event_type")(_application_event_type)

    @field_validator("payload_schema", mode="before")
    @classmethod
    def bounded_schema(cls, value):
        _json_data(value, max_bytes=8192)
        validate_schema(value)
        if value.get("type") != "object":
            raise ValueError("Publication payload schema must be a strict object")
        return value


class ApplicationEventPublicationsV1(PublicationModel):
    """Independent declaration, not an extra field in application descriptor v1."""

    publication_contract_version: Literal[1]
    module_id: str = Field(pattern=MODULE_ID_PATTERN, max_length=160)
    version: str = Field(pattern=SEMVER_PATTERN, max_length=160)
    service_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    publications: tuple[ApplicationEventPublicationV1, ...] = Field(
        min_length=1, max_length=32
    )

    @model_validator(mode="after")
    def unique_publications(self):
        ids = [item.publication_id for item in self.publications]
        pairs = [(item.operation_id, item.event_type) for item in self.publications]
        if len(ids) != len(set(ids)) or len(pairs) != len(set(pairs)):
            raise ValueError(
                "Publication IDs and operation/event bindings must be unique"
            )
        return self


class TimedPublicationModel(PublicationModel):
    @field_validator("occurred_at", "committed_at", mode="before", check_fields=False)
    @classmethod
    def explicit_timestamp(cls, value):
        if not isinstance(value, (str, datetime)):
            raise ValueError(
                "Publication timestamp must be explicit and timezone-aware"
            )
        return value

    @field_validator("occurred_at", "committed_at", check_fields=False)
    @classmethod
    def utc_timestamp(cls, value):
        return value.astimezone(UTC)


class ApplicationEventPublishRequestV1(TimedPublicationModel):
    publication_request_version: Literal[1]
    event_id: str = Field(pattern=r"^evt_[0-9a-f]{32}$")
    publication_id: str = Field(pattern=IDENTIFIER_PATTERN)
    payload: dict
    occurred_at: AwareDatetime

    @field_validator("payload", mode="before")
    @classmethod
    def json_payload(cls, value):
        return _json_data(value, max_bytes=MAX_PUBLICATION_PAYLOAD_BYTES)


class PlatformEventV1(TimedPublicationModel):
    """Common internal envelope candidate; NOT a caller-authenticated wire API."""

    # The extra producer metadata must not invalidate a legacy 64-KiB message.
    # Ingress/payload limits stay unchanged; this allowance is internal only.
    _message_bytes_limit: ClassVar[int] = NODE_MESSAGE_BYTES + 4096

    event_contract_version: Literal[1] = 1
    event_id: str = Field(pattern=r"^evt_[0-9a-f]{32}$")
    producer: EventProducerV1
    event_type: str = Field(min_length=1, max_length=160)
    payload: dict
    occurred_at: AwareDatetime
    publication_id: str | None = Field(default=None, pattern=IDENTIFIER_PATTERN)

    @field_validator("payload", mode="before")
    @classmethod
    def json_payload(cls, value):
        return _json_data(value)

    @model_validator(mode="after")
    def bounded(self):
        if isinstance(self.producer, DeviceEventProducerV1):
            # Preserve the original node/item/depth budget, not a smaller budget
            # after adding the fixed internal producer/version metadata.
            DeviceEventV1(
                event_id=self.event_id,
                device_id=self.producer.device_id,
                event_type=self.event_type,
                payload=self.payload,
                occurred_at=self.occurred_at,
            )
            return self
        return super().bounded()

    @model_validator(mode="after")
    def distinct_producer_contracts(self):
        if isinstance(self.producer, DeviceEventProducerV1):
            if self.publication_id is not None:
                raise ValueError(
                    "Device events cannot claim an application publication"
                )
        else:
            if self.publication_id is None:
                raise ValueError("Application events require a publication declaration")
            if not re.fullmatch(APPLICATION_EVENT_PATTERN, self.event_type):
                raise ValueError("Application event type is invalid")
            _application_event_type(self.event_type)
        return self

    def content_digest(self) -> str:
        # Revalidation matters: frozen Pydantic fields still contain mutable dicts.
        checked = PlatformEventV1.model_validate(self.model_dump(mode="python"))
        encoded = json.dumps(
            checked.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(b"3mm:platform-event:v1\x00" + encoded).hexdigest()


class ApplicationEventPublicationReceiptV1(TimedPublicationModel):
    """Historical durable evidence; not a grant or a request to replay consumers."""

    publication_receipt_version: Literal[1]
    event_id: str = Field(pattern=r"^evt_[0-9a-f]{32}$")
    publication_id: str = Field(pattern=IDENTIFIER_PATTERN)
    producer: ApplicationEventProducerV1
    content_sha256: str = Field(pattern=SHA256_PATTERN)
    committed_at: AwareDatetime

    def matches(self, event: PlatformEventV1) -> bool:
        receipt = ApplicationEventPublicationReceiptV1.model_validate(
            self.model_dump(mode="python")
        )
        return (
            receipt.event_id == event.event_id
            and receipt.publication_id == event.publication_id
            and receipt.producer == event.producer
            and receipt.content_sha256 == event.content_digest()
        )


def validate_application_publications(
    contract: ApplicationEventPublicationsV1, application: ApplicationExtensionV1
) -> ApplicationEventPublicationsV1:
    """Cross-document validation only; package trust/current rights are separate."""
    checked = ApplicationEventPublicationsV1.model_validate(
        contract.model_dump(mode="python")
    )
    application = ApplicationExtensionV1.model_validate(application.model_dump())
    if (
        checked.module_id != application.module_id
        or checked.version != application.version
        or checked.service_artifact_sha256 != application.service.artifact_sha256
    ):
        raise ValueError("Publication declaration does not match application artifact")
    operations = {item.operation_id: item for item in application.operations}
    for declaration in checked.publications:
        operation = operations.get(declaration.operation_id)
        if (
            operation is None
            or operation.kind not in {"command", "job"}
            or operation.idempotency != "required"
            or declaration.event_type not in operation.emitted_events
        ):
            raise ValueError("Publication does not match its declaring command/job")
    return checked


def prepare_application_event(
    request: ApplicationEventPublishRequestV1,
    *,
    authenticated_producer: ApplicationEventProducerV1,
    contract: ApplicationEventPublicationsV1,
    application: ApplicationExtensionV1,
) -> PlatformEventV1:
    """Validate a candidate with a Core-derived identity; never mint a receipt.

    Future callers must obtain producer/contract/application from the current
    authenticated installed service, NOT from untrusted request metadata. This
    function supplies no operation-execution proof, authority check or commit.
    """
    checked = validate_application_publications(contract, application)
    producer = ApplicationEventProducerV1.model_validate(
        authenticated_producer.model_dump()
    )
    request = ApplicationEventPublishRequestV1.model_validate(request.model_dump())
    if producer.module_id != checked.module_id:
        raise ValueError("Publication producer does not own this application")
    declaration = next(
        (
            item
            for item in checked.publications
            if item.publication_id == request.publication_id
        ),
        None,
    )
    if declaration is None:
        raise ValueError("Publication ID is not declared")
    _json_data(request.payload, max_bytes=declaration.max_payload_bytes)
    validate_value(request.payload, declaration.payload_schema)
    return PlatformEventV1(
        event_id=request.event_id,
        producer=producer,
        publication_id=declaration.publication_id,
        event_type=declaration.event_type,
        payload=request.payload,
        occurred_at=request.occurred_at,
    )


def parse_application_publication_request(
    data: str | bytes,
) -> ApplicationEventPublishRequestV1:
    """Bound raw input and reject duplicate keys before model validation.

    Intended for the future signed transport after its authentication checks.
    Pydantic's general JSON parser alone is not the publication ingress parser.
    """
    return ApplicationEventPublishRequestV1.model_validate(_parse_publication_json(data))


def parse_application_publications(data: str | bytes) -> ApplicationEventPublicationsV1:
    """Use the same bounded, duplicate-free parser for immutable declarations."""
    return ApplicationEventPublicationsV1.model_validate(_parse_publication_json(data))


def _parse_publication_json(data):
    if type(data) not in (str, bytes):
        raise ValueError("Publication request must be JSON text")
    if len(data) > NODE_MESSAGE_BYTES:
        raise ValueError("Publication request byte limit exceeded")
    try:
        raw = data.encode("utf-8") if isinstance(data, str) else data
        if len(raw) > NODE_MESSAGE_BYTES:
            raise ValueError("Publication request byte limit exceeded")

        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Publication JSON contains duplicate keys")
                result[key] = value
            return result

        def invalid_constant(_value):
            raise ValueError("Publication JSON numbers must be finite")

        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=invalid_constant,
        )
        _json_data(value)
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("Publication JSON encoding/structure is invalid") from exc
    return value


def adapt_device_event(event: DeviceEventV1) -> PlatformEventV1:
    """Pure legacy view; retain real IDs/type/payload and existing naive-UTC rule.

    Does not replace device authentication, insert a row or change legacy wire
    serialization/cursors. Persistence and broker migration are a later slice.
    """
    # View the legacy JSON wire values (e.g. old Python tuples serialize to lists),
    # leaving the original caller's model and its wire serialization untouched.
    event = DeviceEventV1.model_validate(event.model_dump(mode="json"))
    occurred_at = event.occurred_at
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    return PlatformEventV1(
        event_id=event.event_id,
        producer=DeviceEventProducerV1(device_id=event.device_id),
        event_type=event.event_type,
        payload=event.payload,
        occurred_at=occurred_at,
    )
