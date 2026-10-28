# Builder source preservation

The former Core Builder routes, project models, schemas, generator, editor and
tests are preserved under `source/legacy/`, using their original paths. Shared AI
clients have one owner at `libraries/three_mm_ai`; see `../product-source-map.json`
for original paths and SHA256 hashes. `source/reference/` preserves the old mixed
settings component, and `source/legacy/backend/routes/ai_settings.py` its former
provider settings API fragment.

This is preserved product source for a future standalone application. It is not
an installable package or an alternative Core server. The legacy sources/tests
still refer to former Core internals; they must be ported to the public SDK and
application-owned data before they can run independently. No compatibility
imports or old HTTP routes are installed. The `.3mm-source-only` marker excludes
this directory from Core release artifacts. Normal package inspection, compiled
UI validation/installation and application lifecycle remain in Core.

Migration `6b41c293da31` preserves project/file/build tables as
`retired_extension_projects`, `retired_extension_project_files` and
`retired_extension_project_builds`. All row values, IDs, ownership, build metadata
and original artifact paths remain. The normal backup includes the database and
existing uploads. No upload or build artifact is removed by this change.
Provider settings and their translations are preserved byte-for-byte as values
in `retired_ai_settings` and `retired_ai_setting_translations`; encrypted values
require the existing installation key for future recovery. They are not exposed
as active Core settings. Core still needs that existing encryption key for its
identity and application secrets, so its deployment/key recovery is unchanged.

Retirement never grants an application access to these tables. Future migration
must explicitly export data into the application's own namespace with an owner
mapping and reviewed secret transfer. Database downgrade restores the previous
names/settings only if no current setting/ID would be overwritten; otherwise it
refuses and requires a verified backup. Normal immutable release rollback and
backup/recovery remain the operational path. Dashboards are a separate next step.
