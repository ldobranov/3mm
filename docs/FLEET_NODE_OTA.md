# One-Node runtime update from Fleet

Status: Stage 1 implemented locally, not deployed/published or physically accepted.
This updates the complete Node runtime, not an installed Agent module package.
The published beta.24 / Fleet 0.1.6 do not yet provide this feature.

## Delivery stages

1. **Node execution foundation (current):** versioned handoff, root-only staged
   artifact validation, narrow local helper, detached immutable installer and
   durable outcome. The minimal artifact includes the helper without Core.
2. **Hub/Agent transport:** administrator-scoped catalog and preparation from
   official Node releases, authenticated per-device download, bounded disk use,
   Agent handoff and runtime/outcome reporting. Zero downloads from its Hub;
   it need not access the internet. Never accept arbitrary URLs or shell commands.
3. **Optional Fleet UI:** version/current status, check, prepare, review and
   explicitly install one device; reconnect and show the final outcome.
4. **Physical acceptance and publication:** one-time Node bootstrap adds the
   helper, then real Fleet update, failed-health rollback, network/reboot and
   lost-response tests. Only then advertise subsequent updates without SSH.

No automatic fleet-wide updates, rollout groups, Cloud enrollment or concrete
business-extension behavior are included. Internet/catalog loss must not stop
existing local work. An already verified staged package can later be installed
without a fresh public-network download.

## Implemented Stage 1 boundary

- `three_mm_protocol/node_updates.py`: strict versioned metadata, explicit
  confirmation, exact device/release/archive identity and an aware-UTC bounded
  handoff deadline (at most 120 seconds). No caller-controlled path or command.
- `agent/node_update_client.py`: bounded AF_UNIX request/status client. It does
  not execute root commands and is not yet wired into the public command loop.
- `three_mm_runtime/node_update_helper.py`: root / `3mm` peer checks, persisted
  operation identity and replay conflict detection; fixed detached worker.
- `deployment/apply_node_update.py`: validation and existing immutable installer.
  Final success is distinct from acceptance/delivery and requires healthy target
  runtime with the original device identity and a responding update helper.
  `rolled_back` means the previous release is verified healthy and unchanged
  after an installer failure; it also covers failure before release mutation.
- Root-controlled state: `/var/lib/3mm-node-update`, outside service-owned
  `/var/lib/3mm`. Socket: `/run/3mm-node-update/helper.sock`. The helper reads
  only an already root-prepared `staging/<operation_id>/release.tar.gz`.

At this stage there is intentionally **no remote preparation endpoint** and no
public command handler. The helper cannot be used end-to-end through Fleet yet.
Root staging is an internal/test boundary, not a customer installation procedure.

Operations use `nodeupd_<32 hex>` and carry `device_id`, `release_id`, SHA-256,
original `created_at`/`expires_at` and `confirmed_install: true`. Local envelopes
are `{"action":"apply","request":...}` and `{"action":"status"}`; responses
carry a validated operation or no prior operation. Safe outcome states are
`accepted`, `running`, `succeeded`, `rolled_back`, `failed`, `unknown`.
Lost replies/restarts reuse the identity. Unresolved interrupted work stays
unknown, not queued again. A missing unit or delivery acknowledgement does not
prove successful installation.

History is limited to 128 operations and refuses new work when full. Stage 2
must add controlled retention/recovery; active or unknown attempts must never
be discarded simply to permit another install. The detached worker has its own
45-minute systemd deadline for the entire process tree, independent of helper
restarts.

The archive must match Node/ARMv6/Python 3.13 metadata, expected digest and
release identity, and pass bounded archive/path checks. The existing installer
retains its deployment lock, offline wheelhouse, current/previous links, health
checks and rollback. Agent identity, Hub binding and GPIO state remain outside
the release tree. The root helper is deliberately separate from the Hub's
Core-dependent update/backup helper.

The new helper service survives normally across boots; its detached install
worker does not depend on the old Agent or helper remaining alive. Rolling back
to a Node release predating the helper removes its unit and restores the older
recovery-only service set. Do not claim remote management after that downgrade.

## Verification

Local Stage 1 check: **61 passed** across protocol/client, helper/worker,
minimal package, Node installer, preflight and recovery tests.

Focused tests cover strict input/deadlines, helper authorization, durable replay,
unknown interruption, archive rejection, fixed execution, outcomes and packaging.
Tests use temporary files and fake service/installer runners; no live device,
network mutation or GPIO action is performed. Unix peer/permission behavior and
real Zero installer/restart acceptance must also pass on Linux/target hardware.

Stage 2 must additionally test device revocation, cross-device download denial,
staging limits, original deadline preservation and status after Agent restart.
Only the final operation outcome may be labeled "Updated" in Fleet.
