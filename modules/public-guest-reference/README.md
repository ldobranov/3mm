# CAP10 guest draft reference

`org.3mm.public-guest-reference` serves `/demo-guest` on an explicitly enabled
Public Web test origin. Save **Morning** or **Afternoon**, then reopen the form
in the same browser. A separate browser starts with no draft. After 15 minutes,
a Core restart or a change of application authority, the old session cannot
resume or submit. No name, account, payment or other personal data is collected.

Build the separate example from the repository root, without overwriting the
existing anonymous form example:

```powershell
New-Item -ItemType Directory -Force .runtime/cap10 | Out-Null
& .\.venv\Scripts\python.exe -m tools.build_public_form_reference --guest --output .runtime/cap10/public-guest-reference-1.0.0.zip
```

Run the real transport and token checks in the non-root Linux development lab:

```sh
python -m pytest -q backend/tests/test_public_form_guests.py backend/tests/test_application_public_forms.py components/public_web/tests/test_server.py
```

This build does not install the example or enable the listener. For a disposable
browser setup, use an exact loopback origin (such as `http://127.0.0.1:8081`) with
`--guest-forms`, the current components, and separate approval of this exact
package in the lab. Do not bind the lab to a network interface. The [guest
contract](../../docs/PUBLIC_WEB_EXTENSION_PLAN.md#cap10--temporary-guest-draft)
describes the separate HTTPS origin boundary and the limits of this profile.
