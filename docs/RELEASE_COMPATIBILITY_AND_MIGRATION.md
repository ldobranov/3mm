# Release compatibility and supported migration windows

Status: Milestone 15 documentation, grounded in the current release behavior. It
summarizes existing facts and the support boundary; it does not change the
runtime, publish a release or widen any supported path.

## 1. Version and channel axes

- Core runtime version is read from `VERSION`; the current checkout is
  `0.3.0-beta.47`.
- Release tags map to channels by convention:
  - normal semantic version → `stable`;
  - prerelease (`-beta*`) → `beta`;
  - `-test*` prerelease → `test`.
- SDK 1.3 and earlier supported SDK versions are independent of the Core release
  version. A Core update does not bump the application SDK.
- Device protocol, descriptor and UI-host versions are also independent axes;
  they are not renumbered by a Core release.

## 2. Compatibility matrix (what is preserved on update)

| Artefact | Preserved across update | Replaced by the new release |
| --- | --- | --- |
| Device identity and credentials | Yes (persistent state) | No |
| Agent identity / provisioning | Yes | No |
| Core database and migrations | Migrated by the target installer | Schema may gain additive columns/tables |
| Users, roles, permissions, sessions | Yes | No |
| Uploaded public assets | Yes (`/var/lib/3mm/core/uploads`) | No |
| Installed extensions (backend/frontend/compiled) | Yes (persistent extension store) | No |
| Application extension data | Yes (`/var/lib/3mm/application-extensions`) | No |
| Themes, language packs, settings | Yes | No |
| Frontend build, services, installer | No (immutable release) | Yes |

Compatibility meaning: a supported update must keep the existing IDs, data,
configuration, grants and device bindings. It never re-pairs devices or silently
adopts applications into a different authority mode.

## 3. Supported migration windows

### Core/database migrations

- The immutable installer owns database backup, migration, atomic activation,
  health gates and rollback.
- A migration runs as part of a reviewed release install; it is not an ad-hoc
  backend step.
- Rollback on failure restores the previous `/opt/3mm/previous` release together
  with a verified backup; it never blindly replays an uncertain migration.

### Published dependencies

- Declared APT dependencies are contained in the reviewed installed allowlist.
- Only missing allowlisted packages are installed as individual controlled
  arguments; arbitrary packages, shell fragments and generated scripts are not
  accepted.

### Update windows (Standalone)

- A server-side IANA-timezone maintenance window gates `apply`.
- Applying outside the window requires a separately audited manual override.
- Automatic work is limited to catalog reads; download/staging/install stay manual.

### Cross-host restore

- Restore validates application, protocol, database and architecture
  compatibility before mutation (Milestone 11).
- Core can be restored onto a different supported host when the protected
  credential material is included; device credentials are remapped, not granted
  arbitrary privilege.

## 4. What is not supported / not claimed

- A release with the same or an older semantic version is never offered for
  staging, regardless of commit.
- Published prereleases are accepted only through their matching Beta/Test
  channel. Unpublished or unvalidated branch snapshots are not accepted through
  the normal catalog path.
- Fleet rollout rings and Hub/Node maintenance-window coordination remain
  pending until Hub/Node orchestration provides them.
- No bridge release or tag rewriting is planned; an older installed updater
  cannot gain a fix until it first executes a manual update.

## 5. Remaining Milestone 15 work items

- Signed releases and trusted private module repositories: the Ed25519 helper is
  tested, but publisher/catalog/installer integration and trusted-key policy are
  not delivered by this slice. Existing checksums are not signing evidence.
- Read-only alerts and redacted diagnostics exist; notification policy and live
  monitoring acceptance remain. Retention is manual, confirmed and bounded;
  no automatic purge is scheduled by an update.
- Backup-key rotation is guarded by the shared mutation lock and refuses to
  orphan archives without explicit acknowledgement. Complete secret lifecycle
  and credential recovery acceptance remain; the helper does not re-encrypt old
  archives or rotate anything during installation.
- Cross-host restore and coordinated fleet rollout acceptance remain open.
- Live Internet-exposed ingress acceptance (see the security guide).
