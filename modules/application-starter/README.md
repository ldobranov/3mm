# Official minimal application: Note

This is the bounded CAP21 authoring profile: a Manifest-v2 application with
one operator UI, an application-owned SQLite note and an optional selected
resource. It uses the current public Python SDK and `@3mm/ui/v1` /
`@3mm/application-ui/v1`. No Core or Agent runtime change is needed to install it.
This source example is excluded from the installed Core runtime payload.

## Create a separate application

From the 3mm checkout, choose a new directory, unique module ID and route:

```powershell
python -m tools.extension_dev init .runtime/my-note --module-id org.example.my-note --name "My note" --route /my-note
```

The destination parent must exist; an existing destination is never replaced.
Creation updates the public descriptors and fixture identities, validates the
actual package rules and writes a project guide. It does not execute tests or
implement your domain just by renaming the example. Keep the internal Python
package isolated in the application's own wheel; no new Core branch is needed.

## Local UI preview

```powershell
python -m tools.extension_dev preview .runtime/my-note
```

Open `http://127.0.0.1:5178`. Stop the preview with Ctrl+C. `--port` chooses a
different explicit local port; an occupied port fails rather than silently
moving the preview. Nothing listens on the LAN. `--frontend` can select an
existing Core frontend toolchain for a project outside the checkout.

The visibly labelled simulation uses the project's `preview/host.ts` and the
current public UI components. It has EN/BG, light/dark and a narrow 390px stage.
Switch scenarios without remounting the editor to try missing/revoked edit
access, unavailable provider, missing resource approval, lost save reply or
a conflicting revision. Changes apply to the next request; use the application's
Reload control to read current simulated access and saved state. Reset changes
only disposable in-memory data in this tab.

Preview is not an installed Core, a permission authority or physical provider.
The mock covers only this example's public-host surface. Update it with the UI
and tests when developing another domain. Trusted project code can execute in
the developer browser/process; preview is not hostile-code isolation. It accepts
no Core URL/token and performs no installation, grant approval or hardware action.

## One local check and build command

From a developer checkout with the existing Python development environment,
Node and locked frontend/compiler dependencies available:

```powershell
python -m tools.extension_dev check .runtime/my-note --output .runtime/my-note-1.zip
```

For this repository's Windows environment, use `.\.venv\Scripts\python.exe`
instead of `python` when the system Python does not have the project dependencies.
Use `--frontend <path>` to select an existing Core frontend toolchain;
`COMPILED_UI_NODE` can select an existing Node executable. CI uses Node 22. The
command never runs npm/pnpm/pip installs, downloads, API login, upload, grants,
activation, restart or hardware output. Missing dependencies cause a clear stop.
Do not share Windows and Linux native Node dependencies between environments.

## Inspect contracts before running code

```powershell
python -m tools.extension_dev catalog
python -m tools.extension_dev catalog .runtime/my-note
```

Both commands print deterministic JSON for editors and automation. The first
describes this checkout's current public contracts, SDK/UI errors, transport
budgets and local authoring limits, with hashes of their source files. Structural
schemas come from the actual public models; cross-document semantic rules remain
in the referenced validators rather than a second copied policy.

With a project argument, the catalog builds and validates the candidate package
in memory and includes its exact source/package hashes, full application
declarations and review requirements. It does not import the application, execute
tests or migrations, compile UI, install dependencies, prompt for credentials or
contact Core. Unsupported authoring profiles are distinguished from valid package
declarations; they are not silently called checkable. Use `check` for executed
verification and artifact publication.

This is **not an installed capability inventory**. Declared permissions are not
grants, a declared resource is not an available provider, and an error code alone
does not prove whether a request was sent or permit a retry. Installation still
requires current Core validation, exact-package approval and resource selection.
`schemas` remains the structural-only export; `catalog` adds source references and
local declaration inspection, not runtime authority.

## Generate the UI operation client

The example and newly created projects declare `generated_client` in
`development.json`. Their UI calls the generated `createApplicationClient(host)`
methods rather than spelling raw operation names and payloads at every call site.

```powershell
python -m tools.extension_dev generate-client .runtime/my-note
```

After changing operations, input/output schemas, permissions, audiences or the
package version, explicitly regenerate an existing client:

```powershell
python -m tools.extension_dev generate-client .runtime/my-note --replace
```

An identical file is unchanged. Replacement is explicit and accepts only an
unedited file produced by this generator for the same module. Other files are not
overwritten. Explicit replacement retains the displaced source under the
project's `.runtime/client-recovery/` and reports `recovery_file`; it is excluded
from source packaging. It may briefly leave the target absent while publishing
the new file exclusively. If another editor writes the target meanwhile, that
file is not overwritten: generation stops and retains/restores the prior source
without replacing the other writer. Inspect the reported recovery file after a
refusal. `--output source/frontend/other-client.ts` chooses another local file;
its existing parent directory must be inside that project's frontend source.
Keep `generated_client` pointing to the file the UI actually imports. Project
creation regenerates the client for the new identity automatically.

