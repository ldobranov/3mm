"""One adapter onboarding path. Offers and health never select or grant resources."""

from datetime import UTC, datetime
import os
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field
from three_mm_protocol.device_capabilities import (
    CapabilityAdvertisementV1, CapabilityProviderReportV2, ProviderId, ProviderType,
)
from three_mm_protocol.capability_availability import (
    CapabilityAvailabilityReportV1, CapabilityHealthV1, declaration_digest,
)


class AdapterProvider(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    provider_type: ProviderType = "agent_adapter"
    provider_id: ProviderId
    provider_version: str = Field(min_length=1, max_length=64)
    capabilities: tuple[CapabilityAdvertisementV1, ...] = Field(max_length=64)

    def report(self, device_id, revision):
        return CapabilityProviderReportV2(schema_version=2, device_id=device_id,
            expected_revision=revision, **self.model_dump())

    @property
    def identity(self):
        return self.provider_type, self.provider_id


class ProviderAdapter(Protocol):
    def provider_declaration(self) -> AdapterProvider: ...
    def provider_health(self) -> tuple[CapabilityHealthV1, ...]: ...


class ProviderJournal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: int = Field(default=1, ge=1, le=1)
    device_id: str
    providers: tuple[AdapterProvider, ...] = Field(max_length=16)


class AgentProviderRegistry:
    def __init__(self, data_dir: Path, device_id: str, adapters: tuple[ProviderAdapter, ...]):
        self.path = data_dir / "adapter-providers.json"
        self.device_id = device_id
        self.adapters = adapters

    def _remember(self, providers):
        record = ProviderJournal(device_id=self.device_id, providers=tuple(providers))
        data = record.model_dump_json() + "\n"
        if len(data.encode()) > 65536:
            raise ValueError("Adapter provider journal is too large")
        if self.path.exists() and self.path.read_text() == data:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.path.with_suffix('.tmp')
        with temporary.open('w', encoding='utf-8') as stream:
            os.chmod(temporary, 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)

    def synchronize(self, transport, *, availability):
        current = {}
        for adapter in self.adapters:
            declaration = adapter.provider_declaration()
            declaration.report(self.device_id, 0)  # Validate bounds and reserved provider kinds.
            if declaration.identity in current:
                raise ValueError("Duplicate adapter provider identity")
            current[declaration.identity] = (declaration, adapter)
        previous = ()
        if self.path.exists():
            if self.path.stat().st_size > 65536:
                raise ValueError("Adapter provider journal is too large")
            journal = ProviderJournal.model_validate_json(self.path.read_bytes())
            if journal.device_id != self.device_id:
                raise ValueError("Adapter provider journal identity changed")
            previous = journal.providers
        desired = {item.identity: item.model_copy(update={'capabilities': ()}) for item in previous}
        desired.update({identity: value[0] for identity, value in current.items()})
        # Remember ownership BEFORE publishing: a lost acknowledgement/restart
        # must still withdraw a removed adapter. Never adopt other providers.
        ordered = [desired[key] for key in sorted(desired)]
        if ordered or self.path.exists():
            self._remember(ordered)
        failures = []
        for declaration in ordered:
            try:
                self._synchronize_one(transport, declaration, current.get(declaration.identity), availability)
            except Exception as error:
                failures.append(error)  # One optional adapter must not starve unrelated health reports.
        if failures:
            raise failures[0]

    def _synchronize_one(self, transport, declaration, current, availability):
        snapshot = transport.provider(*declaration.identity)
        report = declaration.report(self.device_id, snapshot.revision if snapshot else 0)
        if snapshot is None and not declaration.capabilities:
            return
        if snapshot is None or snapshot.schema_version != 2 or (
            snapshot.provider_version != declaration.provider_version
            or snapshot.capabilities != declaration.capabilities
        ):
            snapshot = transport.report_provider(report)
            if (snapshot.schema_version != 2 or snapshot.provider_version != declaration.provider_version
                    or snapshot.capabilities != declaration.capabilities
                    or snapshot.revision not in {report.expected_revision, report.expected_revision + 1}):
                raise ValueError("Adapter provider acknowledgement changed")
        if not availability or not declaration.capabilities:
            return
        health = current[1].provider_health()
        if {item.capability_id for item in health} != {item.capability_id for item in declaration.capabilities}:
            raise ValueError("Adapter health does not match its declaration")
        transport.publish(CapabilityAvailabilityReportV1(device_id=self.device_id,
            provider_type=declaration.provider_type, provider_id=declaration.provider_id,
            provider_version=declaration.provider_version,
            declaration_digest=declaration_digest(declaration.provider_type, declaration.provider_id,
                declaration.provider_version, [item.model_dump(mode='json') for item in declaration.capabilities]),
            observed_at=datetime.now(UTC), capabilities=health))
