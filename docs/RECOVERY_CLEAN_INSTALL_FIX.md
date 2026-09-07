# Recovery after a clean installation

The release installer prepares `/etc/3mm/backup.key` and
`/var/lib/3mm/backups/exports` before starting runtime services. The key is
root-owned with mode `0600`. Preparation is idempotent: updates and Master
reset preserve an existing key because retained local backups depend on it.
Master reset also recreates missing recovery storage before restarting Core
and the update helper.

Portable `.3mmrecovery` files carry the source recovery key inside their
password-encrypted bundle. Import validates the bundle and re-encrypts the
archive with the destination device's key. A clean device therefore does not
need the source installation's `/etc/3mm/backup.key`.

Previously, import attempted to create the destination key inside the
read-only helper sandbox. The exception was hidden behind a generic helper
rejection. Import failures now produce a server traceback and distinguish
storage failures from invalid recovery files/passwords in the client response.
The helper does not receive additional write access to `/etc/3mm`.

Restore accepts the same version and older versions within the same major/minor
series (for example, `0.3.0-beta.9` into `0.3.0-beta.10`). The archive's database
revision must be an ancestor of the installed release's single Alembic head.
Protocol and architecture checks still apply. A newer archive or an unsupported
series/revision is rejected before live state changes, with a compatibility
message rather than a password error. After the state switch, the existing
migration, application reactivation and health-check sequence runs; its failure
restores the previous state. Cross-minor recovery is not implicitly supported.

Regression coverage includes a portable archive labelled with an older beta,
an actual database upgrade from an older revision, and restored application data.
Revision discovery does not initialize `backend.database`: the legacy baseline
loads model metadata only when executed, while the Alembic execution environment
loads the full model registry explicitly. A fresh-process regression and a
read-only systemd sandbox check cover this distinction.

## Publishing and acceptance

The one-command installer downloads a published release artifact, not the
current `main` source. These changes must be included in the next release
before a new installation through `install.sh` receives them.

Acceptance sequence:

1. Install the new published release on a fresh card with the documented
   one-command installer and complete setup.
2. Import a downloaded `.3mmrecovery` file from another installation using
   its export password, without first creating a local backup.
3. Verify restored users, settings, device identity and application data.
4. Repeat after Master reset. Check that existing local backups remain usable.
5. Verify that an incorrect export password produces a validation message and
   does not replace current application data.

Automated regression coverage includes storage preparation, key preservation,
cross-device portable import and decryption, reset mount paths, helper error
classification, and existing restore tests. Physical clean-card acceptance
remains separate from the automated checks.
