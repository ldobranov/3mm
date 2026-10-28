# Dashboards source preservation

Product routes, display/widget models, the editor, palette, canvas, public display,
stores and their tests are preserved under `source/legacy/`. Shared Core access,
security and command-palette originals are retained under `source/reference/` to
make the former coupling reviewable. Original moved-file hashes and paths are in
`../product-source-map.json`. The layout dependency is recorded in
`source/frontend-dependencies.json`; Core no longer depends on gridstack.

These sources require a public-SDK/application-data port before they form a
runnable application package. They are not a second Core server or compatibility
route. The `.3mm-source-only` marker excludes this directory from Core releases.
Common compiled UI packages, rendering/loading contracts, application audiences,
roles/groups, language/theme administration and declarative CRUD stay available.
The current declarative consumers require their own later extraction scope.

Migration `7c52d3a4eb42` copies displays, widget configuration/layouts and role
grants to `retired_displays`, `retired_widgets`, `retired_role_dashboard_grants`.
Dashboard/widget rows from the direct, legacy role and group permission tables
move to their three `retired_dashboard_*permissions` tables. Other permission and
application grant rows are unchanged. Archives have no FK/cascade into active
Core users/roles, so later principal deletion cannot erase retained evidence.
No historic grant becomes current application authority.

Compiled widget references are converted into inert generic
`module_package_retained_references` pins for the exact existing package/version.
They protect package archives/builds even when the package is unsupported or
damaged. Administrators can inspect bounded reference metadata through
`GET /api/v1/modules/compiled-ui/packages/<module>/<version>/retained-references`.
These records grant no execution or code approval. This extraction provides no
unreviewed reference-release API: dependent recovery data must first be exported
and reviewed under an explicit future cleanup scope.

The original tables disappear from live Core ORM/API/frontend. An empty retirement
can be downgraded. Populated archives or retained package references refuse
automatic downgrade; use a verified prior backup/release for recovery. This
avoids restoring old rights against changed or reused user/role IDs. Existing
backup data and upload files are preserved. No application is automatically
installed, no owner device is reset, and no old widget/task/effect is executed.
