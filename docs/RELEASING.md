# Publishing a 3mm release

3mm releases are immutable, tag-driven builds from reviewed commits already
contained in `main`. A branch snapshot, dirty working tree or manually
selected Release ref is not publishable.

## Version and channel policy

[Semantic Versioning](https://semver.org/) is used while the product remains
pre-1.0. The repository-root [`VERSION`](../VERSION) file is the single source
of the application release version.

| Version/tag example | Update channel | GitHub state |
| --- | --- | --- |
| `0.3.0` / `v0.3.0` | Stable | Release |
| `0.3.0-beta.5` / `v0.3.0-beta.5` | Beta | Prerelease |
| `0.3.0-test.1` / `v0.3.0-test.1` | Test | Prerelease |

Stable catalog checks deliberately ignore prereleases. An administrator must
select Beta or Test explicitly; preview channels do not weaken any artifact or
approval checks.

Never reuse, move or recreate a published tag. A correction always receives a
new version.

## Release preparation

Before tagging:

1. start from a clean `main` synchronized with `origin/main`;
2. choose the next semantic version and update `VERSION`;
3. move the relevant entries from `[Unreleased]` into a dated section in
   [`CHANGELOG.md`](../CHANGELOG.md);
4. update the current validated release in [`README.md`](../README.md) when
   acceptance has changed;
5. run the complete backend and frontend checks;
6. commit and push the reviewed release changes to `main`.

Canonical checks:

```bash
backend/.venv/bin/python -m pytest -q
pnpm --dir frontend run test:unit -- --run
pnpm --dir frontend run type-check
pnpm --dir frontend run build-only
git diff --check
```

On Windows, use `backend\.venv\Scripts\python`. The four Agent assertions
for Unix `0600` mode bits cannot be represented by NTFS and must still pass
in Linux CI.

## Tagging

Read the version from `VERSION`, create an annotated tag and push it
separately:

```powershell
$version = (Get-Content VERSION -Raw).Trim()
git tag -a "v$version" -m "3mm v$version"
git push origin main
git push origin "v$version"
```

The Release workflow intentionally has no manual dispatch trigger. Publication
must originate from the immutable version tag. If GitHub fails to process a
tag, wait for the service to recover and issue a new version rather than
rewriting history.

## What the workflow verifies

For a tag such as `v0.3.0-beta.5`,
[`.github/workflows/release.yml`](../.github/workflows/release.yml):

1. verifies the semantic-version tag and exact `VERSION` match;
2. proves that the tagged commit belongs to `main`;
3. requires an annotated tag that resolves to the selected commit;
4. runs all backend and frontend tests, type checking and the production build;
5. exports the exact Git tree with `git archive`;
6. builds `aarch64`, `armv7l` and `x86_64` artifacts twice;
7. rejects the release unless both builds are byte-for-byte identical;
8. generates the channel-aware manifest and checksums;
9. uploads every asset to a draft GitHub Release;
10. makes the Release visible only after the complete upload succeeds.

## Required release assets

A complete release contains exactly the expected architecture archives plus
metadata:

```text
3mm-<version>-aarch64.tar.gz
3mm-<version>-armv7l.tar.gz
3mm-<version>-x86_64.tar.gz
3mm-update-manifest.json
SHA256SUMS
```

Every archive contains the same reviewed source and prebuilt frontend plus
architecture-specific `.3mm-release.json` metadata. File ordering, ownership,
permissions and timestamps are normalized using the tagged commit timestamp.

## Dependency boundary

[`deployment/release-dependencies.json`](../deployment/release-dependencies.json)
declares required host packages. The builder accepts only a sorted,
duplicate-free list of safe Debian package names.

The updater also requires every package to appear in the independently
reviewed
[`deployment/update-dependency-allowlist.json`](../deployment/update-dependency-allowlist.json)
shipped by the already installed release. Generated or provider-supplied
commands are never accepted as update dependencies.

## Publication verification

After the workflow succeeds:

1. confirm the GitHub Release is not a draft;
2. confirm prerelease state matches the selected channel;
3. confirm all five required assets are present;
4. inspect `3mm-update-manifest.json` for version, tag, commit, channel and
   architecture entries;
5. confirm `SHA256SUMS` covers every archive and the manifest;
6. keep the Release immutable after it becomes visible.

## Device acceptance

Open **System updates** as an administrator and use the same channel as the
release:

1. check for updates without changing the device;
2. confirm the latest version, channel and validated manifest;
3. stage the update and review every preflight result;
4. verify the architecture, dependency plan and rollback target;
5. provide the exact `INSTALL <version>` confirmation;
6. wait for the operation to reach `succeeded`;
7. independently verify `/opt/3mm/current`, `/opt/3mm/previous`, service
   health and persistent Agent identity;
8. check the same channel again and require `up_to_date`.

For normal operation, automatic checks may be enabled after this acceptance.
They cache catalog metadata only. Confirm the selected channel, interval, last
check and retry state in **Update policy**. If a maintenance window is enabled,
install inside it or deliberately acknowledge the separate outside-window
override; neither choice turns staging or installation into an unattended
operation.

For the first release of a newly introduced channel, install one published
bootstrap release through the reviewed immutable installer. Publish a second
release and use it to prove the complete in-application OTA path.

## Accepted release evidence

- `v0.2.3` completed physical staged-install and rollback acceptance on
  `rasp-3mm`.
- `v0.3.0-beta.3` was the channel-aware Beta bootstrap release.
- `v0.3.0-beta.4` completed the real Beta OTA path from `beta.3`, preserved
  the persistent device identity and retained `beta.3` as the rollback
  release.

Tags `v0.3.0-beta.1` and `v0.3.0-beta.2` are historical failed publication
attempts, not accepted GitHub Releases. They must not be moved or reused.