Queries take a typed payload; commands additionally require the caller-owned
original `idempotencyKey`. Internal-only operations are not exposed. Each method
calls the public host exactly once, propagates its result/error and never retries,
creates an identity, grants access or changes audiences. TypeScript catches
misspelled fields, missing required fields, wrong scalar types and invalid literal
enums. Integerness, lengths, patterns, extra fields on nonliteral objects and other
runtime JSON constraints still require current Core/service validation. Returned
types are not an independent runtime validation of the host's response.

The generator supports explicit object/array/scalar schemas, required/optional
fields, primitive enums and nullable types. Unsupported references/combinators or
unrepresentable mixed additional-property schemas stop generation; they never
silently become `any`. `tests/client.types.ts` holds positive and expected-negative
compile cases; the declared `type_tests` are included in strict type checking.

## What the common check verifies

The `check` command:

1. Freezes supported source files in a disposable local directory; refuses
   escaping paths/symlinks and checks for source changes before publishing output.
2. Builds a deterministic pure-Python service wheel and Manifest-v2 ZIP, then
   uses the actual current package/semantic validator. Service imports from
   private Core internals fail an authoring lint; this is not a security sandbox.
3. Refuses a missing/stale declared generated client before executing project
   code. Imports the declared migration factory from the exact packaged wheel in a
   separate bounded local process. Uses disposable SQLite data to check clean
   creation to the declared target, database and foreign-key integrity,
   reopen/reapply without changed content, upgrade from each earlier revision,
   and rollback after an injected failure in each revision of the current plan.
4. If an explicit previous archive is selected, verifies its fixture-seeded data
   upgrade as described below. Otherwise the report says `not_requested`.
5. Runs project Python tests and verifies that all three declared denial
   scenarios actually execute. A failure, skip or missing scenario is not green.
6. Runs the project's UI tests, strict Vue/TypeScript check (including declared
   compile-only cases) and the actual
   installed-package UI compiler. It does not rebuild the main Core frontend.
7. Writes a new ZIP, `.report.json` and `.checks.log` outside the source project.
   Existing files are never overwritten. Use a new output name for a fresh run.

The normal output is a short readable summary. Add `--json` for automation. The
report includes the source hash, exact ZIP hash, compiler/build identity, executed
checks and validated declarations: operation permissions/idempotency, resource
contracts, storage and SDK/Core compatibility. This is a pre-installation review,
not a claim that code trust, installed grants or a provider are ready.

The migration result contains revisions/counts and verification flags, not table
content. A broken factory, invalid plan, missing target or failed integrity/reopen
check stops at `migrations` without publishing a ZIP. The declared target must be
the last revision, and repeated factory calls must declare the same revision
sequence; a later untested migration cannot silently pass. Rollback is
per revision: already completed earlier migrations remain. The fault probe also
refuses partial changes left by callbacks, including premature commits.
Only public SDK SQLite
storage is supported by this bounded profile; a scoped relational declaration
requires its own lifecycle adapter and currently refuses this check. No service
factory is started by the migration probe. Migration code is still trusted local
developer code, not a security sandbox. This check does not certify migration of
an old installed package, real business data, backup/restore or privacy retention;
add those domain-specific fixtures to project tests before shipping an update.
This local profile allows up to 32 migrations, 16 MiB per disposable database
and a 60-second worker budget. Timeout ends that worker, not arbitrary processes
that developer code may start; neither check nor preview is process isolation.

## Verify an update from a previous package

Keep the exact checked previous ZIP outside the project. Change the independent
application version consistently in all three descriptors and the service wheel
artifact path; add forward migrations when the schema changes. Update versioned
test fixtures as appropriate and regenerate the client. Do not overwrite a
published package with different bytes under its old version.

```powershell
python -m tools.extension_dev check .runtime/my-note --previous-archive .runtime/my-note-1.zip --output .runtime/my-note-2.zip
```

The candidate must be the same module with strictly newer SemVer precedence.
`development.json` names a standalone `upgrade_fixture` under `tests/`:

- `seed(application)` uses the old packaged service/data and returns a bounded
  JSON object containing expected outcomes.
- `verify(application, expected)` uses the candidate service to assert retained
  domain data/receipts and returns `None`. It must not change logical database
  contents/history, even when reading an original idempotent receipt.

The shipped fixture saves a disposable note with the old service and verifies
the note and actor-scoped original receipt after upgrade and reopen. Adapt it to
your domain; an empty/no-op fixture does not prove preservation of your data.
The fixture may import standard-library/public SDK and that phase's packaged
service, not sibling project test helpers. Two distinct isolated Python processes
avoid importing old and new service versions into the same module cache. Both use
the current public SDK, declared configuration defaults and no platform client;
this is not a test of real installed configuration, credentials or provider access.

