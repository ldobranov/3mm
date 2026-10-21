# 3mm 0.3.0-beta.56 — prepared candidate

Status at preparation: **not committed, tagged, published or installed**. The
latest published baseline remains beta.55. This candidate contains one local M21 repair and the
already accepted M20/WP4 closure record; it is not another WP4 implementation
round or a Node/Cloud Terminal release.

## Included

- Correct the output-read handoff when a worker reply reaches Core before the
  worker's send task finishes. One bounded handoff is allowed; a second read
  while provider output is genuinely pending is still refused.
- After worker IPC loss, close the channel and independently verify the exact
  pinned cgroup. Only confirmed OS cleanup plus lifecycle audit releases the
  owned capacity. Occupied, missing-proof or audit-failure cases stay fenced;
  the spent request cannot be reused and input is never resent.
- Add fixed phase/category diagnostics without terminal data, credentials,
  tickets or raw exception details.
- Record [owner acceptance of WP4](EXTENSION_PLATFORM_V2_WP4_FINAL_ACCEPTANCE.md)
  on 2026-10-21, preserving its explicit reviewed-native limits and historic
  incomplete/failed evidence. Whole M20, WP5 and M21 remain separate.

## Verification

| Current-source check | Result |
| --- | --- |
| Owner-run complete isolated Linux/Python 3.14.4 suite | 4,784 passed; 604 skipped; no failures/errors (24m47s) |
| Owner-run complete deployment / Application SDK | 416 passed; one opt-in systemd skip (6.33s) |
| Earlier focused Linux/Python 3.14.4 M21 regression | 112 passed; no skips; overlaps the full run |
| Complete Core frontend, Windows/Node 24.19.0 | 492 tests / 56 files passed; type-check and production build passed |
| Formatting, unchanged frontend/Terminal source and local document links | Passed |

The suites overlap and are not added as unique coverage. Warnings remain visible.
The systemd skip requires an explicitly disposable environment; it is not OS
proof. No installed service, owner database, key or grant was changed. Python
3.13/Node 22 remain the canonical CI/release runtimes. Local complete checks are
finished; the exact-commit CI/publication gates below remain separate.

The owner's complete run collected 5,388 cases and used a dedicated fresh test
venv with the development requirements installed. The copied backend fixture's
fixed database path alone was redirected into the disposable test directory;
tracked assertions, time limits and installed state were unchanged. The earlier
incomplete old-development-venv attempt stopped at collection and is not counted
as a completed run. The 604 skips and existing 14,608 warnings remain explicit.

The first local frontend run passed 491 cases and timed out after five seconds
in the unchanged shared-bootstrap test. The complete sequential repeat passed
all 492 cases without changing source, assertions or timeout. Existing test
warnings remain visible; local Node 24 is not the canonical Node 22 CI gate.

The worker race was reproduced deterministically against the old implementation
and passes with the repair. Local protocol/PTY reproduction also exercised the
actual Terminal 1.0.2 provider through SDK, Core ASGI and worker IPC. That separate
fixture substitutes its isolation assertion/cgroup observer: it is **not** proof
of the installed systemd/OS boundary and is not shipped as production code.

The owner VM reached Connected under beta.55 and subsequently lost its stream.
The first exception was not captured, so the repaired race is a verified cause
of this failure pattern, not a proven forensic explanation of that VM incident.
No stable installed-VM result is claimed yet.

## Publication gates still required

Follow [the existing release procedure](RELEASING.md): explicit reviewed
commit/push, canonical Python 3.13/Node 22 CI, exact-tag checks and reproducible
full/Node artifacts. The completed local suites above need not be repeated for
this results-only documentation update. Historical beta.55 checks are not added
to the beta.56 counts. Skips remain explicit, never passes.

No tag or GitHub Release exists merely because VERSION and these notes changed.
The live installation is left untouched during preparation. After publication,
update the recoverable test VM and follow the
[bounded return test](M21_LOCAL_TERMINAL_TEST.md#beta56-return-test).

## Compatibility and scope

- Keep the separately installed **Terminal 1.0.2** package unchanged. There is
  no Terminal version bump, rebuild or automatic reinstall. Exact native/UI
  trust, service-resource approval and separate current human permission remain
  required. Updating Core does not create or restore those rights.
- No database migration, dependency, Device Protocol 1.0 or Application SDK 1.3
  change. Optional session runtime remains off by default. Existing immutable
  deployment, rollback and authority checks are retained.
- Local/self-provided restricted temporary workspace only; no host/root
  administration, SSH/remote Node/Cloud relay, attach/detach, automatic reconnect
  or uncertain-input retry. No WP5-wide malicious-code/browser isolation claim.
- Keep an independent recoverable Hub VM snapshot/export. Built-in encrypted
  backup/restore remains Standalone-only; do not start a second WSL installation
  on the owner Hub's shared application ports during acceptance.
