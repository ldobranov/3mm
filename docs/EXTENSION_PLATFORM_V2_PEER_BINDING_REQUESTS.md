# M20 WP4 Block 1 — exact peer-action requests

Date: **2026-10-16**. Implemented locally: additive descriptor validation,
read-only declaration comparison and negative runtime/adoption gates. **Positive
scoped peer execution is not implemented by this slice. Block 1 and WP4 remain
open.** This follows the [public peer-listing preparation](EXTENSION_PLATFORM_V2_PEER_READ_FOUNDATION.md)
and preserves the separate [scoped status read](EXTENSION_PLATFORM_V2_STATUS_READ.md).

## Public authoring contract

Optional `peer_bindings` in `application-extension.json` uses the exported
`ApplicationPeerBindingV1` model. The descriptor stays v1, module manifest v2,
SDK 1.3 and existing peer wire versions 1/2. No SDK method/action string, endpoint,
database model, key, grant or migration is added. Absent/empty bindings preserve
existing SDK 1.0–1.3 packages; nonempty declarations require SDK 1.3.

Example **request only**, not an executable package or approved permission:

```json
{
  "contract_version": 1,
  "binding_id": "primary",
  "direction": "outbound",
  "peer_id_config_key": "PEER_LINK",
  "operations": ["read", "enroll"]
}
```

The distributor names a logical binding and saved configuration reference, not an
installation-specific peer, host path, signing audience, owner or credential.
Package validation requires the referenced configuration property to be declared
as a string and the coarse platform request groups to match the manifest.
Configuration values and defaults are not evidence of an existing/current peer.

Every field is explicit; extra fields, coerced/unknown contract versions,
wildcards, unknown actions, duplicate operations, duplicate logical IDs and split
same-direction/configuration references are rejected. A descriptor has at most
32 bindings, each at most five unique actions. Raw descriptor parsing also
rejects duplicate JSON keys, including a hidden nonempty/empty opt-in.

| Direction | Separate requested actions | Existing coarse request groups |
| --- | --- | --- |
| Outbound | `read`, `enroll`, `rotate`, `revoke` | `installation.peers.enroll` |
| Outbound | `report` | Enroll + `installation.peers.report` + `installation.status.read` |
| Inbound | `read`, `approve`, `revoke` | `installation.peers.receive` |

`approve` additionally requires the existing receiver descriptor and its validated
machine-operation contracts. Receive permission alone does not create a receiver.
The coarse groups are compatibility declarations, **not grants for every action
in their row**. Each action is a separate request in the declaration diff.

`read` means an exact selected existing peer, not the current SDK's unfiltered
module-history `list`, an inbound discovery inbox or a wildcard. `enroll` means
completing the existing selected outbound enrollment, not creating a link or
changing consent. Inbound discovery, automatic receiver admission, generic proof
signing and consent editing are deliberately not requestable through this model.
Generic `installation.identity.prove` is not a prerequisite or an implied grant.

## Implemented inspection and refusal

The existing advisory package comparison emits one
`peer:<binding_id>:<operation>` change per action, with direction, configuration
key and a syntactically valid configured `peer_<32 hex>` ID. Invalid/missing
values remain unresolved and are not echoed; no peer table, private key, remote
endpoint or package code is accessed by this comparison. Valid-looking IDs are
explicitly **not verified current-peer evidence**. Reordering actions is not a
semantic change; changing target/direction is, and removal is not expansion.
Every such request remains marked `peer_runtime_authority_not_implemented`.

Actual installed-source resolution retains `peer_authority_unresolved`, even
with otherwise supported command/connector requests. A supported subset cannot
hide unsupported peers. Existing manager rules also refuse fresh native-review
records for an unsupported subject. An old approved plan or native attestation
cannot authorize a changed package. No internal authority version 9 is invented.

For a nonempty declaration, compatibility SDK peer calls cannot fall through to
the broad existing helpers. The common peer gate refuses inbound bootstrap/
callbacks and outbound resumable flows before private-key/network/extension
effects. The compatibility SDK's generic identity-proof call is also refused;
non-compatibility dispatch retains its existing denial allowlist. These refusals
do not erase peer records, rotate keys, send retries or change grants. Explicit
human administrator revocation/cleanup still retains its existing authority and
tombstones; it is not enabled as an application fallback.