The runner pins ZIP/wheel/fixture hashes, checks old revision history as a prefix,
integrity and reopen. New migrations also receive injected-failure rollback probes
against copies of the old seeded data. A same-schema version update reports
rollback as `not_applicable`; successful schema changes are not automatically
downgraded. Failure refuses the new ZIP while retaining the local report/log.
The 60-second budget is per direct worker, with the same database/dump limits as
migration checks. No installed database, backup, device, deployment or grant is
touched. This is trusted developer-code execution and fixture-specific evidence,
not hostile-code isolation or proof for every historical business database.

## Review the two built archives

```powershell
python -m tools.extension_dev compare .runtime/my-note-1.zip .runtime/my-note-2.zip
```

Use `--json` for a machine-readable comparison. Both exact ZIPs are validated
against the checkout's current package rules. The report identifies both hashes
and data revisions, distinguishes changed service bytes from declaration changes,
and names added, removed or edited permissions, operations and resource bindings.
It does not print configuration values, schemas or service code. A different
application or different bytes reusing one version are refused. The comparison
does not decide upgrade order, source-code equivalence, migration correctness or
installed approval. No app execution, Core connection or installation occurs.

Failures exit nonzero with their exact stage; missing, empty, skipped or invalid
test evidence is not a pass. Complete log/report evidence is prepared before
exclusive ZIP publication. `package_publication` distinguishes `not_published`,
`published` and an unconfirmed publication; a late filesystem error does not
pretend an already-created ZIP is absent. Inspect that exact hash and evidence
before using such an artifact. Outputs require a filesystem supporting hard links;
unsupported publication stops without overwriting existing files. Detailed logs
remain local and can contain test output; inspect them before sharing.

Project tests run trusted developer code, **not isolated hostile code**. Their
mock denial scenarios do not certify a running Core, device or provider. The
separate repository integration test `backend/tests/test_application_starter.py`
also exercises this exact packaged service through actual Core human permissions,
sealed service grants, revocation and signed Runtime SDK discovery, using
disposable data. It doubles external process launch/response transport and never
accesses a physical device. A local pass is not installation consent or live
hardware acceptance.

## Read and change the example

- `manifest.json`, `application-extension.json`, `compiled-ui.json`: public
  declarations. The build tool fills the service wheel's SHA256; its source
  placeholder is not used as an execution/trust proof.
- `service/starter_app`: SDK-only service and forward migration `0001`.
- `source/frontend/Notes.vue`: host operations and themed shared editing controls;
  English/Bulgarian messages follow the host's current presentation locale.
- `source/frontend/client.generated.ts`: source-derived UI operation methods;
  regenerate explicitly after declaration changes, never edit it by hand.
- `tests`: note persistence/isolation/conflicts, permission removal and provider
  loss, typed-client and public-host UI behavior, plus the previous-package data
  fixture. `development.json` names these inputs.

Use `init` for a separate identity, then update the service, UI and tests. Use only
standard-library/public SDK/protocol runtime imports in this minimal profile.
It is a pure-Python profile, not a dependency resolver, general package builder,
arbitrary native-wheel builder or universal conformance suite. For editors and
automation, `python -m tools.extension_dev schemas` exports the current public
structural schema catalog as JSON on stdout. Cross-document semantic validation
still belongs to `check`; schemas do not approve native code or access.

Saving uses an explicit idempotency identity scoped to the authenticated user
and an expected note revision. Repeated exact requests read their original
receipt; changed payloads, stale revisions and missing permissions refuse.
An explicit public-host `access_denied` response explains that editing access
was refused, retains the draft and makes the editor read-only. Removing only
`note_write` preserves viewing through `note_read`; restoring edit access needs
an explicit reload of current permissions and the saved note, not a save retry.
Restart preserves the app-owned migration/data. A lost UI acknowledgement keeps
the draft and stops further saves until the user explicitly reloads the saved
revision; it never replays a save. There is no scheduler or automatic polling.
This is a shared operational demonstration note, not a personal-data application.
Do not enter personal data; retention/export/erasure and quotas need their own
application policy before turning it into a different product.

## Select a resource after separate approval

The note works with no device configured. Optional binding `command:resource`
uses `RESOURCE_DEVICE_ID` and the existing versioned
`gpio.digital.control.set_output` contract for channel `gpio.output.1`.
It is deliberately **only observed**; the service has no operation that submits
a hardware command. Resource failure or revocation cannot corrupt the note.

If you explicitly choose to try the package on a device:

1. Upload the generated ZIP through Extensions and prepare its configuration.
2. Select the target in the ordinary application configuration, review the exact
   package/native-code trust and optional resource, and separately approve them.
3. Assign `note_read` to users who can view it and `note_write` to users who can
   edit it. A platform administrator flag is not substituted for app permission.
4. Open `/starter-note`. No route load, note save or resource observation writes
   to hardware. Disable/revoke and removal use the ordinary lifecycle controls.

These are optional manual acceptance steps, not actions performed by `check`.
