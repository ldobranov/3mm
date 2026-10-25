# M20 — common Core trust and approval UX: action plan

Date: 2026-10-22. Status: proposed plan, not implemented or accepted security proof.
Scope: generic Core/M20 management, not a Terminal-specific exception.
M20/WP4 remains closed in its [accepted reviewed-native scope](EXTENSION_PLATFORM_V2_WP4_FINAL_ACCEPTANCE.md).
Whole M20, WP5 isolation and M21 acceptance remain separate.

## 1. Observed Terminal issue — information only

The owner's Raspberry screenshot shows `crypto.randomUUID is not a function`
at `http://rasp-3mm.local/terminal`, not `Application host: access_denied`.
Terminal's `m21TerminalTransport.ts` calls `crypto.randomUUID()` in
`newRequestId()` before `bridge.open()`. This fails before that session-open
request is sent. It is not evidence that the earlier VM stream/SQLite failure
has been fixed or reproduced, nor proof that a shell ran.

`randomUUID()` requires a secure browser context. HTTP localhost has a special
trustworthy-origin treatment that ordinary HTTP LAN/mDNS names do not have.
`getRandomValues()` is available outside secure contexts and can retain strong
request-ID generation for the explicitly supported trusted-LAN beta profile.
See [randomUUID](https://developer.mozilla.org/en-US/docs/Web/API/Crypto/randomUUID),
[secure contexts](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Secure_Contexts)
and [getRandomValues](https://developer.mozilla.org/en-US/docs/Web/API/Crypto/getRandomValues).

Record a separate Terminal correction: cryptographic IDs with unchanged format,
no Math.random/time fallback, no input replay, and tests with randomUUID absent.
Do not implement it as a Core permission bypass or enable insecure browser flags.
HTTP compatibility does not encrypt traffic or make web code-trust approval safe.
The existing local Terminal 1.0.3 preparation must be reviewed separately, not
overwritten or assumed to include this correction. No Terminal patch is made by
this plan.

## 2. Product outcome and first boundary

After one explicit installation-local bootstrap, an administrator should manage
supported application code trust and resource approval in the web interface,
without a new SSH script/review document for every application version.

Keep three distinct decisions: code trust, exact service resources and current
human access. A single guided UI can coordinate them but cannot equate them.
Core keys stay installation-local; never copy a VM key/review to another Core.
An ordinary Node is not automatically a separate Core trust administrator.

First delivery: **already installed, supported application packages**, exact
package/UI identities and existing authority/lifecycle adapters. Reuse existing
manifest-driven Extensions and approval machinery; no concrete application IDs
in Core. Do not claim arbitrary new-version staging, publisher auto-trust or
fleet-wide rollout in this first delivery.

## 3. Work sequence and exit criteria

### A. Fix the trust contract and protected administration boundary

- Document which changes require a new decision: executable package/UI bytes,
  rights, target identities, runtime privilege and recovery generation.
- Distinguish identical executable output with changed build metadata from
  actual code changes in the displayed diff. Keep provenance verification and
  exact build binding; do not silently ignore a different build hash.
- Define an administrator-only management surface with an origin/session not
  shared with executable extension UI. No extension imports or shared extension
  credentials there. Use authenticated transport for remote management; ordinary
  LAN HTTP is not the new code-trust approval channel.
- Specify explicit bootstrap, step-up confirmation, session/CSRF/origin rules,
  expiry, revocation and recovery. A password prompt in the current same-origin
  extension SPA alone is not this boundary.
- A web risk-acceptance decision must have an honest evidence type. Do not call
  the current local writer with fabricated `code_review_completed=True` and
  claim a manual source audit happened. Define its supported policy before use;
  preserve existing local manual-review records and the CLI recovery fallback.

Exit: a reviewed threat model and narrow API/state contract, including refusal
behavior when the protected channel is unavailable. No trust-writing HTTP route
is introduced before this contract is settled.

### B. Implement the common trust coordinator

- Reconstruct the actual installed package, verified UI build, supported runtime
  and current actor on the server; browser-supplied labels/hashes are not proof.
- Present source verification, known/unknown publisher, code changes and risks.
  Existing checksum validation is not a verified publisher signature.
- Bind each explicit decision to the exact artifact, installation, build and
  recovery generation; audit only safe metadata. Expired, stale, replayed or
  superseded decisions fail closed, without mutation replay or fallback grants.
- Keep approval separate from Apply, and service resources separate from human
  permissions. Never auto-recover keys, restore old grants or open a session.
- Avoid long artifact I/O or nested database readers under authority leases;
  preserve bounded checks and uncertain-operation ownership fences.
- Reuse existing persistence where its semantics fit. Any schema change requires
  an Alembic migration and preservation/recovery tests.

Exit: authenticated positive and negative API coverage, old native reviews still
valid under their existing rules, and no application-name-specific branches.

### C. Add one guided Extensions flow

- Show readiness as separate facts: runtime, code trust, service rights and human
  access. A missing capability must not be described as a missing review key.
- Sequence: inspect -> show code/risk/resource changes -> explicit decisions ->
  apply supported lifecycle steps -> freshly verify effective state.
- Coordinate required disable/enable transitions with the existing adapters;
  explain their effect before applying. Do not call an unsupported activation
  path or conceal an invalidated grant to avoid another confirmation.
- Preserve EN/BG, themes, dynamic registration, mobile use and recovery controls.
  No general visual redesign or new frontend framework in this work.
- Make changed code/new rights prominent; show no-code-change cases accurately.
  Do not call code approval a sandbox or successful queuing/session connection
  execution proof.

Exit: visual review and the same generic flow works for Terminal and a neutral
application, without SSH for each code-trust decision once bootstrap is complete.

### D. Verify and deliver one coherent candidate

- Targeted security checks: non-admin and extension-origin refusal, independent
  management credentials, changed artifact/build, expired/replayed decisions,
  revocation, interrupted apply and restored/stale authority.
- UI checks: truthful readiness/errors, state transitions and independent human/
  service permissions. Include HTTP LAN versus localhost/HTTPS compatibility in
  the separate Terminal request-ID regression.
- Owner-run live acceptance on Raspberry and VM: both supported generic apps,
  code-trust revoke, effective resource rights and preserved recovery history.
  Terminal prompt/output/resize/idle/cleanup remains a separate M21 outcome.
- Prepare exact Core and Terminal commit scopes separately. Preserve parallel,
  generated and private changes; no commit/push/tag/deploy by the assistant.
- Assistant prepares files and targeted commands; owner runs tests and commits.
  Avoid repeating full local suites after every small edit. Run complete final
  candidate checks and unchanged canonical CI/tag-driven release gates; skips
  remain skips. No release per sub-step and no weakening publication checks.

Exit: agreed evidence and remaining limits recorded before publication/update.

## 4. Later extensions — not hidden first-release requirements

- Generic staged/new-artifact activation and rollback through the WP3 lifecycle
  work, before claiming fully web-driven arbitrary application upgrades.
- Verified signed packages, publisher/key trust, namespace binding, rotation,
  revocation and explicit update policies. Signature validity is not safe code
  or resource authorization; no blanket trust in all future versions.
- Explicit enrolled-Core fleet policy/distribution without copying private keys
  or silently granting Node/Cloud/root authority.
- Broader hostile-code/backend/browser isolation under WP5; the administration
  channel boundary is required here, but is not whole-WP5 completion.

## 5. Current work remains distinct

Core commit `2fdc3df` is a targeted UI-authority snapshot correction, not this
feature or proof of the installed VM fix. Local beta.57 release metadata remains
a paused draft; this plan does not publish it or require immediate deployment.
Do not mix its previously reported tests with new trust-feature acceptance.
No live key, trust, permission or runtime change is made by writing this plan.
