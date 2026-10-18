# M20 WP4 Block 1 — exact outbound peer-read management UI

Update **2026-10-17**: Core now has a dedicated exact outbound SDK reader. The UI
accepts current effective-grant status without the former runtime blocker, while
retaining safe presentation of older Core responses that explicitly report it.
The dated unavailable-runtime description below records the 2026-10-16 delivery;
current execution evidence is in the [WP4 closeout checklist](EXTENSION_PLATFORM_V2_WP4_CLOSEOUT.md).

Date: **2026-10-16**. Implemented/tested locally on top of
[the sealed installed approval cycle](EXTENSION_PLATFORM_V2_PEER_READ_AUTHORITY.md).
This is an administrator presentation/selection slice, **not peer SDK execution,
live VM acceptance, WP5 isolation or WP4 closure**.

## Behavior

- The existing Application access dialog displays the complete configured
  outbound read family: logical binding, exact peer/configuration field names,
  owner/incarnation/instance, package/service digests, receiver origin/module,
  normalized consent, public identity pins and v1/v2 metadata where applicable.
  The opaque v2 intent is not described as an approval. No private keys,
  credentials, enrollment requests, live values or state observations are shown.
- Each peer read is optional and begins **unselected** after a fresh status.
  The first explicit review obtains all public cards even for an empty choice.
  Every unselected binding stays visible and validated. An empty choice never
  means all peers. Earlier resource families remain required in full.
- Changing a checkbox clears the previous actionable plan and acknowledgment.
  Public draft cards remain visible, but a separate explicit review is required
  before acknowledging/approving. No request is automatically sent on selection.
  A returned plan must echo exactly the requested subset, not a wider/narrower set.
- Approve and apply remain separate, revision/fingerprint-bound actions. Choices
  are locked after approval; refresh discards them. Explicit revocation still
  requires confirmation. Current administrator, code trust, stopped-adoption and
  stale/current-resource checks remain owned by the existing backend.
- `peer_read_runtime_unavailable` is shown as **SDK not available**, never effective
  peer access. Applying a grant does not start the application, enable a peer SDK
  method or grant remote consent. Uncertain mutations receive no automatic retry.
- EN/BG labels and existing theme variables, native dialog focus containment and
  responsive layouts are preserved. No module names are hardcoded in Core.

## Closed presentation contract

The decoder accepts only 1–32 complete, distinct outbound read bindings, matching
the current installation/module/package, with one incarnation/service/instance/
public sender. It checks exact public field shapes, bounded identities and UTC
dates, canonical HTTPS origin syntax, normalized finite consent selections and
matching v2 metadata revision/consent. Shared identity/status resources must agree;
earlier required-scope semantics remain unchanged. Unknown fields, credential or
observation payloads, missing even-unselected bindings, aliases, raw-peer scope
substitution, inbound/mutation/receiver/SQL-mixed profiles fail before rendering
or offering approval. Earlier scope ceilings remain unchanged; 261 is additive
only when exact peer scopes are present.

The browser is **not a cryptographic verifier**: key/metadata digest syntax is
presentation validation, not signature, possession or remote-approval proof.
Core remains responsible for cryptography, current grants and fresh admission.
No backend guard, wire/SDK contract, database schema or service was changed here.

## Verification

- **47 new frontend tests**: 34 decoder cases and 13 dialog cases. They cover
  complete/partial/empty choices; all missing public fields and secret-bearing
  fields; foreign/mixed bindings; v1/v2 metadata; exact request echo; required old
  rights; expiry; changed-choice acknowledgment; uncertain/no-retry behavior;
  distinct approve/apply and revoke/cancel; EN/BG text and unavailable SDK status.
- **416 tests / 51 files passed** in the full frontend suite (57.83 seconds),
  including those 47 cases. Type check and production build passed. Existing
  fixture RouterLink/router/AbortSignal and intentional error-path warnings were
  not suppressed. After the final tiny label clarification, **104 targeted
  frontend tests** and the production build (4.88 seconds) passed again; these
  overlap the full run and are not added to its total.
- **152 existing backend contract cases passed** on Windows/Python 3.13.15
  (10.70 seconds): peer HTTP grammar and v9/old context vectors, including real
  signed-source binding serialization. These overlap previous coverage and are
  not additional unique release tests. No full release/POSIX suite is claimed
  for this frontend-only step; the prior native evidence remains separate.
- Browser/visual checks via computer-use: desktop light EN and dark BG; 390×844
  dark BG with long logical names, 64-device scrollable lists, expanded public
  pins and a 252-character opaque intent; empty/partial choice; separate approval
  and apply. The open mobile dialog had equal client/scroll widths (325 px),
  without horizontal overflow, and no captured browser error logs. Actions fit
  and wrap on mobile. Normal viewport was restored afterwards.
- All browser data and mutations were synthetic/in-memory in the isolated
  `.runtime/m20-peer-ui` fixture on port 5146. No live backend, identity keys,
  credentials, pairing, grants, VM/systemd or parallel M21 checkout were touched.
  Screenshots are under that ignored directory. A development hot reload reset
  the open dialog after the label edit; it was reopened and checked again.

No branch, version bump, commit, push or release. Next: **bounded SDK peer reads**
through the existing signed transport, with fresh guarded exact-resource/current-
grant resolution and revocation-race tests. Existing signing/enrollment/mutation
and unfiltered peer helpers remain blocked for exact-binding packages. The wider
Block 1/platform and neutral acceptance criteria still remain open.
