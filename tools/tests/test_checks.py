"""Check that scope selection cannot silently turn unknown changes green."""

import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("repository_checks", Path(__file__).parents[1] / "checks.py")
checks = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checks
SPEC.loader.exec_module(checks)


class SelectionTests(unittest.TestCase):
    def test_documentation_does_not_schedule_runtime_suites(self):
        plan = checks.select_checks(["AGENTS.MD", "docs/WORKING_STATE.md", "README.md"])
        self.assertEqual(checks.commands(plan, "all", "python"), [])

    def test_executable_in_docs_and_unknown_input_get_full_checks(self):
        for path in ("docs/example.py", "new_component/service.py", "package-lock.json", "../README.md"):
            with self.subTest(path=path):
                plan = checks.select_checks([path])
                self.assertEqual(plan.python, checks.PYTHON_SUITES)
                self.assertTrue(plan.frontend)

    def test_source_changes_keep_python_integration_coverage(self):
        for path in ("agent/device_transport.py", "components/admin_web/server.py",
                     "components/public_web/server.py", "components/platform_runtime/server.py",
                     "packages/provisioning/models.py", "components/setup/main.py",
                     "packages/application_sdk/platform.py", "components/system_runtime/update_helper.py"):
            with self.subTest(path=path):
                plan = checks.select_checks([path])
                self.assertIn("agent/tests", plan.python)
                self.assertIn("backend/tests", plan.python)
                self.assertIn("deployment/tests", plan.python)
                self.assertIn("components/admin_web/tests", plan.python)
                self.assertIn("components/public_web/tests", plan.python)
                self.assertIn("components/setup/tests", plan.python)
                self.assertIn("packages/provisioning/tests", plan.python)
                self.assertNotIn("three_mm_provisioning/tests", plan.python)
                self.assertNotIn("three_mm_public_web/tests", plan.python)
                self.assertNotIn("three_mm_web/tests", plan.python)
                self.assertNotIn("setup_service/tests", plan.python)
                self.assertNotIn("three_mm_application_sdk/tests", plan.python)
                self.assertIn("packages/application_sdk/tests", plan.python)
                self.assertEqual(plan.python, checks.PYTHON_SUITES)
                self.assertFalse(plan.frontend)

    def test_shared_contracts_keep_every_python_suite(self):
        for root in checks.PYTHON_ROOTS:
            with self.subTest(root=root):
                self.assertEqual(checks.select_checks([f"{root}/contract.py"]).python, checks.PYTHON_SUITES)

    def test_shared_wire_expands_python_and_unknown_packages_still_expand_every_group(self):
        for path in ('packages/platform_wire/__init__.py', 'packages/platform_wire/task_time.py'):
            with self.subTest(path=path):
                plan = checks.select_checks([path])
                self.assertEqual(plan.python, checks.PYTHON_SUITES)
                self.assertFalse(plan.frontend or plan.tooling)
        for path in ('packages/__init__.py', 'packages/future/module.py',
                     'packages/platform_wire_other/module.py', 'packages/provisioning_other/models.py',
                     'packages/application_sdk_other/platform.py'):
            with self.subTest(path=path):
                plan = checks.select_checks([path])
                self.assertEqual(plan.python, checks.PYTHON_SUITES)
                self.assertTrue(plan.frontend and plan.tooling)

    def test_test_only_change_selects_its_suite(self):
        self.assertEqual(checks.select_checks(["backend/tests/test_application_access.py"]).python,
                         ("backend/tests",))
        self.assertEqual(checks.select_checks(["components/admin_web/tests/test_server.py"]).python,
                         ("components/admin_web/tests",))
        self.assertEqual(checks.select_checks(["components/public_web/tests/test_server.py"]).python,
                         ("components/public_web/tests",))
        self.assertEqual(checks.select_checks(["components/setup/tests/test_api.py"]).python,
                         ("components/setup/tests",))
        self.assertEqual(checks.select_checks(["components/system_runtime/tests/test_update_helper.py"]).python,
                         ("components/system_runtime/tests",))
        self.assertEqual(checks.select_checks(["packages/protocol/tests/test_models.py"]).python,
                         ("packages/protocol/tests",))
        self.assertEqual(checks.select_checks(["packages/provisioning/tests/test_persistence.py"]).python,
                         ("packages/provisioning/tests",))
        self.assertEqual(checks.select_checks(["packages/application_sdk/tests/test_commands.py"]).python,
                         ("packages/application_sdk/tests",))

    def test_unknown_components_and_shared_parent_keep_full_checks(self):
        for path in ("components/future/service.py", "components/admin_web_other/server.py",
                     "components/public_web_other/server.py",
                     "components/platform_runtime_other/server.py",
                     "components/setup_other/main.py",
                     "components/system_runtime_other/update_helper.py",
                     "components/__init__.py"):
            with self.subTest(path=path):
                plan = checks.select_checks([path])
                self.assertEqual(plan.python, checks.PYTHON_SUITES)
                self.assertTrue(plan.frontend and plan.tooling)

    def test_fixtures_migrations_and_dependency_changes_expand_checks(self):
        for path in ("backend/tests/conftest.py", "backend/migrations/versions/change.py",
                     "backend/requirements.txt", "components/admin_web/tests/conftest.py",
                     "components/public_web/tests/conftest.py",
                     "components/setup/tests/conftest.py",
                     "packages/protocol/tests/conftest.py", "packages/protocol/models.py",
                     "packages/provisioning/tests/conftest.py", "packages/application_sdk/tests/conftest.py"):
            with self.subTest(path=path):
                self.assertEqual(checks.select_checks([path]).python, checks.PYTHON_SUITES)

    def test_combined_changes_preserve_both_families(self):
        plan = checks.select_checks(["frontend/src/App.vue", "backend/applications/authority/access.py"])
        self.assertTrue(plan.frontend)
        self.assertIn("backend/tests", plan.python)

    def test_selection_and_ci_changes_must_validate_all_groups(self):
        for path in ("tools/checks.py", "tools/tests/test_checks.py", ".github/workflows/ci.yml",
                     ".github/workflows/release.yml"):
            with self.subTest(path=path):
                plan = checks.select_checks([path])
                self.assertTrue(plan.tooling and plan.frontend)
                self.assertEqual(plan.python, checks.PYTHON_SUITES)

    def test_full_python_checks_preserve_the_existing_process_boundary(self):
        commands = checks.commands(checks.full_plan('full'), 'python', 'python')
        self.assertEqual(len(commands), 2)
        self.assertNotIn('deployment/tests', commands[0][1])
        self.assertEqual(commands[1][1][4:], ['deployment/tests', 'packages/application_sdk/tests'])