The schema catalog says `declaration_validation: supported`,
`runtime_authority: not_implemented`, `compatibility_fallback: blocked`. A valid
package may be inspected; that is not operational peer support or sandboxing.
Unrelated compatibility application behavior is not declared newly privileged.

## Binding rules for the next executor — not yet implemented

The current read-only diff is not a grant plan. Before enabling even `read`, Core
must resolve the complete declared set from the actual saved configuration and
current owner/incarnation/instance. Reject missing, foreign, revoked, duplicate
resolved aliases and unsupported directions/actions without partial authority.
Bind the exact package/service, public sender/receiver identities, HTTPS origin,
target module, peer wire version and reviewed local consent/verified metadata.
Keep inbound business Owner/intent approval separate from Core service authority.

Permission identity and an **individual attempt's** credential generation,
freshness deadline, challenge/nonce and expected metadata CAS are different
inputs. Ordinary credential rotation may advance a valid generation for the same
reviewed binding; it must neither silently widen a grant nor treat an expired
credential as valid. Revoked/replaced peers and changed keys/consent/ownership
must still fail current admission. No arbitrary signer is exposed to implement
these effects.

Network operations need separate short guarded dispatch/completion phases,
durable exact request evidence, stale-response fences and explicit uncertain
outcome recovery. Do not keep a status-read lease across network I/O, call an
inner committing helper inside an outer authority lease, or replay automatically.
First implement the bounded exact-peer read resolver/admission/SDK result;
mutation/network actions remain refused until their own tested adapters exist.
The subsequent [peer-read source foundation](EXTENSION_PLATFORM_V2_PEER_READ_SOURCES.md)
now implements the internal source reader for both directions and wire versions;
versioned policy, grant admission and positive SDK execution are still not wired.

## Verification and limits

- Native Linux/Python 3.14.4: **1256 passed**, one Windows-only refusal skipped,
  in 468.66 seconds. That refusal passed separately on actual Windows. Execution
  uses an unprivileged UID in a disposable native checkout with private temporary
  paths, not `/opt/3mm-dev`, the installed Core or live VM data.
- Windows/Python 3.13.15: **866 passed, 24 POSIX-specific skips** in the main
  selection; the separate non-POSIX authority refusal passed as **1 additional
  case**. Those POSIX-specific cases execute in the Linux selection. Counts across
  platforms and prior runs overlap and are not added together.
- The selection includes the complete public protocol and SDK test directories,
  plus the selected Core ZIP validation, advisory diff, source/subject and
  authority management, actual signed Unix SDK refusal, pairing/receiver, public
  listing, identity and status regression files. It is not a full release suite.
  Existing real two-Core verified HTTPS **v1** acceptance also passes; v2 coverage
  is fixture-based, not new live-v2 or public-ingress acceptance.
- Production frontend build passed (12.21 seconds). No production frontend source
  changes or new visual acceptance are claimed for this contract-only slice.
- All eight changed production files and four new test files match native snapshot
  `/var/tmp/3mm-peer-bindings.zFqhrQ` byte-for-byte. Logs/JUnit are
  `.runtime/m20-peer-bindings-*`. Existing deprecation and fixture-key warnings
  remain visible rather than suppressed.

An initial Linux run stopped on a new test expecting to record native trust for
an unsupported subject. The existing manager correctly refuses that earlier
than expected. The test was corrected to preserve the stronger refusal and the
whole selection rerun; no production permission gate was weakened. Initial
evidence is retained separately and not counted as a second passing run.

No release, version bump, commit, push, live grant/key/service mutation or parallel
Ubuntu-project change is included.

This is request/inspection/negative-boundary delivery, not positive peer grants,
new visual acceptance, live v2 pairing, production ingress, WP5 isolation or WP4
closure. Existing VM beta.51 relational acceptance is not reopened or reclassified.
