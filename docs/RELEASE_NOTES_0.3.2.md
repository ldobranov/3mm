# Core 0.3.2

Core 0.3.2 adds the first runnable CAP13 application-composition profile:
**local, read-only, one hop**. This is a pre-1.0 development prototype, not
completion of the whole CAP13 roadmap or a production-isolation claim.
These notes describe prepared source; publication occurs only after the tag's
full checks and reproducible builds succeed.

## Changes

- Manifest-v2 applications can declare exact versioned query exports and
  dependencies. Contract identity, input/output schemas and bounds must match.
- The common application configuration form offers matching local provider
  instances and exports without automatically selecting or approving one.
- M20 browser consent visibly presents the provider, contract, response limits
  and exact package/authority pins. Query rights start unselected. Provider and
  consumer each need their own current approval.
- SDK `platform.query(binding_id, arguments=...)` invokes the approved internal
  handler once. Its context identifies the calling application, not a delegated
  human user or shared administrator credential.
- Core admits and authenticates one short send; the independent Runtime waits
  for the bounded provider response through a response-only socket descriptor.
  Core holds no database/authority lease or occupied handler during that wait.
- Before releasing output, Core checks the signed response, original request,
  deadline/schema/size and both current installation/package/configuration/grant
  bindings. Revocation, renewal, disable and drift cannot silently reuse access.
  Pending results are bounded and process-local; timeout/crash never authorizes
  an automatic retry or durable replay.
- Resource discovery distinguishes saved permission, connected Runtime and
  unobserved provider execution. A general Runtime health result alone does not
  prove query support.
- The release saturation-test race is corrected without changing production
  deadlines or pool sizes. Overflow is checked while all eight test waits are
  still live, and the test cleans up its owned Runtime on failure.

## Components, data and upgrades

Core is **0.3.2**; Device Protocol remains **1.0** and Application SDK **1.3**.
Version axes are independent. New source with unchanged SDK numbering still
requires the corresponding current application-host artifact.

CAP13 requires coordinated current Core, Platform Runtime with
`query_execution_contract: 1`, and application-host/SDK code. A Core-only update
does **not** replace independent Runtime/host pins, approve grants or start
applications. Update and probe those components explicitly. An otherwise healthy
previous Runtime can still be selected by independent rollback; without the
query feature, CAP13 readiness remains refused rather than falling back.

There is no new CAP13 database table or migration relative to 0.3.1. Earlier
baseline migration and downgrade restrictions still apply: see
[0.3.1 data/recovery notes](RELEASE_NOTES_0.3.1.md#data-and-recovery). Preserve
verified database/key backups. An older Core directory alone does not restore
the database or independent components. No wipe or key reset is requested.

## Verification and limits

Exact local snapshot evidence and actual skips are recorded in
[WORKING_STATE](WORKING_STATE.md). Checks include real application-host and exec'd
Runtime processes, fresh revocation/drift fencing, Unicode output, invalid
responses, timeout/crash/no-retry behavior, artifact/rollback checks and current
frontend parsing/consent. These are targeted and partly mixed-platform checks,
not a completed full Python 3.13 / Node 22 integration or final-tag device run.

Push the reviewed preparation commit to `main` and wait for its automatic CI.
Then create a new annotated **`v0.3.2`** tag on that exact commit. Release repeats
the complete required checks and two byte-identical full/Node builds before
publishing all seven assets. Do not move or reuse the failed immutable
`v0.3.1`. A tag or draft is not publication; see [RELEASING](RELEASING.md).

Out of scope: commands, human delegation, recursive/remote composition,
entity/deep-link contracts and scoped-relational query providers. Native query
code is not proven pure or isolated; refusing output cannot recall an already
executed handler or prove rollback. Full CAP13, M21, WP5 and host/root
administration are not newly accepted. Terminal remains an independent package.
Publication does not deploy a device; smoke-test the exact published Core and
selected Runtime/host components separately after successful publication.
