# File and media probe

Local CAP11 reference consumer; no hardware commands, external connectors or
automatic navigation entries. Requires file-contract-v2 Core/application host.

Build locally with:

```powershell
python modules/file-probe/build_package.py --output .runtime/file-probe-1.0.0.zip
```

The deterministic ZIP uses manifest v2, service SDK 1.3 and public
`@3mm/application-ui/v1` / `@3mm/ui/v1`. It has a health-only native service and
the `/file-probe` route. Upload/bytes/metadata never use application operations.
Limits: 8 MiB/file, 32 MiB committed, 64 files, two uploads, 16 MiB staging,
one-hour upload expiry. Separate read/write/publish/transform permissions apply.

For later owner-run acceptance, after explicitly installing the new Core/host:

1. Upload/install this ZIP in Extensions and approve the chosen application and
   human permissions. Public sharing/image processing initially remain unchecked.
   Enable the application and open `/file-probe`; an empty saved menu is valid.
2. Choose a file, prepare it, send/pause after a chunk. Reload, reselect the same
   file, check its confirmed offset, then resume/finalize. Verify its checksum.
3. Download and compare bytes. A new upload with an existing logical ID conflicts
   in this create-only demo; use another ID or explicitly delete that file first.
4. Explicitly allow publish for the application and your account. Create a
   five-minute/three-download link, open it without an account, download, revoke
   it and confirm further access is denied. Disabling the app must also deny it.
5. With the optional image provider installed and transform access allowed,
   upload a PNG/JPEG/WebP, create a 256px derivative and preview it. A document or
   unavailable provider reports a failed job while ordinary files still work.

An unconfirmed mutation is not retried. Observe the upload offset, file/job or
receipt before deciding on a fresh intent. The full contract and lifecycle are
in [APPLICATION_FILES.md](../../docs/APPLICATION_FILES.md). These are test
instructions, not a deployment performed by the agent.
