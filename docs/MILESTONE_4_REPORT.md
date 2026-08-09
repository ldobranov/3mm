# Milestone 4 Report

Date: 2026-08-09  
Baseline: Raspberry Pi `rasp-3mm` (`aarch64`)  
Accepted release: `4d33c29-m4-final`

## Result

Milestone 4 is complete. Core, Agent, and UI now share a strict module manifest
v2 model. Core owns validated immutable packages and per-device lifecycle
records. Agent owns transactional staging, health verification, activation,
rollback, disable, retained data, capabilities, permissions, and registrations.

## Acceptance evidence

- Invalid archives, path traversal, undeclared permissions, incompatible
  protocol/runtime versions, and incompatible CPU architecture are rejected.
- Valid `org.3mm.acceptance` version `1.0.0` was delivered through the reliable
  command channel and activated on the physical Agent.
- Intentionally unhealthy `2.0.0` failed its health check; active `1.0.0`
  remained unchanged.
- Module data survived failed update, disable, and full 3mm release reinstall.
- Disable set `enabled: false` and removed registrations without deleting data.
- Core, Agent, and Web stayed active; readiness and health checks succeeded.
- 84 backend, Agent, and shared-protocol tests passed. Frontend type-check and
  production build passed.

Package handling, lifecycle, and navigation are registration-driven and contain
no concrete module-name special cases. Runtime permission declarations are an
enforcement foundation, not an OS sandbox; untrusted code remains deferred.

The next roadmap work is Milestone 5: mock GPIO using these module contracts.
