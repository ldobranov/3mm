# CAP10 public form reference

`org.3mm.public-form-reference` serves `/demo-request` on the separate Public Web
listener. The visitor chooses **Morning** or **Afternoon**. It collects no
personal information, needs no account, and never uses the Core API, a connector
or hardware. Successful submission returns a plain-text acknowledgement.

From the repository root, with the existing project Python environment:

```powershell
New-Item -ItemType Directory -Force .runtime/cap10 | Out-Null
& .\.venv\Scripts\python.exe -m tools.build_public_form_reference --output .runtime/cap10/public-form-reference-1.0.0.zip
```

The builder validates the package and prints its SHA-256. It does not install,
approve or activate it, and refuses to overwrite an existing ZIP. The sample
does not require a frontend build.

The acceptance tests use an ephemeral loopback HTTP listener, real Unix
transport and a signed application host. They exercise upload, activation,
approval, disable, reactivation and uninstall through the actual Core routes.
The privileged helper connection and systemd are replaced by a disposable
process supervisor; no device is used. The public route stays closed until
approval, and uninstall removes the route and runtime but preserves app data.
Run from the repository in a non-root Linux development environment with test
dependencies already available:

```sh
python -m pytest -q three_mm_public_web/tests/test_server.py backend/tests/test_application_public_forms.py
```

In an explicitly approved disposable integration setup, Public Web's
`--form-origin` takes the exact external origin (HTTPS, or loopback HTTP for a
local test such as `http://127.0.0.1:8081`). Match the listener port for loopback;
the option does not terminate TLS or open a port on a device. The normal service
configuration does not enable POST. The exact form ZIP must also be reviewed and
active before it can be served. Use the separate Public Web origin, not the Core
admin origin. Do not expose the local test listener to the Internet.
