# Development checks and commit policy

Choose checks from changed behavior and its consumers. Repeating a passed check
without changed inputs is not additional progress. A commit is not a release.

## Local work

| Change | Local checks |
| --- | --- |
| Documentation | Diff, whitespace and affected links; no runtime suite/build |
| Bounded Python fix | Changed behavior and direct consumers/regressions |
| Frontend logic/layout | Relevant tests, applicable type-check/build, visual review |
| Auth, SDK/API, runtime | Affected integration, compatibility, denial/revocation |
| Schema or installer | Relevant migration/upgrade/rollback checks |
| Broad integration/release | Full applicable suites; retain release gates |

Frontend dependency edits must keep both `package-lock.json` and
`pnpm-lock.yaml` consistent with `package.json`. The deployment preparation's npm
cache does not prove the pnpm installation used by CI. Validate in a clean
frontend directory with Node 22 and pnpm 10.13.1 using the CI commands:

```bash
pnpm install --frozen-lockfile
pnpm run test:unit -- --run
pnpm run type-check
pnpm run build-only
```

From the root, using the project's Python environment:

```powershell
python -m pytest -q backend/tests/test_application_checkpoints.py
python tools/checks.py
python tools/checks.py --paths README.md docs/WORKING_STATE.md
python tools/checks.py --base origin/main
python tools/checks.py --run
python tools/checks.py --full --run
```

The first command is an example, not a universal gate. The planner prints commands
by default; execution requires `--run` and stops at the first failure. It does not
install dependencies, stage, commit or publish. `--paths` is a planning preview.
Without a base it includes staged, unstaged and untracked paths. With `--base`,
it compares that commit with `--head` (HEAD by default), excluding dirty files.
Choose the comparison intentionally; do not include unrelated user work.

## Automatic CI selection: conservative first version

- Documentation-only changes skip runtime suites; frontend-only changes run
  frontend checks. Mixed changes retain every applicable group.
- Test-only Python edits select their containing suite. Fixtures, migrations,
  configuration and production Python retain **all existing Python suites**.
  Narrower production groups need an actual consumer/dependency audit.
- Unknown inputs, locks, workflow/selection-tool changes, and unavailable bases
  select every group. Renames select both old and new paths.
- Push/PR comparisons require a successful CI run for the exact base commit.
  Failed, cancelled, pending or unknown bases and Actions API errors select full
  checks. The verified comparison base is carried into Python execution, so the
  runner cannot silently narrow a full plan against the original failed base.
- Plan failure fails the existing Python/frontend check jobs; it cannot yield
  successful skipped gates. Manual CI runs select all groups.
- Tags use Release's full gates rather than duplicating ordinary CI. Release
  adds tooling self-checks; no existing release gate is removed.

This schedules components; it is not a complete dependency graph. Use full checks
when a change crosses these groups or its dependencies are uncertain.

The Python integration group includes optional `libraries/three_mm_ai/tests` and
`libraries/three_mm_crud/tests`; their source-path setup is test-only and does not
install either library into Core. CRUD renderer tests use the existing frontend
toolchain with `vitest run --config libraries/three_mm_crud/tests/vitest.config.mjs`.
Empty `.3mm-source-only` markers in individual `modules/<name>` or
`libraries/<name>` directories exclude preserved product/optional source from
release payloads. Runtime dependencies cannot use a marker to evade required-file
validation. `retired_` table names are reserved for explicit recovery migrations,
outside live Core ORM ownership; never use autogenerate to erase that evidence.

## Requested commits and reuse

1. Review the exact intended/staged diff; preserve unrelated/generated files.
2. Reuse identifiable passed checks for unchanged content, dependencies and
   environment. Run only missing checks or those invalidated by a later edit.
3. Keep environment limits explicit. A Windows skip is not a Linux/POSIX pass.
4. Commit the agreed scope. Push, version bumps, tags and releases are separate.

Never bypass hooks/required checks or call a targeted run full coverage.
After failures, repair within scope and rerun affected checks. Record unrelated
defects for later unless they demonstrably block the result.

The local `deploy.ps1` preparation caches exact source/dependency/environment
evidence and frontend builds. An explicit reviewed `-TestPaths` selection is
recorded as targeted; another explicit selection gets separate evidence. The
last successful selection can be reused for unchanged inputs during local
deployment. Without previous evidence, all Python groups run in their existing
separate processes, plus tooling and frontend checks. This does not replace
published release gates. Controller checks: `python -m pytest -q
tools/tests/test_deploy.py`; Windows wrapper command doubles:
`pwsh -NoProfile -File tools/tests/test_deploy_powershell.ps1` (no network).
Explicit Agent rollout (`-WithAgent` at preparation) additionally uses the normal
service-component artifact/update/probe path; include affected Agent checks and
`deployment/tests/test_service_component.py` when validating its delivery.

## Small handoff

For CAP11's optional image profile, install
`deployment/application-media-requirements.txt` in a disposable Linux test
environment and run the media SDK/HTTP/worker/snapshot checks. A missing-provider
skip is not image-provider conformance. Test its native host artifact with
`--image-provider` in a clean interpreter; Pillow is not a Core dependency.
The SQL recovery/upgrade tests that validate file preimages also cover media
manifests. Their isolated root driver needs a public-code source directory
traversable by its disposable non-root migration UID; a 0700 frozen source
directory causes environment-only worker-import failures. Do not weaken
production namespace/key permissions to repair that test environment.

Update the existing WORKING_STATE.md at meaningful handoffs, not every command:
`checked content/base | command/scope | environment | result | limits`.

A commit hash alone is insufficient for dirty work. Identify the checked content
and subsequent relevant edits. Do not relabel historical totals as new runs.
Keep long logs out of the handoff; consult history only for a specific question.
