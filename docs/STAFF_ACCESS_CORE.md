# Generic staff access — Core integration

## P0: own access snapshot

`GET /api/v1/application-extensions/{module_id}/access` requires a normal
authenticated user and returns `Cache-Control: no-store`:

```json
{
  "module_id": "org.example.application",
  "active_version": "1.0.0",
  "user_id": 42,
  "allowed_route_ids": ["desk"],
  "allowed_operation_ids": ["list_records"]
}
```

The server selects the user from the token. No parameter selects another user.
Permissions are resolved for the active installation on each request. The
snapshot uses the route policy and the operator gateway's operation policy.
Human users may access public operations, permitted operator operations, and
(only global administrators) administrator operations. Kiosk/internal-only
operations are excluded, including for administrators.

An empty successful list means no access. Missing installations return 404;
disabled, inconsistent or unreadable active packages return 409. Anonymous,
kiosk and device credentials cannot retrieve this snapshot. Current login
tokens carry `sid`; revoked, missing, expired or foreign sessions return 401
in snapshot, gateway and the shared authenticated dependency. Legacy signed
user tokens without `sid` remain accepted for compatibility until JWT expiry.
Blocked accounts are rejected. Legacy tokens default to token generation zero;
account blocking or termination of all sessions increments the stored generation
and invalidates them permanently, even after unblocking or a new login.

Client integration must refresh on login, user change, window focus and
401/403. Clear old permissions while refreshing or on failure. Do not cache
across users or installations. A snapshot is UI guidance, never authorization
for a later mutation: every gateway request checks current access again.
No extension-specific names or staff roles are built into Core.

## Users: direct application grants

Each user card now opens Application access. The panel lists only active
applications and reads localized permission labels from their declarations.
Grant/revoke uses the existing administrator-only endpoints and reloads server
state after each write. Failed writes require a refresh; they are not displayed
as successful. Global admin access is explicitly separate from direct grants.
No role/group aggregation or extension-specific policy is introduced.

## Next Users stages

1. Review the new Users application permissions panel on the device.
2. Design role/group aggregation and grant removal semantics before adding
   role/group grants. Existing direct grants must retain their meaning.
3. Validate account blocking on the device; plan retirement of legacy
   sessionless tokens independently.
4. Consider delegated application configuration separately from install,
   secrets and permission administration.

The extension consumes this generic contract in its own task. Its business
roles, route prerequisites and payment permission splits remain extension work.

## Account status and sessions

Administrator-only `PUT /api/user/{user_id}/status` accepts `is_blocked`.
Blocking revokes all sessions atomically; unblocking allows a fresh login only.
`POST /api/user/{user_id}/revoke-sessions` ends sessions without blocking login.
Both actions are audited. Self-blocking and removal of the last unblocked
administrator are prohibited. Existing accounts migrate as unblocked.

The Core-wide HTTP dependency checks signed human bearer credentials before
legacy and dynamic routes run; application/device credentials retain their own
policies. Revocation is enforced at the next request, not by pushing a logout
notification to idle browsers. Anonymous public access remains public.
