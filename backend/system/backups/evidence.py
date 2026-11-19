"""Closed vocabulary for sharing capture checks. No file, database or service access."""

NOTICES = {
    'compatibility.database': 'The Core database revision could not be verified.',
    'compatibility.device': 'The Standalone device identity or role could not be verified.',
    'compatibility.application': 'The Core version could not be determined.',
    'compatibility.installation_identity': 'Installation recovery material is missing or invalid.',
    'state.required_missing': 'Required state is missing.',
    'state.optional_missing': 'Some optional state is absent.',
    'state.symlink_rejected': 'A link cannot be included in this backup.',
    'state.special_file_rejected': 'An unsupported file type cannot be included.',
    'state.read_failed': 'A file could not be read consistently.',
    'state.application_data_invalid': 'Application-owned data requires recovery review.',
    'state.application_inventory_invalid': 'The application inventory could not be verified.',
    'state.application_package_invalid': 'An active application cannot be recovered from its recorded package.',
    'state.application_schema_invalid': 'Required active application data is missing or cannot be verified.',
    'state.application_separate_preparation': 'An active application requires separate preparation. The archive can preserve its data, but an automatic full Standalone restore will be refused.',
    'state.application_profile_unverified': 'The bounded readiness check could not verify the restore profile of every active application.',
    'storage.inspect_failed': 'Available backup space could not be checked.',
    'storage.insufficient': 'Free space is insufficient for this backup.',
    'other': 'Another preflight check reported a problem.',
}


def checked_inventory(value):
    """Never render arbitrary messages, names, paths or identities from an imported file."""
    def count(n): return type(n) is int and 0 <= n <= 2**53-1
    if (type(value) is not dict or value.get('kind') != 'backup_inventory_check' or
            type(value.get('schema_version')) is not int or value['schema_version'] != 1 or
            value.get('scope') != 'capture_preflight_only' or value.get('archive_verified') is not False or
            type(value.get('ready_to_capture')) is not bool or type(value.get('issues')) is not list or
            len(value['issues']) > 2*len(NOTICES)):
        raise ValueError('Invalid inventory evidence')
    ready = value['ready_to_capture']
    inventory = value.get('inventory')
    files = value.get('file_count')
    apps = value.get('listed_application_groups')
    extra = value.get('unlisted_application_files')
    if (inventory not in ('available','not_available') or ready != (inventory == 'available') or
            (ready and (not count(files) or files < 1 or not count(apps) or apps > min(files,32) or
                        not count(extra) or extra > files - apps)) or
            (not ready and (files is not None or apps is not None or extra is not None))):
        raise ValueError('Invalid inventory counts')
    issues, seen = [], set()
    for row in value['issues']:
        if type(row) is not dict:
            raise ValueError('Invalid inventory issue')
        severity, code, n = row.get('severity'),row.get('code'),row.get('occurrences')
        if (severity not in ('warning','error') or type(code) is not str or code not in NOTICES or
                not count(n) or n < 1 or (severity,code) in seen or (ready and severity=='error')):
            raise ValueError('Invalid inventory issue')
        seen.add((severity,code))
        issues.append({'severity':severity,'code':code,'occurrences':n})
    return dict(schema_version=1,kind='backup_inventory_check',scope='capture_preflight_only',archive_verified=False,
                ready_to_capture=ready,inventory=inventory,file_count=files,listed_application_groups=apps,
                unlisted_application_files=extra,issues=issues)
