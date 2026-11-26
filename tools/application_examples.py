"""Local source references for authors. These are not installed capabilities."""
from hashlib import sha256
from packages.protocol.diagnostic_snapshot import read_regular
from tools.application_project import ProjectCheckError, REPOSITORY, local_path


DATA = 'libraries/data_tools/'
REPORT = DATA + 'examples/report_task/'
LIBRARY = DATA + 'application_data_tools/'
TEST = DATA + 'tests/'
STARTER = 'modules/application-starter/'

# Only these repository-owned paths are opened. Lookups never accept a path,
# import examples, inspect an application's files or connect to a Core.
EXAMPLES = {
    'starter': ('UI, owned SQLite data and an optional device selection',
                STARTER+'README.md', 'Read and change the example',
                (STARTER+'application-extension.json', STARTER+'source/frontend/Notes.vue',
                 STARTER+'service/starter_app/service.py'), (STARTER+'tests/test_service.py',)),
    'tables': ('Review tabular input before applying it; export only authorized rows',
               DATA+'README.md', 'Import in two steps', (LIBRARY+'tabular.py',), (TEST+'test_tabular.py',)),
    'search': ('Index and search only the current visibility partition',
               DATA+'README.md', 'Search only a currently visible partition', (LIBRARY+'search.py',), (TEST+'test_search.py',)),
    'report-task': ('Render a private printable table in a bounded task; return only its receipt',
                    DATA+'README.md', 'Printable table as a bounded task',
                    (LIBRARY+'report.py', REPORT+'build_reference.py', REPORT+'service/report_example/service.py'),
                    (TEST+'test_report.py',)),
    'inbox': ('Opt-in report notices, original-intent delivery and bounded retries',
              DATA+'README.md', 'Opt-in, in-app notifications',
              (LIBRARY+'inbox.py', REPORT+'notice_integration.py'), (TEST+'test_inbox.py', TEST+'test_report_intent.py')),
}


def example_catalog(identifier=None):
    keys = sorted(EXAMPLES) if identifier is None else (identifier,)
    if any(k not in EXAMPLES for k in keys):
        raise ProjectCheckError('examples', 'Unknown example. List examples to see the available IDs.')
    rows, seen = [], {}
    for key in keys:
        title, guide, heading, sources, tests = EXAMPLES[key]
        for name in (guide, *sources, *tests):
            if name not in seen:
                try:
                    seen[name] = read_regular(local_path(REPOSITORY, name), 512 * 1024)
                except (ValueError, OSError, RuntimeError):
                    seen[name] = None
        files = (guide, *sources, *tests)
        available = all(seen[n] for n in files) and ('## ' + heading).encode() in seen[guide].splitlines()
        row = {'id': key, 'title': title, 'state': 'present' if available else 'incomplete_checkout',
               'guide': guide, 'heading': heading, 'sources': list(sources), 'test_files': list(tests)}
        if identifier is not None and available:
            row['source_sha256'] = {n: sha256(seen[n]).hexdigest() for n in files}
        rows.append(row)
    return {'schema_version': 1, 'scope': 'authoring_source_only', 'tests_run': False,
            'installation': 'not_requested', 'examples': rows}
