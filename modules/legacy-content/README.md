# Preserved pre-v2 content sources

This directory preserves the former Page/Extension models, routes, arbitrary
table/translation engine and obsolete database scripts. It is source-only and
excluded from Core release payloads. `source/legacy` holds the moved originals;
`source/reference` holds copies of mixed files whose current Core consumers were
separated. Original paths and hashes are recorded in `../product-source-map.json`.
These files are recovery/development evidence, not an executable compatibility
server or a supported installation/reset workflow.

Current Core navigation owns `backend/db/menu.py`. Its table and API keep existing
menu items, localized labels and audience metadata. Validated immutable v2 language
packages own translations. Core stores only their selected package, language code
and enabled flag in `language_extension_installations`; English remains the
recovery fallback. No legacy Python extension code is imported or enabled.

Migration `9e74f5c60d64` preserves the eight former content/translation tables and
page/extension subsets of direct, role and group permissions in FK-free `retired_`
archives. An optional `extension_multilingual_content` prototype table is archived
when present. Current principals can be deleted without cascading into archives.
The migration preserves managed language selections and does not restore grants,
import archived records into an application or execute package code.

Old registry rows can claim arbitrary SQL tables. Before changing schema, the
migration refuses actual registered custom tables and incoming foreign keys from
retained tables to retired models. Those require an explicit ownership/export
plan; no data is guessed to be disposable. Registrations of Core-owned tables do
not transfer ownership or retire those tables.

Empty retirement supports downgrade through frozen historical DDL. Populated
archives/current language selections require recovery from a verified prior
database backup, with the matching release and package files. The optional
prototype table also requires backup recovery because its original constraints
are not assumed. A downgrade does not silently reintroduce historical authority.
Never run the preserved reset scripts against an installation.
