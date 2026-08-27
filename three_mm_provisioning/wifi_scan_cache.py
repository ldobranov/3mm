"""Privacy-safe Wi-Fi scan cache shared with the captive setup service."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

from three_mm_provisioning.network_manager import WifiNetwork

WIFI_SCAN_CACHE_NAME = "wifi-scan-cache.json"
SETUP_SSID_PREFIX = "3mm Setup "


def merge_wifi_networks(
    *groups: Iterable[WifiNetwork],
) -> tuple[WifiNetwork, ...]:
    """Merge scans, remove the setup AP, and keep the strongest SSID entry."""

    strongest: dict[str, WifiNetwork] = {}
    for group in groups:
        for item in group:
            if item.network_name.casefold().startswith(SETUP_SSID_PREFIX.casefold()):
                continue
            previous = strongest.get(item.network_name)
            if previous is None or item.signal > previous.signal:
                strongest[item.network_name] = item
    return tuple(
        sorted(
            strongest.values(),
            key=lambda item: (-item.signal, item.network_name.casefold()),
        )[:30]
    )


def write_wifi_scan_cache(data_dir: Path, networks: Iterable[WifiNetwork]) -> None:
    """Atomically store non-secret scan results for the setup UI."""

    items = merge_wifi_networks(networks)
    if not items:
        return
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / WIFI_SCAN_CACHE_NAME
    temporary_path = data_dir / f".{WIFI_SCAN_CACHE_NAME}.tmp"
    try:
        temporary_path.write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "network_name": item.network_name,
                            "signal": item.signal,
                            "secured": item.secured,
                        }
                        for item in items
                    ]
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary_path, 0o644)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def read_wifi_scan_cache(data_dir: Path) -> tuple[WifiNetwork, ...]:
    """Load a validated scan cache, treating missing or invalid data as empty."""

    try:
        payload = json.loads(
            (data_dir / WIFI_SCAN_CACHE_NAME).read_text(encoding="utf-8")
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        return ()
    networks: list[WifiNetwork] = []
    for item in payload["items"]:
        if not isinstance(item, dict):
            continue
        network_name = item.get("network_name")
        signal = item.get("signal")
        secured = item.get("secured")
        if (
            not isinstance(network_name, str)
            or not 1 <= len(network_name) <= 32
            or not isinstance(signal, int)
            or isinstance(signal, bool)
            or not 0 <= signal <= 100
            or not isinstance(secured, bool)
        ):
            continue
        networks.append(WifiNetwork(network_name, signal, secured))
    return merge_wifi_networks(networks)
