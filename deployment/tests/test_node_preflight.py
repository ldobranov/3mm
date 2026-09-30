from deployment.node_preflight import inspect_node


def test_armv6_is_a_candidate_not_a_certified_installer():
    looked_up = []
    report = inspect_node(machine='armv6l', system='Linux', python_version=(3, 13),
        lookup=lambda name: looked_up.append(name) or '/usr/bin/' + name,
        importer=lambda name: None)
    assert report['runtime_dependencies_ready']
    assert not report['installer_ready']
    assert 'node' not in looked_up and 'npm' not in looked_up


def test_missing_dependency_and_old_python_are_reported_without_raw_errors():
    def imports(name):
        if name == 'requests':
            raise ImportError('private/path/must-not-leak')
    report = inspect_node(machine='armv6l', system='Linux', python_version=(3, 10),
        lookup=lambda name: '/usr/bin/' + name, importer=imports)
    assert not report['runtime_dependencies_ready']
    assert not next(c for c in report['checks'] if c['name'] == 'python')['passed']
    assert 'private/path' not in str(report)


def test_unknown_architecture_and_missing_commands_fail():
    report = inspect_node(machine='unknown', system='Linux', python_version=(3, 13),
        lookup=lambda name: None, importer=lambda name: None)
    assert not report['runtime_dependencies_ready']
