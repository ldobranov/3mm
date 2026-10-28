# Automations source preservation

The former Core proposal/planning, budget/usage, revision, simulation, deployment
and editor sources/tests are preserved under `source/legacy/`, using original
paths. Shared provider clients live only in `libraries/three_mm_ai`. Original file
paths and hashes are recorded in `../product-source-map.json`.

These are product sources for a future SDK application, not a runnable package,
replacement server or compatibility path. Legacy direct Core SQL/device queue
imports must be replaced by application-owned storage, the public resource SDK
and separate current human/service authority before activation. The source-only
directory is excluded from Core release artifacts. The existing Agent automation
protocol/runtime and current device commands remain unchanged; retirement does
not send disable, rollback, start or replacement commands to a device.

Migration `6b41c293da31` preserves all six historical tables under `retired_` names:
`automation_proposals`, `automation_revisions`, `automation_audit_events`,
`ai_credit_accounts`, `ai_jobs`, `ai_usage_ledger`. Their IDs, owner references,
JSON, status, command IDs, balances and usage values remain unchanged. They are
recovery evidence, with no Core ORM registration or execution path. Existing
backups retain them. Refer to `../builder/README.md` for preserved provider
settings, encryption key requirements and guarded downgrade/recovery.

CAP08 remains the generic bounded task/time mechanism. This extraction does not
automatically convert historical revisions to tasks or replay uncertain effects.
