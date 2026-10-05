# Core writable asset storage

Code and data must not share a release directory:

- `/opt/3mm/releases/<release-id>`: immutable code and bundled assets.
- `/etc/3mm`: protected configuration and keys.
- `/var/lib/3mm`: mutable, persistent installation state.

## Public asset store

`backend.services.asset_storage.get_asset_storage()` uses the existing
`BackendSettings.uploads_dir` / `UPLOADS_DIR` configuration. The installer sets
it to `/var/lib/3mm/core/uploads`; local development retains its configured
checkout upload directory. Static serving, image operations and backup all
use this same root. No new database field or migration is required.

```text
/var/lib/3mm/core/uploads/
  settings/                         uploaded logos and settings images
  extensions/<extension-id>/        namespaced public assets, when used
  modules/                          existing package storage, unchanged
```

Backend consumers can use the shared helper without deriving paths from
`__file__`, the working directory or `/opt/3mm/current`:

```python
from backend.services.asset_storage import get_asset_storage

storage = get_asset_storage()
storage.settings_dir(create=True)
storage.write_bytes("settings", "logo.png", validated_image_bytes)
url = storage.public_url("settings", "logo.png")
storage.extension_dir(validated_extension_id, create=True)
```

`directory`, `file`, `settings_dir` and `extension_dir` validate relative paths
and reject traversal, absolute paths and symbolic links below the configured
root. `write_bytes` stages the upload in the destination directory and replaces
it atomically; a failed write leaves the previous asset intact and cleans up
the staging file. URLs remain `/uploads/...`, independently of the release ID.

This is an in-process backend helper, **not a new extension SDK filesystem
grant**. Consumers still enforce their own authorization, namespace ownership,
content types and size limits. It is not a sandbox for untrusted code or
concurrent filesystem writers.

## Settings endpoint compatibility

The legacy `/upload/settings-image` endpoint retains the stable `logo.<ext>`
filename. `/api/settings/upload-image` retains unique filenames and accepts
the existing query `directory` or the image editor's multipart form field.
Settings operations are bounded to `settings/` and its child directories;
they cannot write another extension's assets. Existing image MIME types and
the 2 MiB size limit remain. Listing remains public and mutations require an
active authenticated user, as before. The helper does not decode image data
or introduce an SVG sanitization policy.

Listing, folder creation, rename and delete use the same configured root.
Validation errors remain client errors, rather than being converted into an
upload failure with status 500. Reads do not create directories.

## Private data and recovery

Everything reachable through `/uploads` is public. Do not store credentials,
private documents, application databases or private generated files here.
Application extensions already have their own private `data/` directory under
the application runtime root. Their existing storage and access contracts
remain unchanged. Temporary private work must use private storage, not this
public asset store.

The existing backup source includes the complete configured uploads root.
Settings assets are therefore included in local backup and portable export /
import / restore without a separate backup subsystem. A release update does
not move or delete them; factory reset remains a deliberate data erasure and
requires a recovery backup to restore them.

No release permissions, systemd protections or installer layout are changed.
If an older nonstandard deployment wrote images into a checkout or release,
an administrator must copy those desired images into the configured uploads
root before discarding that old directory. Existing URL paths can be kept;
the application does not silently copy or overwrite historical release data.
