# 3mm / CONERAX working instructions

## Start and scope

- Read `docs/WORKING_STATE.md`, then only the files needed for the active task.
- Use `docs/DEVELOPMENT_CHECKS.md` when choosing checks or preparing a commit.
- Deliver one meaningful, bounded result. Finish at the agreed acceptance point.
- Implement general Core mechanisms; extensions must not require a special Core
  change for every task. Never hardcode concrete module/extension names in Core.
- Record unrelated findings briefly; expand scope only for a demonstrated blocker
  or the user's instruction. Do not reopen accepted work from historical reports.
- Keep independently developed work within its agreed integration scope.
- This is an unreleased prototype with no production users/installations. Target
  manifest v2; old manifest/SDK/API compatibility and installed prototype extensions
  are not preservation requirements. Remove obsolete paths in scoped, complete
  changes instead of adding compatibility adapters solely for historical versions.
- Preserve user source changes, including independent M21 work. Prototype status
  does not itself request a device wipe, reset or deployment.
- Local device/access notes live in Git metadata; locate them with
  `git rev-parse --git-path 3mm-development-access.md`. Keep credentials out of
  tracked files and reports.

## Architecture and recoverability

- Coordinated API/SDK breaks are authorized for scoped prototype simplification;
  update current consumers/contracts together. Version axes remain independent.
- Keep navigation, routing and extension registration data-driven; preserve auth,
  role filtering, i18n, themes and Command Palette behavior.
- Database changes require an explicit migration or scoped clean-reset plan and
  relevant checks; do not perform an unrequested reset.
- Auth changes require explicit task scope and affected security checks, including
  denial, revocation and isolation behavior.
- Preserve immutable releases, prebuilt frontend delivery, health checks and
  rollback: `/opt/3mm/current -> /opt/3mm/releases/<release-id>`.
- Read relevant files and necessary direct dependencies before editing. Check
  imports, registrations and consumers before removing apparently unused paths.
- Prefer fewer rules and dependencies. Splitting files alone is not simplification.
- For stabilization/setup/debug work follow `docs/CORE_STABILIZATION_ACTION_PLAN.md`;
  consult `docs/CORE_RESILIENCE_DIRECTION.md` for architecture detail on demand.
  Core must remain administrable when optional runtimes/diagnostics fail. Planned
  packages are not an instruction to implement everything at once.
- For setup changes keep device role, network choice and recovery state separate.
  Wi-Fi/AP is optional; preserve existing host-managed networking. Link loss must
  not reset the role or automatically stop otherwise healthy local workloads.

## Checks and commits

- Choose checks from the changed behavior and its consumers. Use targeted local
  checks while implementing; broad checks belong at integration/release gates.
- Documentation-only edits do not require runtime tests or a frontend build.
- Reuse successful checks when the relevant content, dependencies and environment
  are unchanged. State what was reused; a new commit hash alone does not invalidate
  evidence. Never claim an old run tested later code changes.
- Broaden checks for shared contracts, auth, migrations, runtime or deployment.
  Uncertain dependencies require a broader group, not an assumed safe omission.
- Do not create tests for trivial reversible edits or tests that only mirror code.
- Do not disable hooks, use `--no-verify`, or ignore required checks to save time.
- Do not create branches or rewrite history. Preserve existing user changes.
- Commit only when explicitly requested. Review the exact staged diff and required
  evidence, then commit. Push, version changes, tags and releases each require user
  scope; do not infer them from "commit".

## Context and reporting

- Keep current scope, accepted decisions, next action and concise verification
  evidence in `docs/WORKING_STATE.md`. Update it at meaningful handoffs.
- Historical plans/reports are references, not mandatory reading or a task queue.
- Do not create another report for every step or repeat logs already examined.
- Report the result, checks (new or reused), and material remaining limitation.
- Do not promise a credit percentage or infer usage from test count. Reduce
  repeated investigation, output and checks; no delegation unless requested.

## Frontend tasks

- Keep the existing Vue 3 / TypeScript / Vite / Pinia / Vue Router stack. Do not
  introduce a framework/component library without explicit user approval.
- For visual redesign, read `docs/FRONTEND_REDESIGN.md` on demand. Preserve behavior
  and inspect affected layouts/themes in addition to relevant checks. Do not run a
  frontend build for unrelated backend/documentation work.