class GitAndExecutionTests(unittest.TestCase):
    def test_local_scope_includes_staged_unstaged_and_untracked(self):
        with patch.object(checks, "git_paths", side_effect=[['backend/a.py'], ['frontend/b.ts'], ['docs/c.md']]):
            self.assertEqual(checks.changed_paths(Path('.'), None, 'HEAD'),
                             ['backend/a.py', 'docs/c.md', 'frontend/b.ts'])

    def test_renames_are_compared_as_delete_and_add(self):
        commit = subprocess.CompletedProcess([], 0, stdout=b'a' * 40)
        with patch.object(checks.subprocess, 'run', return_value=commit):
            with patch.object(checks, "git_paths", return_value=['backend/old.py', 'agent/new.py']) as git:
                paths = checks.changed_paths(Path('.'), 'base', 'head')
                self.assertIn('--no-renames', git.call_args.args)
                self.assertIn('agent/tests', checks.select_checks(paths).python)

    def test_missing_comparison_base_cannot_skip_checks(self):
        for base in ('', '0' * 40):
            with self.subTest(base=base), self.assertRaises(ValueError):
                checks.changed_paths(Path('.'), base, 'HEAD')

    def test_failed_git_comparison_emits_full_ci_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'outputs'
            with patch.object(checks, 'changed_paths', side_effect=subprocess.CalledProcessError(1, 'git')):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(checks.main(['--base', 'missing', '--github-output', str(output)]), 0)
            self.assertEqual(output.read_text(), 'python=true\nfrontend=true\ntooling=true\n')

    def test_preview_never_executes_checks(self):
        with patch.object(checks.subprocess, 'run') as run, redirect_stdout(io.StringIO()):
            self.assertEqual(checks.main(['--paths', 'frontend/src/App.vue']), 0)
            run.assert_not_called()

    def test_runner_stops_at_the_first_failure(self):
        with patch.object(checks.subprocess, 'run', return_value=subprocess.CompletedProcess([], 7)) as run:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(checks.main(['--full', '--run']), 7)
            self.assertEqual(run.call_count, 1)


if __name__ == '__main__':
    unittest.main()
