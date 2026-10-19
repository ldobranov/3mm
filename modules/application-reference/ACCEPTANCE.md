# Scoped mock acceptance: installation and independent access

This is the post-update operator runbook, not an automatic installer or a grant.
Use only the reviewed mock target. Do not patch an immutable release, use the
synthetic sample device, or turn a real GPIO driver into a test target.

## Preparation gate

- The Core candidate must contain the kiosk timestamp-after-IPC correction.
  Published beta.53 does not; do not run its known-broken kiosk scenario.
- Take a current recoverable VM snapshot/export before changing the Hub. The
  built-in Standalone backup is not a supported Hub restore procedure.
- Confirm the isolated mock Agent is still online. Its temporary service has no
  boot enable and a four-hour runtime; preserve its identity/state if it expires.
- Confirm the actual registry reports exactly one registered/available provider
  for the target command, its reviewed contract version/digest and false output.
- Use the separately delivered app ZIP and its checksum. Test packages are not
  installed or trusted by a Core release. The default legacy reference and
  default output-only package remain unchanged.

## Normal platform flow (administrator preparation)

1. Inspect/upload the app through Extensions. This compiles UI source but grants
   nothing. Record the ZIP digest and target's verified compiled-build digest.
2. For a new app, use the existing initial compatibility installation, confirm
   health, then disable it before first scoped adoption. This profile's health
   does not submit commands; its schema migration creates no business tables.
   Do not submit a probe while still in compatibility mode.
3. Read `GET /api/v1/application-extensions/{module_id}/authority` to obtain the
   installation ID; never reuse the old relational fixture's installation ID.
   With local Core administration, inspect the exact target UI build and record
   completed source/build review:

   ```bash
   core_authority inspect-ui-build --installation-id <actual-id>
   core_authority native-review --installation-id <actual-id> \
     --artifact-sha256 <exact-zip-sha256> \
     --built-ui-sha256 <exact-target-build-sha256> \
     --review-document <completed-review.md> \
     --code-review-completed --accept-native-host-risk --accept-same-origin-ui-risk
   ```

   `core_authority` is the existing service-account wrapper. It prompts for a
   current administrator token without printing it. Never reuse the development
   machine's build hash as target attestation; toolchain changes may alter it.
4. In Application access review select only `command:acceptance`. Check target,
   provider, contract, action, argument bounds and TTL. Approve and Apply are
   separate steps. No connector, SQL, event, checkpoint or peer rights are needed.
5. Activate the same reviewed package/configuration. Activation changes the
   authority epoch: inspect status and perform a fresh review/Approve/Apply when
   needed. Require enforced mode, effective rights and no runtime blockers.
6. Independently grant `probe_use` to the chosen ordinary operator through
   `POST /api/v1/application-extensions/{module_id}/permissions/grants` with
   `{"user_id": <actual-operator-id>, "permission_id": "probe_use"}`. Use an
   administrator session only for this grant, not to impersonate the operator.
7. Separately create/claim a kiosk enrollment through the existing kiosk flow.
   Its credential is not a user login or service resource grant. Keep credentials
   private; never put them in the review report, ZIP or request-ID evidence.

Stop on stale/unconfirmed lifecycle or review responses. Preserve the exact
request/revision and use explicit inspection/recovery, not an automatic retry.

## Owner UI check

As the ordinary operator open `/reference/operations` on the VM Hub. Paste:

```json
{"channel":"gpio.output.1","duration_ms":50}
```

Click **Queue one mock request** once and save its request ID externally. Use
**Read existing outcome** on that same ID. The lookup itself may say `found`;
the nested command must say `succeeded`, and the reported output must return to
false. `queued`, `delivered`, `expired` and `unconfirmed` are not execution proof.
Do not resend an uncertain operation or create a replacement request ID.

Then verify the separate kiosk `/reference/register` route with its kiosk session,
not an administrator token. The kiosk intentionally has no operator lookup.
Administrative inspection can read its existing command result without resending.

## Negative checks and closure boundary

Revoke human access: the operator must be refused while SDK rights are unchanged.
Revoke kiosk enrollment: that kiosk must be refused. Revoke service command rights:
new effects must be refused independently of human access. A UI/build-trust refusal
may also hide the route; it must never fall back to compatibility. Reapprove only
the exact current review; disable/restart must not replay previous business work.
Record IDs, outcomes and command counts, never credentials.

Local tests of these paths are not live Hub/Node, full-release, reboot or recovery
acceptance. WP4 closes only against its complete closeout checklist.
