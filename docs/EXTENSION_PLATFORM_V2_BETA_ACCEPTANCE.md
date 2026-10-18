# Extension Platform v2 — beta.52 test acceptance

Status: test-release checklist, not completed live acceptance or WP4 closure.

## Scope and compatibility

This release delivers the implemented M20 package-inspection and installed-only
resource-authority slices, common lifecycle/recovery fences, application event
publication and scoped private-file execution. It also includes the bounded
relational-storage foundation: exact grants, signed admission/atomic receipts,
explicit protected preparation/recovery and normal SDK execution for a verified
prepared database. It does not finish WP4, new-artifact staging/adoption, WP5 isolation,
remote distribution or commercial entitlement work.

Beta.52 additionally carries exact checkpoint, existing public identity,
consent-bound local-status and outbound peer-read adapters, plus the public
application UI host and exact-build reviewed UI profile. These are opt-in
resource/native reviews, not an automatic conversion of installed applications.
The current [closeout checklist](EXTENSION_PLATFORM_V2_WP4_CLOSEOUT.md) records
local integration evidence and the remaining common Standalone/Hub acceptance.

Existing applications remain in compatibility mode. Updating Core does not grant
new resources, adopt applications or record executable code as trusted. First
adoption requires a disabled application, a verified recoverable backup and a
locally administered code-trust record for the exact package. Unsupported adapters
remain unsupported; reviewed-native execution is not a security sandbox.

Device Protocol 1.0, Application SDK 1.3, dynamic navigation, roles, themes,
installation peers and Node Update remain. Concrete business/theme packages are
separate uploads. Publication does not update the VM, Hub or Zero.

## First live gate — disposable VM

1. Export a password-protected portable backup **before** upgrading and keep it
   off-device. Record the installed release and local Agent device ID. Snapshot
   the VM as an independent fallback; do not keep two active clones with one identity.
2. After all seven release assets are published, select Beta in System Updates,
   stage `v0.3.0-beta.52`, review preflight and explicitly install that version.
   If an earlier failed relational preparation left a recovery checkpoint,
   encrypted backup/restore is blocked. Preserve its evidence and a verified VM
   snapshot; an update is not recovery and does not authorize another preparation.
3. Require a durable successful update result. Check the active release and Core,
   Agent, Web and update-helper service health independently. Core/Agent readiness
   must pass and the Agent identity must remain unchanged.
4. Sign in with existing accounts. Check roles, dynamic extension routes/menu,
   selected theme and branding, installed versions and application data. Existing
   active applications must not silently become scoped/adopted installations.
5. In Extensions inspect a known local ZIP. Verify identity/version/declarations
   and current-to-candidate changes, with no install, grant or helper action merely
   from inspection. Cancel and verify the installed catalog has not changed.
6. Open Application access / Права на приложението for an existing application.
   Confirm the actual compatibility/review-required/enforced mode and package
   digest are shown. A missing/invalid local review key or unsupported scoped
   adapter must show an explicit blocked-review reason with no review/revoke
   controls or effective-grant claim. Invalid package/guard evidence still fails
   closed. Refresh must not create keys, trust or grants. Ordinary users cannot
   approve/apply/revoke resources. Do not adopt a real business extension to make
   an unsupported screen appear supported.
7. Restart Core and recheck identity, compatibility status and preserved data.
   Record results before testing Raspberry; do not infer physical success from VM.

Read-only console checks after the update:

```bash
readlink /opt/3mm/current
cat /opt/3mm/current/VERSION
systemctl is-active 3mm-core 3mm-agent 3mm-web 3mm-update-helper
curl --max-time 10 -fsS http://127.0.0.1:8887/ready
curl --max-time 10 -fsS http://127.0.0.1:8890/ready
```

## Scoped runtime acceptance — separate neutral fixture

A ready-to-build, headless Manifest v2 fixture is now available:
[WP4 Test](../modules/wp4-test/README.md). It exercises installation, admin echo
and bounded private-file access with no devices, connectors or background work.
It is a separate uploaded package, not a bundled Core/business extension. Its
safe first phase works without adopting an application. The installed-status UI
fix is included in beta.46, not the existing beta.45 tag. Successful status does
not make the adapter eligible or authorize resource execution.
This fixture covers private files only, not the event/command/connector and
relational acceptance gates below.

