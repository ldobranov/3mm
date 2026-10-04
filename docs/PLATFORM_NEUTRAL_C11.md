# C11 — Versioned capability contracts

Implemented locally, 2026-10-03. Shared Standalone, Hub/local Agent and application
layer; no Fleet dependency, ESP implementation, SDK bump or new hardware catalog.
Device protocol remains 1.0 and Application SDK remains 1.3. No deployment,
reset, commit or release was performed for this stage.

## Three separate identities

- `capability_id`: behavior, e.g. `gpio.digital.control`.
- `contract_version`: exact two-part version, e.g. `1.0`; no ranges, wildcards or
  inference from a `.v1` suffix.
- `provider_version`: implementation release, e.g. module `1.0.6` or firmware
  `0.2.0`. Neither selects the application contract.

The bounded shared `CapabilityContractV1` describes actions (arguments/result
schemas), optional state schema and event payload schemas. Provider registrations
attach `contract`; module manifests attach it only to capability registrations.
The common registry supplies `contract_version` and `contract` in registry-v2
queries and the AI/discovery context. One source of truth, not another registry.
Schemas belong to providers outside Core. The reference contract is in
`examples/mock_embedded/contracts.py`, not a Core GPIO special case.

The first schema dialect supports strict objects and bounded string, boolean,
integer, number and null values. Objects require `additionalProperties: false`,
up to 32 fields and depth at most four; numeric/string limits are explicit.
Actions/events are limited to 32 each; a complete contract fits 16 KiB and its
provider report must still fit the existing Node message limit. No arrays,
unbounded maps, refs, remote schemas, regexes or general JSON-Schema interpreter.
Extend this dialect only for a demonstrated generic need.

## Invocation and immutable queue evidence

Application bindings may specify `contract_version: "1.0"` in
`application-extension.json`. Existing signed SDK command submission is unchanged:
the application chooses its declared binding, not the device, provider or action.
Its existing argument/permission constraints still apply in addition to the
provider contract. Admin invocation accepts the same optional exact version:

```json
{
  "capability_id": "gpio.digital.control",
  "contract_version": "1.0",
  "action": "set_output",
  "arguments": {"channel": "gpio.output.1", "value": true}
}
```

Post to the existing `/api/v1/devices/{device_id}/capabilities/invoke`. Discovery
alone grants no permissions. The common queue also checks raw admin commands and
application commands, so bypassing this adapter does not bypass strict validation.

1. Queue: match exact version, declared action and bounded arguments. Require
   runtime feature `capability_contracts.v1`; unknown/legacy support is insufficient.
   Store a canonical SHA-256 `contract_digest` with the immutable command payload.
2. First dispatch: check the current effective registration, feature, version and
   digest again. Withdrawal, disable or incompatible/same-version schema change
   fails never-dispatched work as `not_dispatched`, with no delivery attempt.
3. Physical application permit: recheck binding/version/digest immediately before
   consuming the existing one-time permit. No fresh authorization after withdrawal.
4. Linux/mock runtime: verify against its actual active contract, not just Core's
   advertisement, before effects. The Linux physical journal records known contract
   rejection as `not_executed`; durable receipt replay does not repeat the action.
   Module withdrawal also removes the local service/contract, including on update.
5. Linux validates results after invocation; invalid result does not undo a physical
   effect or prove non-execution. Existing physical-journal uncertainty semantics
   remain. State schemas are checked at Linux state publication; event schemas
   describe payloads but do not replace the existing typed event/authorization
   boundary. Core retains historical result/event evidence rather than revalidating
   it against a newer provider and discarding it.

Already delivered work keeps its original delivery/receipt/uncertainty evidence;
it is not rewritten as `not_dispatched` or automatically replayed. Provider
contracts should be versioned immutably: changed semantics/schema need a new
contract version. The queued digest detects even accidental same-version changes;
it is not a global certification that providers implement identical semantics.
Signed installation authority and single-use permits remain separate requirements.

## Compatibility and persistence

Absent `contract` means **legacy/unknown**, not an inferred v1 contract. Legacy
registrations, requests, manifest/application serialization and providers retain
their old behavior. Optional fields are omitted when absent, including nested
manifest registrations, so old packages are not silently rewritten with new keys.
An explicit version cannot target an unknown contract. An explicit provider
requires an explicit consumer version; silently adopting its newest version is
not allowed. Registry-v1 module-only responses are unchanged.

Existing JSON registration fields and immutable command payloads store this data;
no database model/table change, Alembic revision, re-pairing or data rewrite is
needed. Existing identity, credentials, installations and desired state stay intact.
Use updated Core and Node runtime before opting into explicit contracts. Older
runtimes do not advertise enforcement and must not receive strict commands.
Older Cores/Nodes may reject newly explicit manifest fields; absence serialization
and legacy providers remain the supported compatibility path, not a security
downgrade. New schema/range support is not implied by device protocol 1.0.

Builder/discovery can see contracts, but automatic conversion of old widgets,
automations or generator templates is not part of this stage. In particular old
local automation definitions lack a version/digest binding and must not target
strict providers; the runtime refuses such invocations. Existing unversioned
GPIO packages and their automations continue to work. UI helpers and migration
of those optional consumers should be separate scoped changes.

## Reference and acceptance

The mock remains legacy by default for existing C0–C10 tests. Opt into its strict
reference contract on an updated Core:

```bash
python -m examples.mock_embedded --core-url http://localhost:8887 \
  --data-dir .runtime/mock-contract-node --versioned-contracts
```

Enrollment/administrator approval, credentials and transport remain unchanged.
This is simulation only, not ESP firmware or electrical acceptance.

Focused tests prove exact schema/version bounds, unchanged legacy serialization,
one SDK-1.3 application binding controlling Linux/module and firmware providers
with different release versions, Standalone and Hub roles without Fleet,
idempotent submission, module restart, runtime feature gating, unknown actions,
invalid arguments, raw-queue enforcement, update/withdrawal before first dispatch,
withdrawal after delivery denying a permit without erasing evidence, and local
contract rejection before driver/simulation effects. Existing Core/Agent/module,
provider and application regression checks also run. Live Hub/Zero, consumer UI
and future hardware/provider conformance remain separate acceptance gates.

Local evidence: the final contract/security test selection passed **45 tests**.
The wider compatibility selection passed **111 tests, 1 skipped** (POSIX-only
permission check on Windows). These are separate focused runs, not a full-suite
or live deployment claim. The size-boundary test also checks the final payload
after adding its digest, before any command is persisted.
