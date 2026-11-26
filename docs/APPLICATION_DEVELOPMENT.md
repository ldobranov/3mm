# Building applications

Start here for a new application on the current source tree. An application owns
its service, UI, data and tests; Core supplies reviewed execution, access and
resource contracts. Do not add a Core branch, route or database table for a
concrete application.

The supported starting profile is the [Note starter](../modules/application-starter/README.md):
Manifest v2, a pure-Python service, public-SDK SQLite storage and compiled Vue UI.
Its [project instructions](../modules/application-starter/AGENTS.md) are copied
by `init` for developers and coding assistants. Existing projects do not receive
template changes automatically.

From the platform checkout, run `python -m tools.extension_dev examples` to
find a starting point for a UI, import/export, scoped search, report task or
opt-in inbox. `python -m tools.extension_dev examples inbox --json` returns
the matching guide, source and test paths with hashes. “Present” means the
reference files are in this checkout, not that the tests ran or any permission
was granted. A named example missing from a trimmed checkout exits nonzero.
For reproducible evidence from the optional table/search/report/inbox references,
see the [Linux authoring reference check](DEVELOPMENT_CHECKS.md#authoring-reference-check).

## Agree on the application boundary

Before implementation, establish the module ID, route, purpose and acceptance
cases. Identify owned data, who can read/change it, required versus optional
resources, background work and any physical effects. Keep configuration, a user's
unsaved draft and persisted business data distinct.

Prefer existing public contracts. A new device integration belongs in a provider
or driver implementing a generic capability, not in application-specific Core or
Agent logic. If a required public mechanism is missing, describe the gap and
agree on that separate platform change; do not bypass it with internal imports,
direct device access or SQL against Core.

This source layout is not compatible merely because an older host advertises the
same SDK version. Use a Core build that actually supplies the current imports and
features. Treat the current catalog and validators as authoritative, not an old
example, historical plan or copied schema.

## Create and inspect a project

Run from the platform checkout with its existing Python development environment.
Use `.\.venv\Scripts\python.exe` on Windows, or the selected environment's Python
on Linux. Do not mix Windows and Linux Node dependencies.

```powershell
python -m tools.extension_dev init .runtime/my-note --module-id org.example.my-note --name "My note" --route /my-note
python -m tools.extension_dev catalog .runtime/my-note
```

The destination's parent must already exist. An existing project is never
overwritten. Choose an independent application ID and route; renaming the Note
example does not implement a new domain. The application may live outside the
platform checkout; pass its path and, where needed, `--frontend PATH_TO_FRONTEND`.

`catalog` inspects real current schemas and validated declarations without running
application code or contacting a device. With no project argument it describes
public contracts, source identities and tooling limits. `service_profiles`
shows the Full application and minimal Node Agent defaults from their actual
unit files; these are not measured limits. With a project, `project.resource_budgets`
lists declared operation/task deadlines, task queue bounds, connector caps and
optional SDK storage bounds. Missing storage declarations grant nothing.
For installed measurements see the [resource profile contract](../deployment/systemd/README.md#resource-profile-contract).
Inspect only relevant
contract sources after this entry point; do not load the entire historical plan.

## Project files and supported imports

```text
my-note/
  AGENTS.md                      development rules carried with the project
  README.md                      project-specific workflow and decisions
  manifest.json                  identity, compatibility and configuration
  application-extension.json     service, operations, rights, resources and storage
  compiled-ui.json                declared UI entrypoints and navigation
  development.json                tests, scenarios, client and upgrade fixture
  service/starter_app/             private application code and migrations
  source/frontend/                Vue UI and generated operation client
  preview/host.ts                  disposable UI simulation
  tests/                          service, UI, types and retained-data checks
```

All three descriptors share the exact module ID and application version. The
service wheel path must match `development.json`'s `python_package` and that
version. The builder supplies the actual wheel digest. Never invent a digest,
edit a built archive or replace different bytes under a published version.

| Responsibility | Public entry |
| --- | --- |
| Service context, storage, migrations and platform client | `packages.application_sdk` |
| Shared models when needed | `packages.protocol` |
| Shared themed Vue controls | `@platform/ui/v1` |
| Reviewed application operations and presentation | `@platform/application-ui/v1` |

Use relative imports for the application's own code. Do not import `backend`,
`agent`, `components`, `deployment`, `tools`, Core frontend aliases/stores/router,
or removed `three_mm_*` / `@3mm/*` packages into the application. Do not vendor
Core or a second Vue runtime. Operational IDs, environment keys and signing
domains are contracts, not branding: do not rename them to match a product label.

## Implement data and operations together

Declare bounded input/output schemas, audiences, human permissions and idempotency
for every operation. Keep read-only queries separate from commands. Validate
business rules inside the service as well as at the public boundary. Derive the
actor from the supplied context, never from a caller-supplied user or role.

Use the application's supplied storage and explicit forward migrations. Do not
create tables on every handler call, open Core's database, store live data beside
source files, or replace a migration with reset/delete instructions. Keep database
transactions short; no network/provider wait while holding a write transaction.

A command keeps one original idempotency identity and a durable receipt scoped to
its actor and application. The same ID with different input must refuse. For
editing shared data, use an expected revision and retain the draft on conflict.
A timeout, HTTP 409, missing receipt or lost reply is not proof of non-execution.
Read the original outcome or current saved revision as the contract allows;
never create a replacement ID to replay an uncertain change.

Classify personal data and define retention/export/erasure and quotas before
using the example for real users. Test retained data and receipts across upgrades.
The starter's shared demonstration note is not a personal-data policy.

For a package that declares personal data, **Extensions → Inspect package**
and the local check report (`review.data_practices`) identify the exact
export, erasure and retention declarations and their human permissions. This
is not consent, a subject lookup or evidence that a handler works. Keep the
business operations in the application. Exercise them on disposable data:

- Give two test subjects distinct records. An authorized export for one must
  not include fields or records belonging to the other.
- Deny an account without the declared authority, and repeat after revocation;
  the failed operation must neither disclose data nor partially erase it.
- Run the reviewed erasure once and read its receipt with the same original
  request ID after a lost response. Verify the other subject is unaffected.
- Test the retention boundary on both sides of its cutoff, or document that
  data stays until explicit erasure. State which downloaded backups, prior
  exports and external copies are outside the local handler's reach.

## Keep permissions and resources separate

Review three independent boundaries: native package/code trust, current human
operation access, and the application's selected platform resource scopes.
A visible route, declared permission, selected device or administrator label is
not proof that all three are satisfied. Service and Core checks remain required;
disabled controls alone do not enforce access.

For application-owned tabular import/export, the
optional [data tools](../libraries/data_tools/README.md) bind reviewed bytes to
their exact column schema and validate before mutation. Keep subject filtering,
current permission, SDK transaction and durable request receipts in the app.
The same optional library supports a current-access, partitioned search index
and a printable table. The worker-only packaging example keeps the report in
the app database, sends only a small receipt to Core, and rechecks access
before publication. None of these helpers grants file, network or task access.

For a personal “report ready” message, see the [opt-in inbox](../libraries/data_tools/README.md#opt-in-in-app-notifications).
It lives in your app, uses current recipient access, and records at most one
notice for the original intent. Listing notices is read-only. It does not send
email, grant access to the report or add a poll to Core.
For temporary inbox limits the example can hand one bounded retry schedule
to the existing task API. Commit its original ID first; recover by lookup,
never by submitting a replacement. A successful task is not a read receipt.
Its `export_metadata` helper supplies only the current recipient's retained
notification metadata to a separately authorized personal export; it is not
a whole-application export or a general diagnostics attachment.

Declare optional resources explicitly. Own-data operations must remain usable
when an unrelated optional provider is absent, disabled or unapproved. Resolve
current resources through SDK discovery, not hostnames, hardcoded device IDs,
private HTTP calls, `/dev` access or direct GPIO/I²C from the application. The
Note example only observes its optional resource and never sends a command.

Scheduled tasks, events, connectors and hardware commands need their own declared
contracts, bounded work and current authority. Do not implement a busy loop or
poll every second by default. Choose independent, bounded UI/data intervals;
stop unnecessary browser polling when hidden or unmounted. Permission loss and
provider loss need explicit UI states, not generic success or automatic approval.

## Build the interface from shared controls

Use Vue 3 and TypeScript with the existing public components, not a new UI library
or private Core component. For forms start with `UiSurface`, `UiForm`, `UiField`
and `UiButton`; use `UiEditorForm`, `UiTable` and `UiCollectionEditor` when needed.
Use `UiRecordPicker` in single-selection mode for one record and multiple mode
only for a real collection. A small fixed choice need not become a searchable
multi-select. Inspect component props/examples instead of guessing their API.

Opening a page must not create a command, reserve a resource or prepare an approval. A button
labelled **Refresh status** should perform status reads only. If preparing a
change records an intent or takes an exclusive lock, give it a separate explicit
action. In the component test, open the page, refresh, and simulate a failed
read: assert **zero mutation calls** in all three paths. Then request the
change explicitly and assert that it prepares just one intent; allowing the
change is still a separate action where the contract requires it.

Read locale from `host.presentation`; subscribe and unsubscribe without
remounting the editor or losing drafts. Use theme tokens and scoped styles,
EN/BG labels, loading/empty/error/read-only states, keyboard labels and a narrow
layout. Ordinary controls must remain useful without opening diagnostic details.
Show technical IDs and recovery details separately from the main task.

Use the generated operation client rather than raw operation strings or ad hoc
`fetch`/login/token handling. After changing declarations or version:

```powershell
python -m tools.extension_dev generate-client .runtime/my-note --replace
python -m tools.extension_dev preview .runtime/my-note
```

Preview listens only on loopback, normally port 5178. Stop it with Ctrl+C. Its
project-owned scenarios cover normal, read-only, unavailable/unapproved resource,
lost reply and revision conflict states. It is a UI simulation, not the Python
service or installed authorization. Adapt those scenarios to the real domain.

## Check and build before installation

Node 22 and the existing locked frontend/compiler dependencies must be available;
the command does not install or download them. Follow
[development checks](DEVELOPMENT_CHECKS.md) when preparing that toolchain.
If you use `--frontend PATH`, select the complete platform frontend for the
current OS. The same directory supplies Vitest, type checking and the final
UI compiler. A missing compiler is a toolchain error, not permission to fall
back to another checkout or to publish a partly checked package.

```powershell
python -m tools.extension_dev check .runtime/my-note --output .runtime/my-note-1.zip
```

This checks real package validation and reproducibility, current generated
client, packaged SQLite migrations/reopen/rollback, executed Python and denial
scenarios, UI tests, strict types and the actual UI compiler. It writes a new
ZIP, report and log **outside** the application project. Use a fresh output name;
existing files are never overwritten. A failure or skipped required scenario is
not a pass. Inspect the reported stage instead of weakening a check.

The report's `scenario_checks` maps each missing-permission, revoked-access
and unavailable-provider scenario to a distinct declared test and its observed
result. A failed Python run can still show which scenarios passed, failed,
were skipped or were not observed. If an earlier build or migration step stops
the check after the project configuration is validated, the declared scenarios
say `not_run`; a Python check with no matching result says `not_observed`.
Neither is a permission denial. These are local project tests, not live
Core grants or proof of physical execution. The shareable scenario entries
do not include assertion output; the accompanying test log is local.
A final UI compiler failure can also carry a fixed `failure_code`: an unreadable
installed compiler file, an OS process error, a measured timeout, an unsuccessful
exit, or `compiler_output_invalid` when the compiler returned success but its
interface files could not be validated. For the last case, check the entrypoint
index and the files it references; exit code zero is not proof of a usable build.
The report omits compiler output. Inspect the local check log; neither exit
status alone establishes a defect in the application's source.

On a Core with package-build diagnostics, a compilation failure returns a short
explanation. If the installed compiler entry file cannot be read, Core returns
HTTP 503 and does not register the package or retain a new ZIP.
Compilation did not start; check the installation before editing or resending
the app. A fresh build with an invalid output index also returns 503, but
explicitly reports that compilation ran. Damage to an already cached build is
not evidence of a new compiler run. Diagnostics records the observed fresh
compiler outcome under `package.ui_compile`, with the original request ID. The
report does not contain the compiler's output. Check the exact ZIP in the local
authoring environment for more detail; no new grant or automatic upload is needed.

For an update, preserve the exact previous ZIP, use a newer independent
application version, adapt `tests/upgrade_fixture.py`, regenerate the client and:

```powershell
python -m tools.extension_dev check .runtime/my-note --previous-archive .runtime/my-note-1.zip --output .runtime/my-note-2.zip
python -m tools.extension_dev compare .runtime/my-note-1.zip .runtime/my-note-2.zip
```

No previous archive means upgrade verification was **not requested**, not passed.
Comparison is static review, not migration execution. The current common profile
does not build arbitrary native dependencies or verify scoped relational storage;
unsupported profiles need their relevant lifecycle checks, not a fake green result.
Local checks run trusted developer code and are not hostile-code isolation.

## Install and accept separately

Use **Extensions** in the admin panel, not SSH, direct database edits or copying
files into an immutable release. Upload the checked exact ZIP and review the
stopped candidate. Complete missing required device choices through the offered
configuration step, when present. Changing an optional device or query selection
on the same stopped package also prepares the exact configuration separately,
then opens a fresh access review; saving the selection does not start the app.
Review and approve the exact package's current access, then activate. Active apps
must be stopped before a changed selection is prepared. Dedicated relational and
session-provider profiles retain their own prepared lifecycles; this is not a
general configuration editor for every profile. Re-read a changed consent
preview; do not repeatedly click activation against a stale approval or repeat
preparation after an uncertain response. Local checks perform none of these
admin actions.

For Note, resource selection may be left empty. Open the route declared in the
candidate's `compiled-ui.json` (`/starter-note` only for the official example).
At the agreed test boundary verify:

- successful save, full reload and exact readback, including non-ASCII content;
- removal of edit permission blocks writes without destroying the draft or
  unrelated read access; current access is reloaded explicitly;
- missing, revoked or unavailable optional resources do not break owned data;
- lost replies and revision conflicts do not cause automatic repeated changes;
- applicable upgrade/restart, theme, locale and narrow-layout cases.

Record local versus live evidence separately. A preview or build pass does not
prove a physical effect. Deployment, granting rights, hardware writes, Git push
and release publication each need their own requested scope. Keep credentials,
tokens, personal data and private device details out of source and shared logs.

### Accept an update of the application itself

Keep the previous ZIP and its digest. Use the **same** candidate ZIP that
passed `check --previous-archive`: compare its report digest with the digest
in **Extensions → Inspect package**. A matching version label is not enough.

1. Save a known test record through the old version. Note the route, value and
   revision. If the candidate is rejected during compilation, check that the
   old route still reads that record after a full reload. Do not uninstall.
2. Upload the checked candidate. Upload alone should leave the old version
   running. Stop the app explicitly, prepare the new version, review that
   exact package's access, then activate it. The route need not be available
   while the app is stopped.
3. Reload the original route. Confirm the **new** interface is served and
   reads the **old** record. Edit it once, reload, and check the new revision.
4. If the old app supports the current data schema, test returning to the
   retained ZIP through the same stop, prepare, review and activate steps.
   Verify the old interface reads the **latest** edit. This changes the app
   version; it does not restore a database snapshot or reverse migrations.
   For incompatible schemas, use the application's migration/recovery plan.

### When the installed app refuses an operation

Keep the original identifiers and inspect before trying again. A signed-in
administrator can use **Extensions → Resource limits → Save app diagnostics**
with the original `cmd_…` or `task_…` for just that installation. A command
offered to a device, a claimed permit and an execution receipt are different
observations. A missing field is not a negative result.

For an HTTP failure, save **Settings → Diagnostics → Download report** before
clearing history. If you have the original `invoke_…` or `platform_…` ID,
run `python -m tools.diagnostics explain diagnostic-cases.json --trace-id ORIGINAL_ID --json`
in the platform checkout. This reads the saved file only. Report the failed
step, recorded cause and what remains unknown; don't infer a grant refusal
from a timeout or an unrecorded step. See [diagnostic evidence and limits](DIAGNOSTICS.md).

If an app disappears after an installer rollback, distinguish its **installed
package**, **saved data**, **account permissions** and **effective application
approval**. Restoring the Core database invalidates previously issued execution
approvals. An unchanged ZIP or a checked account permission is not proof that
the old approval still applies. Check the installation and its read-only
**Application access** status first. Do not automatically prepare a grant,
reinstall the package, change its version, or replay the last save. A normal
successful **Core** update is a separate test: an unchanged approved app should still read its
original data from the open tab, without asking for new access.

## Contract references

- [Note workflow and tooling limits](../modules/application-starter/README.md)
- [Manifest v2](MODULE_MANIFEST_V2.md) and [public schema and SDK contracts](EXTENSION_PLATFORM_V2_PUBLIC_CONTRACTS.md)
- [Public UI controls and host](EXTENSION_UI_V1.md) and [compiled UI](COMPILED_EXTENSION_V1.md)
- [Commands](APPLICATION_COMMANDS.md), [tasks](APPLICATION_TASKS.md) and [files](APPLICATION_FILES.md)
- [Package and data lifecycle](EXTENSION_LIFECYCLE.md)
- [Opt-in local host-account sessions](HOST_ACCOUNT_SESSIONS.md)

Read a specialized contract only when using that feature. Historical plans
describe prior stages and do not override current source, validators or project
instructions.
