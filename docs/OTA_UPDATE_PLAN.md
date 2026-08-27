# 3mm OTA update and dependency plan

Status: Phases 1 and 2 are published in stable release `v0.1.0`. The Phase 3
boundary was introduced in `v0.2.0` and physically accepted on `rasp-3mm` on
2026-08-26: failed `v0.2.1` and `v0.2.2` attempts restored the healthy `v0.2.0`
release, corrected `v0.2.2` was installed as the trusted base, and `v0.2.3` was
then staged and activated successfully through the OTA path. Phase 4 channel
selection was physically accepted with a `v0.3.0-beta.3` bootstrap followed by
an in-application OTA update to `v0.3.0-beta.4`. Standalone background checks,
cache/backoff and maintenance-window enforcement were physically accepted on
2026-08-27, published in `v0.3.0-beta.5` and accepted through an
in-application OTA update from the official `v0.3.0-beta.4` release.

## Goal

Give a Standalone 3mm device the convenience of ShowController-style update
and dependency management without giving the web process unrestricted root
access or replacing the immutable release, health-check and rollback layout.

The existing deployment layout remains authoritative:

```text
/opt/3mm/current -> /opt/3mm/releases/<release-id>
```

An update is a reviewed 3mm release. It is never an arbitrary branch head and
never a collection of commands returned by an AI provider.

## Phase 1 — Read-only release catalog

Implemented:

- administrator-only `GET /api/v1/system-updates/status` reads local release metadata;
- administrator-only `POST /api/v1/system-updates/check` checks the public GitHub Release catalog;
- opening the UI never contacts GitHub automatically;
- a strict `3mm-update-manifest.json` is required before an update is trusted;
- the release tag, manifest, asset names, sizes, URLs and available GitHub digest are cross-checked;
- architecture compatibility and declared APT packages are displayed;
- a release with the same or an older semantic version is never offered for
  staging, even when its commit differs from the installed snapshot;
- no archive is downloaded and no package, service or filesystem state is changed;
- System Updates is an admin route available to the data-driven Menu Editor.

The first published catalog entry is stable release `v0.1.0` with validated
artifacts for `aarch64`, `armv7l` and `x86_64`.

## Manifest v1

Each release must contain an asset named `3mm-update-manifest.json`:

```json
{
  "schema_version": 1,
  "version": "1.2.0",
  "release_id": "v1.2.0",
  "commit": "0123456789abcdef0123456789abcdef01234567",
  "channel": "stable",
  "artifacts": [
    {
      "architecture": "aarch64",
      "filename": "3mm-1.2.0-aarch64.tar.gz",
      "download_url": "https://github.com/ldobranov/3mm/releases/download/v1.2.0/3mm-1.2.0-aarch64.tar.gz",
      "sha256": "<64 lowercase hexadecimal characters>",
      "size_bytes": 123456
    }
  ],
  "dependencies": {
    "apt_packages": ["rsync"]
  }
}
```

Unknown fields, duplicate architectures, duplicate files, unsafe package names,
external download URLs and inconsistent release metadata are rejected.

## Phase 2 — Reproducible release artifacts

Implemented and published in `v0.1.0`:

- tag-driven GitHub workflow restricted to commits contained in `main`;
- locked frontend installation plus the complete frontend/backend quality gates;
- exact tagged source export through `git archive`;
- deterministic archives for `aarch64`, `armv7l` and `x86_64`;
- normalized file order, timestamps, owners and permissions;
- architecture-specific release metadata containing release ID, version and commit;
- generated strict manifest with artifact size and SHA-256;
- reviewed, sorted dependency declaration;
- two independent builds with a byte-for-byte comparison before publication;
- draft-first upload so an incomplete release never becomes the latest release.

See [RELEASING.md](RELEASING.md) for the maintainer procedure.

The published release catalog, architecture selection and reproducible artifact
checks are now exercised by the accepted Phase 3 path on `rasp-3mm`.

## Phase 3 — Staged update and dependencies

Implemented in `v0.2.0`:

- one architecture-specific artifact is downloaded into a bounded fixed staging
  location; no URL or filename is accepted from the browser;
- size, SHA-256, redirect host, safe tar layout, expanded size, required files,
  embedded release identity and embedded dependency declaration are verified;
- storage, architecture, SQLite quick-check, backup capacity and migration
  entrypoint preflights are presented to the administrator;
- declared APT packages must be contained in the reviewed installed allowlist;
- the UI shows keep/install actions and requires a separate restart
  acknowledgement plus an exact version-bound API approval;
