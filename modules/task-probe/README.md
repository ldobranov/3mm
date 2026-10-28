# Result task probe

Neutral consumer for scoped one-shot, interval and calendar tasks. It calculates
`1 + ... + upper`; `pause_ms` permits controlled failure/deadline acceptance.
Its local attempt journal records handler entries. The arithmetic variant has no
device/network resource scopes; the separately built command variant consumes
one explicitly selected output. Both services import only the public SDK.

Build from the repository root:

```text
python modules/task-probe/build_package.py --output modules/task-probe/dist/task-probe-0.2.0.zip
python modules/task-probe/build_package.py --with-command --output modules/task-probe/dist/task-command-probe-0.2.0.zip
python -m pytest -q backend/tests/test_application_tasks.py backend/tests/test_application_task_schema.py
```

Use the matching local Core/SDK, Platform Runtime and native application-host
artifacts. Approve only `task:calculate` through the existing Application access
flow. The separate worker runs explicitly through the Runtime artifact's
`--task-worker --authority-socket ... --core-uid ...` entry point as an unprivileged
principal. The authorized 2026-10-26 owner rollout installed the matching components,
approved this package and explicitly enabled the optional task-worker service.

## Owner VM test

In PowerShell, from the repository root:

```powershell
.\modules\task-probe\Test-VM.ps1
```

Version0.2.0 adds interval/calendar admission using `bounded_task_v1`. The
separate command variant declares only `task:switch_output` and `command:output`
for an explicitly selected device; it observes the original Agent result and
never resubmits after losing a reply. Both variants keep their own attempt journal.

The default test waits five seconds, calculates `1 + ... + 100` and prints
`queued`, `running`, then `succeeded` with `PASS: total = 5050`. Repeating the
command starts a fresh test after the previous request has a confirmed terminal
state. The installed client runs as the application UID using its pinned native
host's independent SDK; the launcher exposes no token or transport key.

```powershell
.\modules\task-probe\Test-VM.ps1 --lookup
.\modules\task-probe\Test-VM.ps1 --upper 1000 --delay 10
.\modules\task-probe\Test-VM.ps1 --interval 5 --runs 3
.\modules\task-probe\Test-VM.ps1 --calendar --timezone Europe/Sofia
```

`--lookup` reads the last persisted request, without scheduling another task.
For cancellation, start a delayed test and wait for `Admitted: queued`, then run
`Test-VM.ps1 --cancel` in another terminal before the due time. A running task is
returned unchanged. Ctrl+C leaves the request saved; use lookup to inspect it.
The client refuses to overwrite a pending or unknown request. Lost submit replies
also require lookup; do not replace their request IDs.

The interval exercise confirms three separate5050 results, then exhausts its finite
schedule. The calendar exercise admits one next-minute occurrence in the selected
timezone. `--lookup`/`--cancel` also work with the saved schedule. Ctrl+C preserves
the active schedule; inspect or cancel it before starting another exercise.

The public client is `examples/task_probe.TaskProbe`. Preserve its original request
ID before schedule; a lost reply requires lookup, not another schedule call.
The sample arithmetic result for upper100 is5050. There is no scheduler UI in this
terminal acceptance. Recurrence, DST, retention and command-effect rules are in the
shared contract; application business workflows remain outside Core.

See [Application tasks](../../docs/APPLICATION_TASKS.md) for authority, deadlines,
failure states, migration, explicit reconciliation and current profile limits.