### Owner-reported beta.48 private-file regression — 2026-10-14

The updated Ubuntu/WSL VM reports beta.48, four active Core/Agent/Web/helper
services and both readiness endpoints ready with its unchanged Agent identity.
The existing private-file fixture retains effective grant revision 3, its original
text/digest and completed historical receipt. The owner confirmed a Core restart;
the same checks still pass, and the earlier denied request still has no receipt.
This accepts the private-file update/Core-restart regression only, not a whole
VM reboot, relational lifecycle, portable restore or WP4/M20 closure.

A separate [WP4 Relational Test](../modules/wp4-relational-test/README.md) now
provides a bounded own-database package, catalog-only upload/manual probes and
an explicit stepwise VM procedure for the beta.48 local-admin controls. Its
preflight does not provision accounts, authorize code or prepare/start a database.
Stop at a missing prerequisite or uncertain result; never bypass generic guards.

### beta.48 relational live preparation refusal — 2026-10-14

The separate relational fixture was cataloged, inertly registered and locally
native-reviewed; a fresh own-database read/write plan was approved and applied.
The first preparation created its namespace/key, but the hardened helper lacked
effective `CAP_SETUID` for the non-root migration child. Core retains an
`execution_unconfirmed` migration action; the runtime rollback records
`restored_not_started`, with no database or published active/relational metadata.
The fixture is stopped/disabled; the original key, staged wheel and checkpoint
were retained. This is failed relational acceptance, not WP4 completion.

The beta.49 fix retains only `CAP_SETUID` across helper exec without
removing `NoNewPrivileges`/kernel/filesystem protections, and checks effective
UID/GID transition capabilities before preparation effects. An opt-in real
systemd regression proves a non-root migration with zero child capabilities and
an early refusal without the prerequisite. It uses isolated disposable test
paths, not the installed fixture. Publication and the VM update/recovery are
separate gates; no installed checkpoint is cleared by this change.

Targeted verification: 38 isolated Linux cases passed including both real
systemd launch cases; a fresh wider isolated root run passed 95 migration,
installation and fixture cases. An earlier wider run's single signed-SDK refusal
passed separately and then in the complete rerun; diagnostics were added only
to the test harness, without production retries or permission fallback.

Beta.49's empty-bootstrap and prepared-candidate recovery contracts do not
cover this restored-empty migration checkpoint. A separate bounded
[restored-empty recovery/resumption](EXTENSION_PLATFORM_V2_RESTORED_EMPTY_RECOVERY.md)
is included in beta.50, not beta.49. Its controlled VM trial is
recorded below; beta.50 update acceptance remains a separate gate.
It retains the existing key/wheel and archives only verified empty rollback
evidence; migration needs a separate new consent. Do not erase markers, renew an
old ticket or rerun fresh preparation to manufacture successful acceptance.

### Controlled relational VM trial — 2026-10-14

The owner authorized a scoped prototype trial without another release. Verified
root-owned code snapshots and one-shot workers reconciled the exact empty
checkpoint and separately prepared the fixture, preserving the old failed source,
original key and all evidence. The trial exposed/fixed root-witness replacement
ownership and the `Type=simple` pre-exec principal race. Only this fixture has a
`Type=exec` override, initially ephemeral and then protected/persistent
for the separately authorized WSL reboot; installed beta.49 code remains immutable.

Prepared start, real signed SDK read/write, exact replay, changed-content conflict,
ATTACH refusal and revoke/regrant passed. One business record remains; the denied
write is absent. Subsequent controlled stop/recovery and new start passed, followed
by separate enable-only boot consent and an actual WSL shutdown/cold start. The
fixture started automatically; verified current-process sealed admission, kernel
principal, original key, grant revision 11, text/digest/count 1 and denied-write
absence were preserved. Core/Agent readiness and unchanged device identity passed.
The early Core-not-ready startup refused before factory import; the existing
systemd restart policy later admitted a fresh process without manual start/regrant.
This accepts the exact controlled fixture's restart/boot gate, not the public
unpatched beta.49 installation path, physical Raspberry boot or broader WP4
closure. See the [exact trial boundary and evidence](EXTENSION_PLATFORM_V2_RELATIONAL_VM_TRIAL.md).