- Core can send only release ID, short-lived approval nonce and administrator ID
  to a root-owned local Unix socket;
- the root worker revalidates the archive against the official stable GitHub
  manifest immediately before any package or installer mutation;
- only missing allowlisted packages are passed as individual `apt-get`
  arguments; shell fragments and generated install scripts are impossible;
- the existing immutable installer owns database backup, migration, atomic
  activation, Core/Web/Agent health gates and rollback;
- Core audit entries identify the staging and approving administrator, while a
  root-owned operation/audit record survives service restarts without secrets.

Physical acceptance completed on `rasp-3mm` on 2026-08-26:

- `v0.2.3` was selected as the exact `aarch64` artifact over the manually
  installed `v0.2.2` base;
- archive identity, SHA-256, dependencies, disk capacity, SQLite quick-check,
  backup capacity and migration entrypoint all passed before approval;
- exact confirmation `INSTALL 0.2.3` queued the root-owned worker and the UI/API
  recovered after the Core and Web restart;
- two earlier real installer failures restored the previous release, database
  and healthy services, and persisted a terminal failure operation record;
- the successful run activated `/opt/3mm/releases/v0.2.3`, preserved device
  identity and left Core, Web, Agent and the update helper healthy.

The web backend must not execute arbitrary package names, shell fragments or
generated install scripts.

## Phase 4 — Operational controls

Stage 1 implemented and physically accepted on 2026-08-26:

- an administrator explicitly selects `stable`, `beta` or `test` before a
  catalog check;
- stable checks continue to use GitHub's latest stable release, while preview
  checks inspect published prereleases for the selected channel;
- the tag convention maps normal semantic versions to `stable`, prereleases to
  `beta`, and `-test...` prereleases to `test`;
- the selected channel is bound into the staged plan and independently checked
  again by the root worker before any mutation;
- changing channels discards the previous catalog result and staged UI plan,
  and preview channels carry a visible warning;
- requests without a channel remain backward compatible and use `stable`.

Physical acceptance completed on `rasp-3mm`:

- published `v0.3.0-beta.3` was installed as the channel-aware bootstrap;
- the Beta catalog then selected only published Beta release
  `v0.3.0-beta.4` and validated its manifest;
- staging passed archive, storage, database, migration and dependency
  preflights before the exact `INSTALL 0.3.0-beta.4` approval;
- the root-owned update worker activated `v0.3.0-beta.4`, retained
  `v0.3.0-beta.3` as rollback and preserved the device identity;
- Core, Web, Agent and update-helper passed health checks, and a final Beta
  catalog check returned `up_to_date`.

Stage 2 implemented and physically accepted on 2026-08-27:

- an administrator can opt into read-only background catalog checks, choose
  the channel and select a bounded interval from one hour to seven days;
- the selected policy and last trusted catalog result persist outside the
  immutable release tree;
- successful checks schedule the next interval, while failures retain the last
  trusted result and use persistent exponential backoff capped at 24 hours;
- a daily IANA-timezone maintenance window is calculated server-side and shown
  in the UI with its current or next occurrence;
- applying a staged release outside that window is rejected unless the
  administrator supplies a separate explicit override, which is recorded in
  the audit log;
- automatic work is deliberately limited to catalog reads: download, staging,
  dependency changes and installation remain separate manual operations.

Physical acceptance completed on `rasp-3mm`:

- the policy persisted Beta checks every six hours and a Europe/Sofia daily
  window from 03:00 to 05:00;
- the running background worker independently cached a Stable `not_newer`
  result and then a Beta `up_to_date` result with zero failures;
- an apply request outside the window was rejected before staging or the root
  helper could be reached;
- official `v0.3.0-beta.5` was installed through the in-application Beta OTA
  path from official `v0.3.0-beta.4` and the root operation reached
  `succeeded`;
- `/opt/3mm/current` resolved to `v0.3.0-beta.5`, `/opt/3mm/previous` retained
  the official `v0.3.0-beta.4` base and the persistent device identity was
  unchanged;
- Core, Web, Agent and update-helper passed health checks, and a fresh Beta
  catalog check returned `up_to_date` with zero retry failures.

Still pending:

- fleet rings for Hub/Node installations;
- power-loss acceptance and recovery;
- optional automatic installation only after the manual path is accepted on
  clean Raspberry Pi media.

## Deliberately excluded through Phase 4

- unattended download or installation;
- arbitrary packages, commands, URLs or branch archives;
- Web process access to `sudo`, `apt`, `systemctl` or writable system paths;
- changing NetworkManager;
- accepting prereleases or unvalidated branch snapshots.
