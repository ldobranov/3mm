# C7 — Common Node security validation

Implemented and checked locally 2026-10-03. Applies to Standalone, Hub/Fleet,
local Linux Agent and independent runtimes through the common Device/Node
Platform. No hardware-specific rule, SDK/transport bump, migration, deployment,
commit or release. This is contract hardening, not production certification.

## Authentication, identity and authority

Existing unique per-device secrets remain hashed in Core; there is no fleet-wide
secret. Protected routes bind path/report identity to the authenticated device.
Human/application tokens cannot impersonate device credentials. Revoking the
credential or device denies subsequent protected requests without re-pairing.

`require_device` now refreshes cached ORM credential/device records before
checking revocation and approval, and rejects oversized authorization headers.
Runtime feature replacement additionally validates report identity at its
service boundary, not only in the HTTP route. Existing provider ownership,
revision, duplicate-provider conflicts, Core-owned disable and actor/application
permissions remain unchanged. An advertisement grants no execution authority.

The Linux publisher no longer follows redirects on authenticated publication,
poll, state or execution-permit requests. A redirect is not an acknowledgement:
pending publications remain queued. Negotiation, enrollment and the independent
reference transport also disable redirects. Existing Core-address binding is
retained; this is not TLS enrollment, automatic trust transfer or cloud pairing.

## Payload and time limits

`three_mm_protocol/node_security.py` defines platform-independent finite JSON:
string keys, valid UTF-8, <=16 nesting depth, <=8192 visited values/keys and
<=64 KiB compact validated JSON. Inventory/provider/feature contracts retain
their existing equal or tighter limits. The common heartbeat, event, result,
capability state and desired/reported state DTOs now apply the generic bound.

The real Core app installs `DeviceBodyLimitMiddleware` before route parsing
for POST/PUT/PATCH on `/api/v1/devices/...` and `/api/v1/pairing/enroll`.
It checks actual received bytes even without or with a false Content-Length;
ordinary bodies are <=64 KiB including wire whitespace/encoding. Excess bodies
return `413`; malformed, non-finite or excessive-structure JSON returns `400`.
Existing DTO field/schema violations retain `422`. Unrelated APIs and GET
responses are not claimed to be uniformly bounded by this middleware.

The administrative command queue has one bounded compatibility exception for
existing `module.install.payload.package_base64`: the existing 10 MiB module
archive allowance, its base64 expansion and 64 KiB normal metadata/envelope
budget. Other command payloads and module metadata remain <=64 KiB. Runtime
ZIP/hash validation remains authoritative; accepting a queue envelope is not
validating or installing the archive. Service-level queue validation also
protects non-HTTP callers. Invalid queue payloads retain the route's `409`
command-conflict response. Other APIs such as multipart module upload retain
their existing package validation, not this device JSON exception.

Commands require timezone-aware creation/expiry, a positive TTL <=86400 seconds
and bounded finite payloads. Existing tighter signed-operation constraints and
deadline checks before/after authorization remain. Core validates the outgoing
desired-state envelope before committing updates so response overhead cannot
make a newly saved state unreadable to the Node. Legacy report/event timestamps
remain accepted where previously supported; no false claim of uniformly strict
timestamps or synchronized physical clocks is made.

## Replay, uncertainty and buffers

The Linux generic command receipt cache now binds the canonical command
content (including identity/type/payload/deadline, excluding its receipt alias)
and terminal result with SHA-256 proofs in a private sidecar. The old result
file remains readable. A legacy receipt without a proof fails closed as
`unknown`; changed content/mismatched result fails as `conflict`. Neither
automatically repeats work or fabricates a previous success. An interrupted
two-file write can lose confirmation, not permit blind replay.

This cache does not prove that non-physical operations survived a crash before
their first receipt was written. Real physical commands still use the separate
SQLite physical journal: durable pending intent before dispatch, strict replay
binding, deadline/permit checks and quarantine after uncertain execution.
Tests include crashes before and after the simulated effect and expired/offline
authorization. No exactly-once guarantee for external mechanisms is claimed.

The publisher's persistent outbox remains limited to 500 deduplicated records,
but overflow now reports an error and preserves pending records rather than
silently evicting the oldest ones. Replacing the same deduplication key remains
allowed. This is backpressure, not guaranteed unlimited event capture: existing
in-memory queues, receipt/event retention, disk failure recovery and production
capacity policies remain explicit runtime/operations responsibilities.

Credentials/temp credential files reject symlink targets and retain private
POSIX storage modes; an existing credential file is restricted on load.
Credential/proof hashes are bindings, not encryption or tamper-proof storage
against a compromised runtime. Firmware must supply equivalent private
credential storage; actual firmware OTA signing/storage security is later work.

Node Update uncertainty is preserved: only validated terminal operation evidence
or proven absence of dispatch releases the gate. A late timeout/failure result
after dispatch is not consent to retry an external effect.

## Audit

The Core-owned `runtime.features.updated` and `capability.provider.updated`
event types cannot be submitted through the device event endpoint (`403`).
Core still produces these events through its authenticated registry/feature
services; unchanged retries do not duplicate them. Existing pairing/revocation,
actor/application and command audit remains. Runtime events/results are
authenticated reports, not independently verified evidence of physical action.

## Evidence and limits

Focused tests cover common HTTP authentication/cross-device/revocation,
cached-ORM revocation, identity at the feature service, reserved audit events,
body/chunk/JSON limits, preserved module archive budget, desired envelope
overhead, replay proofs, legacy receipts, redirects/backpressure, physical
uncertainty, application permits, Node Update and the Linux role/schema baseline.
Windows/Python 3.13 final focused regression: **80 passed, 1 skipped in 21.43s**;
74 existing dependency/deprecation warnings, no test failures. New helper/test
files pass Black; changed tracked files pass whitespace checks. C7 introduces
no frontend changes, so no frontend build was needed.

Reproduce from the repository root, PowerShell:

```powershell
$c7Tests = @(
  "three_mm_protocol/tests/test_node_security.py"
  "agent/tests/test_node_security.py"
  "backend/tests/test_node_security.py"
  "backend/tests/test_node_contract_conformance.py"
  "agent/tests/test_physical_command_journal.py"
  "backend/tests/test_device_runtime_features.py"
  "backend/tests/test_application_commands.py"
  "backend/tests/test_node_update_delivery_route.py"
  "backend/tests/test_device_state_routes.py"
  "backend/tests/test_node_protocol_baseline.py"
)
.venv\Scripts\python.exe -m pytest -q @c7Tests --tb=short
```

The POSIX permission/symlink test is skipped on Windows; Linux file permissions
have not been verified on a live Pi in this stage. TLS, secure enrollment outside
a trusted test LAN, physical timings, deployed Fleet consumers and real firmware
are not proven by these tests. Revocation does not undo an already dispatched
effect or claim to eliminate every concurrent in-flight request race.

[C8](PLATFORM_NEUTRAL_C8.md) now checks the mixed-version migration/portable
restore/rollback matrix and handles legacy receipts/state/commands exceeding
the new limits without deletion or replay. C9 must prove both runtimes together
plus signed application execution. No real ESP support is claimed before that
acceptance.
