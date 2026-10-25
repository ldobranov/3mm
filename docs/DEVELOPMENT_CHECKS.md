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
- Plan failure fails the existing Python/frontend check jobs; it cannot yield
  successful skipped gates. Manual CI runs select all groups.
- Tags use Release's full gates rather than duplicating ordinary CI. Release
  adds tooling self-checks; no existing release gate is removed.

This schedules components; it is not a complete dependency graph. Use full checks
when a change crosses these groups or its dependencies are uncertain.

## Requested commits and reuse

1. Review the exact intended/staged diff; preserve unrelated/generated files.
2. Reuse identifiable passed checks for unchanged content, dependencies and
   environment. Run only missing checks or those invalidated by a later edit.
3. Keep environment limits explicit. A Windows skip is not a Linux/POSIX pass.
4. Commit the agreed scope. Push, version bumps, tags and releases are separate.

Never bypass hooks/required checks or call a targeted run full coverage.
After failures, repair within scope and rerun affected checks. Record unrelated
defects for later unless they demonstrably block the result.

## Small handoff

Update the existing WORKING_STATE.md at meaningful handoffs, not every command:
`checked content/base | command/scope | environment | result | limits`.

A commit hash alone is insufficient for dirty work. Identify the checked content
and subsequent relevant edits. Do not relabel historical totals as new runs.
Keep long logs out of the handoff; consult history only for a specific question.
