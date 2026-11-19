"""Small, read-only operator view of a backup preflight; not an archive or a restore receipt."""
from collections import Counter
from pathlib import PurePosixPath
import re
import sqlite3
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.system.backups.service import BackupPreviewResponse, _database_path
from backend.system.backups.evidence import NOTICES, checked_inventory


MAX_APPLICATIONS = 32
_MODULE = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,159}\Z')
_VERSION = re.compile(r'[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}\Z')


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')


class IssueCount(_Model):
    severity: Literal['warning','error']
    code: str
    occurrences: int = Field(ge=1)


class Issue(IssueCount):
    message: str


class InventoryEvidence(_Model):
    schema_version: Literal[1]
    kind: Literal['backup_inventory_check']
    scope: Literal['capture_preflight_only']
    archive_verified: Literal[False]
    ready_to_capture: bool
    inventory: Literal['available','not_available']
    file_count: int | None
    listed_application_groups: int | None
    unlisted_application_files: int | None
    issues: tuple[IssueCount,...] = Field(max_length=2*len(NOTICES))


class ApplicationFootprint(_Model):
    instance_id: str = Field(pattern=r'^[0-9a-f]{24}$')
    files: int = Field(ge=1)
    size_bytes: int = Field(ge=0)
    catalog_state: Literal['installed','retained','unmatched','unavailable'] = 'unavailable'
    module_id: str | None = None
    package_version: str | None = None


class BackupReadiness(_Model):
    schema_version: Literal[1] = 1
    ready: bool
    entry_count: int = Field(ge=0)
    estimated_backup_bytes: int = Field(ge=0)
    available_bytes: int = Field(ge=0)
    issues: tuple[Issue,...]
    inventory: Literal['available','not_available']
    applications: tuple[ApplicationFootprint,...] = Field(max_length=MAX_APPLICATIONS)
    unlisted_application_files: int | None = Field(default=None, ge=0)

    def shareable(self):
        # Reconstruct an allowlisted snapshot; never serialize the whole admin
        # view (which includes app identities, versions, sizes and issue text).
        raw = dict(schema_version=1,kind='backup_inventory_check',scope='capture_preflight_only',archive_verified=False,
                   ready_to_capture=self.ready,inventory=self.inventory,
                   file_count=self.entry_count if self.inventory=='available' else None,
                   listed_application_groups=len(self.applications) if self.inventory=='available' else None,
                   unlisted_application_files=self.unlisted_application_files,issues=[
                       {'severity':row.severity,'code':row.code,'occurrences':row.occurrences} for row in self.issues])
        return checked_inventory(raw)


class OperatorReadiness(BackupReadiness):
    # Admin HTTP response only. The independently running helper's existing
    # strict wire model stays unchanged, including on a mixed-version upgrade.
    support_summary: InventoryEvidence | None = None


def _owners(database_url, instances):
    if not instances:
        return {}
    ids = tuple(instances)
    params = ','.join('?' for _ in ids)
    try:
        uri = _database_path(database_url).resolve().as_uri() + '?mode=ro'
        connection = sqlite3.connect(uri, uri=True, timeout=0.25)
        try:
            connection.execute('PRAGMA query_only=ON')
            connection.execute('PRAGMA trusted_schema=OFF')
            # Two existing unique instance indexes, no scans of application data.
            rows = connection.execute(f'''
                SELECT i.instance_id, i.module_id, p.version, 'installed'
                FROM application_extension_installations i LEFT JOIN module_packages p
                    ON p.id=i.module_package_id AND p.module_id=i.module_id
                WHERE i.instance_id IN ({params})
                UNION ALL SELECT instance_id, module_id, NULL, 'retained'
                FROM application_retained_data WHERE instance_id IN ({params})''', ids+ids).fetchall()
        finally:
            connection.close()
    except (ValueError, OSError, sqlite3.Error):
        return {}
    owners = {instance: {'catalog_state':'unmatched'} for instance in ids}
    duplicates = set()
    for instance, module, version, state in rows:
        if instance in duplicates or not isinstance(module, str) or not _MODULE.fullmatch(module):
            owners[instance] = {'catalog_state':'unavailable'}
        else:
            owners[instance] = {'module_id':module, 'catalog_state':state,
                'package_version':version if isinstance(version,str) and _VERSION.fullmatch(version) else None}
        duplicates.add(instance)
    return owners


def summarize_backup(preview: BackupPreviewResponse, database_url: str) -> BackupReadiness:
    groups = Counter((issue.severity, issue.code if issue.code in NOTICES else 'other') for issue in preview.issues)
    issues = tuple(Issue(severity=severity,code=code,message=NOTICES[code],occurrences=count)
                   for (severity,code), count in sorted(groups.items()))
    footprints = {}
    omitted = 0
    if preview.manifest is not None:
        for item in preview.manifest.entries:
            if item.area != 'applications':
                continue
            parts = PurePosixPath(item.path).parts
            if len(parts)<3 or parts[1]!='data' or not re.fullmatch(r'[0-9a-f]{24}',parts[0]):
                omitted += 1
                continue
            instance = parts[0]
            if instance not in footprints and len(footprints) >= MAX_APPLICATIONS:
                omitted += 1
                continue
            counts = footprints.setdefault(instance, [0,0])
            counts[0] += 1
            counts[1] += item.size_bytes
    owners = _owners(database_url, footprints)
    return BackupReadiness(ready=preview.ready, entry_count=preview.entry_count,
        estimated_backup_bytes=preview.estimated_backup_bytes, available_bytes=preview.available_bytes, issues=issues,
        inventory='available' if preview.manifest is not None else 'not_available',
        unlisted_application_files=omitted if preview.manifest is not None else None,
        applications=tuple(ApplicationFootprint(instance_id=i,files=n,size_bytes=size,**owners.get(i,{}))
                           for i,(n,size) in sorted(footprints.items())))
