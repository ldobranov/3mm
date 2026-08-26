# Publishing a 3mm release

The release workflow is intentionally tag-driven. A GitHub Release must point
to a reviewed commit already contained in `main`; branch snapshots and dirty
working trees are not publishable releases.

## What the workflow does

For a tag such as `v1.2.0`, `.github/workflows/release.yml`:

1. verifies that the tag is valid semantic versioning and its commit belongs to `main`;
2. runs the complete backend and frontend checks;
3. builds the production frontend from locked dependencies;
4. exports the exact tagged Git tree with `git archive`;
5. builds artifacts for `aarch64`, `armv7l` and `x86_64` twice;
6. rejects the release unless both builds are byte-for-byte identical;
7. generates `3mm-update-manifest.json` and `SHA256SUMS`;
8. uploads everything to a draft GitHub Release;
9. publishes the release only after every asset was uploaded successfully.

A prerelease semantic version such as `v1.2.0-beta.1` is published as a GitHub
prerelease. Normal versions use the `stable` channel, `-test...` versions use
the `test` channel, and every other prerelease uses `beta`. Stable catalog
checks deliberately ignore prereleases; an administrator must select a preview
channel explicitly.

## Required assets

A completed release contains:

```text
3mm-<version>-aarch64.tar.gz
3mm-<version>-armv7l.tar.gz
3mm-<version>-x86_64.tar.gz
3mm-update-manifest.json
SHA256SUMS
```

Every archive contains the same reviewed source and built frontend, plus
architecture-specific `.3mm-release.json` metadata. File ordering, ownership,
permissions and timestamps are normalized using the tagged commit timestamp.

## Reviewed dependency declaration

`deployment/release-dependencies.json` lists the host packages required by the
release. The builder accepts only a sorted, duplicate-free list of safe Debian
package names. The staged updater also requires every name to exist in the
independently reviewed `deployment/update-dependency-allowlist.json` shipped by
the already installed release.

Adding or removing a package is a code-reviewed change. The future privileged
helper must also apply its own allowlist and must never execute package names,
commands or scripts supplied by an AI response.

## Publishing

After the release changes are committed, tested and pushed to `main`, an
authorized maintainer creates and pushes one annotated semantic-version tag:

```powershell
git tag -a v1.2.0 -m "3mm 1.2.0"
git push origin v1.2.0
```

Creating the tag triggers publication. Do not reuse or move a published release
tag. A correction receives a new version.

## Verification

After the workflow succeeds:

- confirm that all five assets are present on the GitHub Release;
- open **System updates** as an administrator;
- press **Check for updates**;
- confirm that the manifest is validated and the correct device architecture is listed;
- confirm that dependency packages are displayed as a preview only.

Phase 3 manual staging and explicit installation approval were physically
accepted on `rasp-3mm` with successful `v0.2.3` activation and real failed-run
rollback evidence. Preview channels still require a separate published
acceptance release before scheduled checks are considered.
The installed `.3mm-release.json` must contain `version`; both the manual
deployment launcher and published artifacts source it from the repository
`VERSION` file so the updater can reject same-version and downgrade attempts.
