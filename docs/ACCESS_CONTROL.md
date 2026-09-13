# Users, groups and application access

## Operator guide

In **Users → Roles and groups**:

1. Create a named role and optionally a group.
2. Select the role and grant permissions for an installed application or dashboard.
3. Assign the role directly to a user, or to a group containing that user.
4. In the user's **Application access** panel, direct checkboxes remain editable;
   the source text shows inherited access as well. Removing a direct grant does
   not remove an independently inherited grant. Refresh if another admin edits
   membership concurrently.

Permissions are resolved from the database on every protected request, not
embedded in JWTs. Revocation applies to the next request, without another login.
An already rendered page can remain visible until refresh; its operations are
still checked by the backend. Blocking an account overrides human grants.

The global `User.role = admin` flag remains separate. A custom role named
`admin` never becomes a system administrator. Only a system administrator may
create roles/groups, change membership or grant permissions. No explicit deny
exists: effective access is the union of current grants.

Supported role resources in this revision are application permission IDs,
scoped to an installation, and dashboard widget access. Dashboard levels are
`view < edit < delete < admin`; `none` removes the grant. Ownership, dashboard
sharing/deletion and bulk-layout remain owner-only. Core system management and
device administration are not exposed as custom-role grants in this revision.
Legacy single-row `role_permissions` / `group_permissions` are not silently
activated or migrated; assign explicit reviewed grants in the new panel.

## Extension handoff: delegated management

Core has no hardcoded knowledge of extension names or business roles.
`administrator` continues to mean the **system** administrator. Do not change
that audience globally to make a single extension's management page accessible.

An extension that wants delegation must explicitly declare:

```json
{
  "route_id": "management",
  "entrypoint_id": "management",
  "audience": "operator",
  "required_permissions": ["configuration_manage"]
}
```

Its management operations must likewise include `operator` in `audiences` and
declare `required_permission: configuration_manage` (or a narrower declared
permission for each operation). Keep internal operations internal. Keep purely
system-admin actions on their existing administrator-only gateway. Merely
changing the page declaration does not authorize its operations.

The compiled entrypoint must not retain `requires_role: admin`. Navigation must
use Core's authorized catalog and the own-access snapshot:
`GET /api/v1/application-extensions/{module_id}/access`.
Check `allowed_route_ids` / `allowed_operation_ids`, not global role names.
Delegated calls use:
`POST /api/v1/application-extensions/{module_id}/operator/operations/{operation_id}`.
The signed context supplies the actual user and effective permission IDs.

Existing extension packages are deliberately not rewritten. Updating the
extension manifest, its UI gates and calls is a separate extension release.
Granting rights alone cannot unlock its old administrator-only pages.

## Storage and verification

Migration `0d15c6d7e8f9` adds `group_roles`, `role_application_grants` and
`role_dashboard_grants`. Existing users/direct grants are preserved. Grants are
removed on resource uninstall/deletion; reused SQLite identifiers do not inherit
old rights. Role deletion is refused while assigned to users or groups.

Targeted tests cover two users in different groups, same-token grant/revoke,
blocked accounts, expired/NONE dashboard grants, direct-role inheritance,
undeclared-permission rejection, uninstall cleanup and explicit delegated versus
system-administrator boundaries. Migration checks cover fresh installation,
upgrade from the previous schema and downgrade. Physical Raspberry acceptance
of this revision remains a separate test; no factory reset is required.
