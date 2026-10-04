"""Negotiate with upgraded Core; retain inventory v1 for legacy Core only."""

import threading
import time

from agent.device_transport import HttpDeviceTransport, requests  # legacy test/embedding alias

from three_mm_protocol.node_features import (
    CoreNodeProtocolV1,
    DeviceRuntimeFeaturesReportV1,
    DeviceRuntimeFeaturesSnapshotV1,
)
from three_mm_protocol.capability_availability import AVAILABILITY_FEATURE


class RuntimeFeaturePublisher:
    def __init__(self, core_url, credential, *, transport=None):
        self.transport = transport if transport is not None else HttpDeviceTransport(core_url, credential)
        self.credential = credential
        self._lock = threading.Lock()
        self._last_check = float("-inf")
        self._last_exchange = float("-inf")
        self._declaration = None
        self._inventory_versions = (1,)
        self.availability_enabled = False

    def inventory_version(self, preferred, declaration_provider):
        with self._lock:
            now = time.monotonic()
            if now - self._last_check >= 30:
                declaration = declaration_provider()
                if declaration != self._declaration or now - self._last_exchange >= 300:
                    self._exchange(declaration)
                    self._declaration = declaration
                    self._last_exchange = now
                self._last_check = now
            if preferred in self._inventory_versions:
                return preferred
            if 1 in self._inventory_versions:
                return 1
            raise ValueError("Core supports no compatible Agent inventory schema")

    def _exchange(self, declaration):
        protocol = self.transport.protocol()
        if protocol is None:
            self._inventory_versions = (1,)
            self.availability_enabled = False
            return
        if (
            protocol.device_id != self.credential.device_id
            or 1 not in protocol.runtime_feature_schema_versions
        ):
            raise ValueError("Core protocol negotiation identity/schema mismatch")
        if not set(protocol.inventory_schema_versions) & {1, 2}:
            raise ValueError("Core supports no compatible Agent inventory schema")
        declaration = dict(declaration)
        # Registry v3 declares the C14 health contract using an EXISTING wire
        # field; a new field would break older strict protocol-1.0 parsers.
        if 3 not in protocol.capability_registry_versions:
            declaration["features"] = [feature for feature in declaration["features"] if feature != AVAILABILITY_FEATURE]
        report = DeviceRuntimeFeaturesReportV1(
            **declaration,
            expected_revision=protocol.runtime_features_revision,
        )
        snapshot = self.transport.report_features(report)
        if (
            snapshot.device_id != self.credential.device_id
            or snapshot.source != "advertised"
            or snapshot.declaration is None
            or snapshot.declaration.model_dump(mode="json") != declaration
            or snapshot.revision
            not in {
                protocol.runtime_features_revision,
                protocol.runtime_features_revision + 1,
            }
        ):
            raise ValueError("Runtime feature acknowledgement mismatch")
        self._inventory_versions = protocol.inventory_schema_versions
        self.availability_enabled = AVAILABILITY_FEATURE in declaration["features"]
