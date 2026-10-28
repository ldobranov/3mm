"""Compose bounded read-only observations; never resolve or mutate bindings."""
from datetime import UTC, datetime
import json
from itertools import islice
import time

from three_mm_protocol.application_command_discovery import CommandDiscoveryV1
from three_mm_protocol.application_requirements import (
    ApplicationRequirementV1, ApplicationRequirementsRequestV1,
    ApplicationRequirementObservationV1, ApplicationRequirementsV1,
    assess_platform_requirements,
)
from three_mm_protocol.platform_transport import PlatformDiscoveryV1


def discover_requirements(client, requirements):
    from three_mm_application_sdk import ApplicationPlatformClient, ApplicationPlatformError, REQUEST_TIMEOUT_SECONDS

    # Validate the whole batch before the first connection. This is caller-owned
    # SDK configuration, not new manifest declarations or an activation policy.
    values = [item.model_dump(mode='json') if isinstance(item, ApplicationRequirementV1) else item
              for item in islice(requirements, 17)]
    raw = json.dumps({'requirements': values}, allow_nan=False)
    if len(raw.encode()) > 64 * 1024: raise ValueError('Requirement batch is too large')
    request = ApplicationRequirementsRequestV1.model_validate_json(raw)
    deadline = time.monotonic() + min(client.timeout_seconds or REQUEST_TIMEOUT_SECONDS, REQUEST_TIMEOUT_SECONDS)

    def observer():
        budget = deadline - time.monotonic()
        if budget <= 0:
            raise ApplicationPlatformError('Requirement observation exceeded its deadline',
                reason='deadline_exceeded', phase='observation_unconfirmed')
        return ApplicationPlatformClient(client.socket_path, client.instance_id, client.secret,
            diagnostics=client.diagnostics, timeout_seconds=min(budget, REQUEST_TIMEOUT_SECONDS))

    first = observer().discover_platform()
    platform = PlatformDiscoveryV1.model_validate(first)
    commands = {}; results = []
    assessment = assess_platform_requirements(request.requirements,
        transport_contract_version=platform.contract_version, operations=platform.operations)
    for support in assessment.requirements:
        requirement = support.requirement
        missing, supported, reason = support.missing_operations, support.supported, support.reason
        command = None
        if reason is not None:
            pass
        elif platform.authority_mode != 'enforced':
            reason = 'scoped_authority_required'
        elif requirement.binding_id is not None:
            if requirement.binding_id not in commands:
                try:
                    commands[requirement.binding_id] = observer().discover_command(requirement.binding_id)
                except ApplicationPlatformError as error:
                    # Invalid/authentication responses cannot become a benign
                    # optional-feature result. No fallback or retry is attempted.
                    if error.reason not in {'operation_unsupported', 'operation_denied', 'operation_failed'}:
                        raise
                    commands[requirement.binding_id] = None
            value = commands[requirement.binding_id]
            if value is None:
                reason = 'observation_unavailable'
            else:
                command = CommandDiscoveryV1.model_validate_json(json.dumps(value))
                if command.access != 'granted':
                    reason = 'access_required'
                else:
                    candidate = command.candidates[0]
                    if not candidate.compatible or not candidate.selectable:
                        reason = 'binding_unavailable'
                    elif candidate.readiness != 'ready':
                        reason = 'resource_unknown' if candidate.readiness == 'unknown' else 'resource_unavailable'
        results.append(ApplicationRequirementObservationV1(requirement=requirement, supported=supported,
            missing_operations=missing, met=reason is None, reason=reason, command=command))

    if commands and observer().discover_platform() != first:
        # Discard every detail if consent, recovery, process or transport identity
        # changed during observation. It is never a cached authorization lease.
        raise ApplicationPlatformError('Authority changed during requirement observation',
            reason='observation_changed', phase='observation_unconfirmed')
    status = ('blocked' if any(not item.met and item.requirement.required for item in results)
              else 'degraded' if any(not item.met for item in results) else 'satisfied')
    return ApplicationRequirementsV1(platform=platform, observed_at=datetime.now(UTC), status=status,
        requirements=tuple(results)).model_dump(mode='json')
