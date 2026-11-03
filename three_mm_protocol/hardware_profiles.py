"""Exact Agent hardware-profile consent, distinct from application permissions.

A package may declare one immutable configuration profile in capability
metadata. Core renders that data; only trusted Agent handlers interpret it.
Neither inspection nor consent executes a capability or opens a device.
"""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

HARDWARE_PROFILE_FEATURE = 'module_hardware_profiles.v1'


def profile_digest(configuration: dict) -> str:
    raw = json.dumps(configuration, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if len(raw.encode()) > 8192:
        raise ValueError('Hardware profile is too large')
    return hashlib.sha256(raw.encode('ascii')).hexdigest()


class AgentHardwareProfileV1(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    schema_version: Literal[1] = 1
    profile_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    simulated: bool = Field(strict=True)
    configuration: dict


class AgentHardwareApprovalV1(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    schema_version: Literal[1] = 1
    device_id: str = Field(pattern=r'^dev_[0-9a-f]{32}$')
    package_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    profile_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class AgentModuleInstallRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    hardware_profile_approval: AgentHardwareApprovalV1 | None = None


def hardware_profile(manifest) -> AgentHardwareProfileV1 | None:
    registrations = [item for item in manifest.registrations
                     if item.kind == 'capability' and 'profile_sha256' in item.metadata]
    if not registrations:
        return None
    if ('agent' not in manifest.runtimes
            or not manifest.entrypoints.get('agent', '').startswith('builtin:')
            or not any(permission.startswith('hardware.') for permission in manifest.permissions)):
        raise ValueError('Hardware profile requires a trusted Agent hardware provider')
    digests = {item.metadata['profile_sha256'] for item in registrations}
    modes = {item.metadata.get('simulated') for item in registrations}
    if (len(digests) != 1 or len(modes) != 1
            or any(type(item.metadata.get('simulated')) is not bool for item in registrations)):
        raise ValueError('Hardware profile declarations disagree')
    declared = next(iter(digests))
    if type(declared) is not str or declared != profile_digest(manifest.configuration_defaults):
        raise ValueError('Hardware profile digest does not match configuration')
    return AgentHardwareProfileV1(profile_sha256=declared, simulated=next(iter(modes)),
                                  configuration=manifest.configuration_defaults)


def validate_hardware_approval(manifest, approval, *, device_id: str | None, package_sha256: str):
    """Fail closed before extraction, activation or side effects, on both peers."""
    profile = hardware_profile(manifest)
    if approval is None:
        if profile is not None and not profile.simulated:
            raise ValueError('Exact hardware profile approval is required')
        return None
    value = AgentHardwareApprovalV1.model_validate(approval)
    if (profile is None or profile.simulated or value.device_id != device_id
            or value.package_sha256 != package_sha256
            or value.profile_sha256 != profile.profile_sha256):
        raise ValueError('Hardware profile approval does not match device, package and profile')
    return value
