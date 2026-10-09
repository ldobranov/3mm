# Extension Platform v2 — beta.44 test acceptance

Status: test-release checklist, not completed live acceptance or WP4 closure.

## Scope and compatibility

This release delivers the implemented M20 package-inspection and installed-only
resource-authority slices, common lifecycle/recovery fences and application event
publication. It does not finish WP4, new-artifact staging/adoption, WP5 isolation,
remote distribution or commercial entitlement work.

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
   stage `v0.3.0-beta.44`, review preflight and explicitly install that version.
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
   Confirm compatibility/unsupported status is explicit. Ordinary users cannot
   approve/apply/revoke resources. Do not adopt a real business extension to make
   an unsupported screen appear supported.
7. Restart Core and recheck identity, compatibility status and preserved data.
   Record results before testing Raspberry; do not infer physical success from VM.

Read-only console checks after the update:

```bash
readlink /opt/3mm/current
systemctl is-active 3mm-core 3mm-agent 3mm-web 3mm-update-helper
curl --max-time 10 -fsS http://127.0.0.1:8887/ready
curl --max-time 10 -fsS http://127.0.0.1:8890/ready
```

## Scoped runtime acceptance — separate neutral fixture

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
- [Recovery fences](EXTENSION_PLATFORM_V2_RECOVERY_FENCES.md)
- [Release procedure](RELEASING.md)