Use only a reviewed headless fixture, mock devices and a non-effecting connector
on the disposable VM. Follow the public-contract and local key-administration
guides; never fabricate native trust or grants directly in the database.

- Review the exact installed bindings; approval alone must not apply rights.
- Explicit Apply permits only declared resources/actions under current authority.
  Changed package/configuration/resource identity and revoked rights must deny new work.
- Publish one bounded schema-valid event through the real signed SDK transport.
  Retry the **same persisted** ID/time/payload after a lost acknowledgement: require
  the original receipt and one journal record, not a second effect.
- Changed payload, foreign ownership, undeclared publication and device-event ID
  collisions must be denied. Exact owned history may remain readable after revoke/
  disable; a new event must not be admitted through that history exception.
- Device-event subscriptions remain device-only; publication does not implicitly
  authorize another application's consumption. Do not exercise turnstiles/payments.
- For a supported private-file fixture, review read and write separately, then
  verify exact owned paths, declared bounds and current grants through the SDK.
  Foreign/undeclared paths, revoked rights and changed content under one operation
  ID must fail. Lost acknowledgements must use the existing receipt, not replay.

## Relational storage boundary — not a public installation recipe

The automated root/non-root disposable tests exercise a protected, explicitly
prepared database, the normal host and signed SDK transport. They cover atomic
business/outbox/receipt commit, read-only/revoked access, metadata-only factory/
health, restart without migrations and uncertain completion without replay.
These tests do not prove the public first-install/upgrade coordinator or a
complete relational portable restore/key lifecycle.

Generic activation/native/source guards remain closed for relational packages.
Do not remove guards, edit grants/database rows or manually re-enable a business
application to reproduce an internal fixture. Beta.50 additions now
include preparation/resumption, bounded local adoption of a newer catalog
version after confirmed exact-source stop, prepared-database forward upgrade, readonly
published-upgrade/rollback confirmation, explicit completion of a partial
`restoring` checkpoint and closed local-administrator/helper commands. See the
[exact upgrade/restore boundary and admin flow](EXTENSION_PLATFORM_V2_RELATIONAL_UPGRADE.md).
The local adoption command executes no package code and creates no trust/rights;
fresh native review, normal resource approval and explicit migration are separate.
These are not capabilities of the unchanged beta.49 release, a general candidate
installer/adoption path or completed live upgrade/restore acceptance. Preserve
all pending recovery evidence; a blocked backup is not permission to delete markers.

The broader neutral Standalone/Hub, human/kiosk and recovery acceptance remains
an explicit WP4 gate; this checklist does not mark it complete.

## Restore and rollback safety

Test portable restore and injected failed-update recovery only on the disposable
VM with a verified snapshot/backup. Restored resource grants and in-flight effects
must be fenced; history is retained and new rights require fresh explicit review.
Do not treat restored approvals as fresh execution authority or automatically
repeat uncertain commands, HTTP mutations or fiscal operations.

Do not manually switch the release symlink over a newer database. Used authority
and application-produced event history prevent destructive schema downgrade.
Returning to beta.43 requires the matching **pre-upgrade** backup/code, not erasing
authority rows or force-dropping the new schema. Preserve failed recovery evidence.

## References

- [M20 plan and remaining closure gates](../EXTENSION_PLATFORM_V2_CORE_PLAN.md)
- [Public contracts](EXTENSION_PLATFORM_V2_PUBLIC_CONTRACTS.md)
- [Local review-key administration](EXTENSION_PLATFORM_V2_REVIEW_KEYS.md)
- [Authority apply](EXTENSION_PLATFORM_V2_AUTHORITY_APPLY.md)
- [Application event publication](EXTENSION_PLATFORM_V2_EVENT_PUBLICATION.md)
- [Private files](EXTENSION_PLATFORM_V2_PRIVATE_FILES.md)
- [Relational storage contract and remaining gates](EXTENSION_PLATFORM_V2_RELATIONAL_STORAGE_CONTRACT.md)
- [WP4 closure audit](EXTENSION_PLATFORM_V2_WP4_CLOSURE_AUDIT.md)
- [Recovery fences](EXTENSION_PLATFORM_V2_RECOVERY_FENCES.md)
- [Release procedure](RELEASING.md)
