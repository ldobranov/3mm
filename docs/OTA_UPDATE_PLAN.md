# 3mm OTA update and dependency plan

Status: Phase 1 and the Phase 2 release tooling are implemented locally on
2026-08-26. The first published release and all installation behavior remain
intentionally pending.

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
- no archive is downloaded and no package, service or filesystem state is changed;
- System Updates is an admin route available to the data-driven Menu Editor.

The public repository currently has no published GitHub Release. The expected
and honest result is therefore `no_release` until the first release is
published with a valid manifest.

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

Implemented locally:

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

Still pending:

- commit and push the release tooling;
- create the first semantic-version tag;
- let GitHub build and publish the first real release;
- validate that release through System Updates on `rasp-3mm`;
- exercise the published archive with the existing installer and health gates.

Acceptance boundary: a freshly published release appears as available on a
supported device, but the application still cannot install it.

## Phase 3 — Staged update and dependencies

- download only the selected manifest artifact into a bounded staging directory;
- verify size and SHA-256 before extraction;
- run disk-space, architecture, database-backup and migration preflight checks;
- compare declared APT packages with a reviewed 3mm allowlist;
- show the exact dependency plan and require explicit administrator approval;
- let a narrow privileged helper install only approved packages and activate the
  staged release through the existing immutable installer;
- require Core, Web and Agent health checks; restore the previous symlink,
  database backup and services on failure;
- retain an audit record without credentials or provider keys.

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

## Deliberately excluded from Phases 1–2

- automatic updates;
- downloading or extracting release archives;
- `apt`, `pip` or `npm` installation;
- `sudo`, service restart or systemd mutation;
- database migrations;
- changing NetworkManager;
- accepting prereleases or unvalidated branch snapshots.
