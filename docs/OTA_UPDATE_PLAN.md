# 3mm OTA update and dependency plan

Status: Phases 1 and 2 are published in stable release `v0.1.0`. Phase 3 is
included in release candidate `v0.2.0` and awaits physical Raspberry acceptance
before it is considered complete.

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

Still pending: exercise a newer published archive through the Phase 3 manual
path and existing installer health gates on `rasp-3mm`.

Acceptance boundary: a freshly published release appears as available on a
supported device, but the application still cannot install it.

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

Physical acceptance still required:

- deploy the Phase 3 boundary itself through the existing reviewed manual path;
- publish a version newer than the installed Raspberry release;
- stage it from the UI and inspect the real dependency/disk/database plan;
- approve it and observe the UI recover after Core/Web restart;
- inject one installer failure and confirm the previous release, database and
  services are restored while the failure remains visible in operation status.

The web backend must not execute arbitrary package names, shell fragments or
generated install scripts.

## Phase 4 — Operational controls

- update channels and maintenance windows;
- automatic checks with cached results and backoff;
- manual download/apply separation;
- fleet rings for Hub/Node installations;
- power-loss acceptance and recovery;
- optional automatic installation only after the manual path is accepted on
  clean Raspberry Pi media.

## Deliberately excluded through Phase 3

- automatic updates;
- background or scheduled download/install;
- arbitrary packages, commands, URLs or branch archives;
- Web process access to `sudo`, `apt`, `systemctl` or writable system paths;
- changing NetworkManager;
- accepting prereleases or unvalidated branch snapshots.
