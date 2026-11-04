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

The command:

1. Freezes supported source files in a disposable local directory; refuses
   escaping paths/symlinks and checks for source changes before publishing output.
2. Builds a deterministic pure-Python service wheel and Manifest-v2 ZIP, then
   uses the actual current package/semantic validator. Service imports from
   private Core internals fail an authoring lint; this is not a security sandbox.
3. Imports the declared migration factory from the exact packaged wheel in a
   separate bounded local process. Uses disposable SQLite data to check clean
   creation to the declared target, database and foreign-key integrity,
   reopen/reapply without changed content, upgrade from each earlier revision,
   and rollback after an injected failure in each revision of the current plan.
4. Runs project Python tests and verifies that all three declared denial
   scenarios actually execute. A failure, skip or missing scenario is not green.
5. Runs the project's UI tests, strict Vue/TypeScript check and the actual
   installed-package UI compiler. It does not rebuild the main Core frontend.
6. Writes a new ZIP, `.report.json` and `.checks.log` outside the source project.
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
- `tests`: note persistence/isolation/conflicts, permission removal and provider
  loss, plus public-host UI behavior. `development.json` names these inputs.

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
