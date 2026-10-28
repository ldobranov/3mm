# Contacts application candidate

Contacts now uses the optional shared CRUD engine and renderer, public application
SDK/host, ordinary operator permissions and its own scoped relational database.
The source directory keeps its historical name; Core has no Contacts-specific
route, SQL, migration hook or module-name branch. The compiled route is `/contacts`.

Build from the repository with the project's Python environment:

```powershell
python modules/runtime-contacts/build_package.py --output .runtime/contacts-c3-local.zip
```

The builder refuses to overwrite an output file. This is a local, unpublished
candidate at the existing source version 1.0.0, not an overwrite of an uploaded
1.0.0 artifact. An existing catalog version with different bytes must remain
immutable; choose a separately authorized version before replacing such a package.
Installation/activation still requires normal review, current permissions,
compiled UI and the supported native scoped relational profile. Nothing is
installed, migrated, enabled or granted merely by running the builder.

Original manifest/definition and Core implementation are preserved under
`libraries/three_mm_crud/source/legacy`. Core retirement archives preserve all
historical rows. Import is explicit and administrator-only, uses current field
validation, preserves identity/provenance and refuses conflicts. No old access
grant is transferred. Tests use disposable own-data directories; they are not a
claim of owner-VM installation or fresh hardware/systemd acceptance.

See [shared CRUD](../../libraries/three_mm_crud/README.md) for limits, command
outcomes, retention/export/erasure and recovery behavior.
