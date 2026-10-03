"""Negotiate with upgraded Core; retain inventory v1 for legacy Core only."""

import threading
import time

import requests

from three_mm_protocol.node_features import (
    CoreNodeProtocolV1,
    DeviceRuntimeFeaturesReportV1,
    DeviceRuntimeFeaturesSnapshotV1,
)


class RuntimeFeaturePublisher:
    def __init__(self, core_url, credential):
        self.url = f"{core_url}/api/v1/devices/{credential.device_id}"
        self.credential = credential
        self._lock = threading.Lock()
        self._last_check = float("-inf")
        self._last_exchange = float("-inf")
        self._declaration = None
        self._inventory_versions = (1,)

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
        headers = {
            "Authorization": f"Device {self.credential.credential_id}:{self.credential.credential_secret}"
        }
        response = requests.get(
            self.url + "/protocol", headers=headers, timeout=10, allow_redirects=False
        )
        if response.status_code in {404, 405}:
            self._inventory_versions = (1,)
            return
        response.raise_for_status()
        protocol = CoreNodeProtocolV1.model_validate(response.json())
        if (
            protocol.device_id != self.credential.device_id
            or 1 not in protocol.runtime_feature_schema_versions
        ):
            raise ValueError("Core protocol negotiation identity/schema mismatch")
        if not set(protocol.inventory_schema_versions) & {1, 2}:
            raise ValueError("Core supports no compatible Agent inventory schema")
        report = DeviceRuntimeFeaturesReportV1(
            **declaration,
            expected_revision=protocol.runtime_features_revision,
        )
        response = requests.put(
            self.url + "/runtime-features",
            headers=headers,
            json=report.model_dump(mode="json"),
            timeout=10,
            allow_redirects=False,
        )
        response.raise_for_status()
        snapshot = DeviceRuntimeFeaturesSnapshotV1.model_validate(response.json())
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
