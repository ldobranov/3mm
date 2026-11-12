"""Lab isolation and provenance checks; never contact a device or package index."""

import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock

from tools import dev_lab


class DevLabTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def archive(self, *, content=b"original", stored=None, extra=(), duplicate=False):
        hashes = {"backend/example.py": dev_lab.digest(content)}
        manifest = {"schema_version": 1, "head": "a" * 40, "files": hashes,
                    "source_sha256": dev_lab.digest(json.dumps(hashes, sort_keys=True).encode())}
        path = self.root / "snapshot.tar"
        entries = [("backend/example.py", stored if stored is not None else content),
                   (dev_lab.MANIFEST, json.dumps(manifest).encode())]
        if duplicate:
            entries.append(entries[0])
        with tarfile.open(path, "w") as bundle:
            for name, blob in entries:
                info = tarfile.TarInfo(name)
                info.size = len(blob)
                bundle.addfile(info, io.BytesIO(blob))
            for info in extra:
                bundle.addfile(info, io.BytesIO(b""))
        return path

    def test_pack_captures_dirty_and_new_source_without_live_configuration(self):
        names = ["backend/example.py", "backend/new.py", "backend/deleted.py",
                 "install.sh", "deploy.ps1", ".github/workflows/release.yml", "private-deploy.ps1",
                 "backend/private.env", "backend/.env.local", "backend/data/live.db",
                 "backend/prices.json", "backend/output.json",
                 ".git/local-access.md", "config.json", ".runtime/secret.py"]
        for name in names:
            if name == "backend/deleted.py":
                continue
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"dirty source" if name.endswith("example.py") else b"private")

        def git(_repo, *args):
            return b"a" * 40 if args[0] == "rev-parse" else b"\0".join(p.encode() for p in names)

        with mock.patch.object(dev_lab, "git", side_effect=git), mock.patch("builtins.print"):
            archive = dev_lab.pack(self.root)
        destination = self.root / "extracted"
        manifest = dev_lab.unpack(archive, destination)
        self.assertEqual(set(manifest["files"]), {"backend/example.py", "backend/new.py",
                         "install.sh", "deploy.ps1", ".github/workflows/release.yml"})
        self.assertEqual((destination / "backend/example.py").read_bytes(), b"dirty source")
        self.assertNotIn("backend/deleted.py", manifest["files"])

    def test_optional_library_source_is_explicit_and_roundtrips_without_installation(self):
        ordinary = 'backend/example.py'
        library = ['libraries/shared/shared/__init__.py', 'libraries/shared/shared/engine.py',
                   'libraries/shared/frontend/Page.vue', 'libraries/shared/.3mm-source-only']
        private = ['libraries/shared/private.env', 'libraries/shared/data/live.db',
                   'libraries/shared/node_modules/package/index.js', 'libraries/shared/dist/bundle.js']
        names = [ordinary, 'frontend/package.json', *library, *private]
        for name in names:
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'source fixture')
        def git(_repo, *args):
            return b'a'*40 if args[0] == 'rev-parse' else b'\0'.join(name.encode() for name in names)
        with mock.patch.object(dev_lab, 'git', side_effect=git), mock.patch('builtins.print'):
            minimal = dev_lab.pack(self.root)
            included = dev_lab.pack(self.root, with_libraries=True)
        self.assertEqual(set(dev_lab.unpack(minimal, self.root/'minimal')['files']), {ordinary})
        manifest = dev_lab.unpack(included, self.root/'with-libraries')
        self.assertEqual(set(manifest['files']), {ordinary, *library})
        self.assertEqual((self.root/'with-libraries'/library[0]).read_bytes(), b'source fixture')

    def test_nested_web_snapshot_includes_parent_but_not_other_components(self):
        included = ["components/__init__.py", "components/admin_web/__init__.py",
                    "components/admin_web/__main__.py",
                    "components/admin_web/server.py", "components/admin_web/tests/test_server.py",
                    "components/public_web/__init__.py", "components/public_web/__main__.py",
                    "components/public_web/server.py", "components/public_web/webhook_pilot.py",
                    "components/public_web/tests/test_server.py",
                    "components/platform_runtime/__init__.py", "components/platform_runtime/__main__.py",
                    "components/platform_runtime/server.py", "components/platform_runtime/tasks.py",
                    "components/setup/__init__.py", "components/setup/__main__.py",
                    "components/setup/main.py", "components/setup/product.py",
                    "components/setup/requirements.txt", "components/setup/static/setup.html",
                    "components/setup/tests/test_api.py", "components/system_runtime/__init__.py",
                    "components/system_runtime/update_helper.py", "components/system_runtime/tests/test_update_helper.py"]
        excluded = ["components/future/service.py", "components/admin_web_other/server.py",
                    "components/admin_web/.env.local", "components/admin_web/data/live.db",
                    "components/admin_web/__pycache__/server.pyc", "three_mm_web/server.py",
                    "components/public_web_other/server.py", "three_mm_public_web/server.py",
                    "components/public_web/.env.local", "components/public_web/data/live.db",
                    "components/public_web/__pycache__/server.pyc",
                    "components/platform_runtime_other/server.py", "three_mm_platform_runtime/server.py",
                    "components/platform_runtime/data/live.db", "components/platform_runtime/.env.local",
                    "components/platform_runtime/__pycache__/server.pyc",
                    "components/setup_other/main.py", "setup_service/main.py",
                    "components/setup/data/live.db", "components/setup/.env.local",
                    "components/setup/__pycache__/main.pyc", "three_mm_runtime/update_helper.py",
                    "components/system_runtime_other/update_helper.py", "components/system_runtime/.env.local",
                    "components/system_runtime/data/live.db", "components/system_runtime/__pycache__/update_helper.pyc"]
        names = included + excluded
        for name in names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(name.encode())

        def git(_repo, *args):
            return b"a" * 40 if args[0] == "rev-parse" else b"\0".join(name.encode() for name in names)

        with mock.patch.object(dev_lab, "git", side_effect=git), mock.patch("builtins.print"):
            archive = dev_lab.pack(self.root)
        manifest = dev_lab.unpack(archive, self.root / "extracted")
        self.assertEqual(set(manifest["files"]), set(included))
        for name in included:
            self.assertEqual((self.root / "extracted" / name).read_bytes(), name.encode())

    def test_neutral_shared_snapshot_includes_parent_assets_but_not_other_packages(self):
        included = ['packages/__init__.py', 'packages/platform_wire/__init__.py',
                    'packages/platform_wire/task_time.py', 'packages/platform_wire/event_delivery.py',
                    'packages/protocol/__init__.py', 'packages/protocol/models.py',
                    'packages/protocol/theme_design_defaults.json', 'packages/protocol/tests/test_models.py',
                    'packages/provisioning/__init__.py', 'packages/provisioning/network_recovery.py',
                    'packages/provisioning/tests/test_network_recovery.py',
                    'packages/application_sdk/__init__.py', 'packages/application_sdk/commands.py',
                    'packages/application_sdk/tests/test_commands.py']
        excluded = ['packages/future/module.py', 'packages/platform_wire_other/module.py',
                    'packages/platform_wire/.env.local', 'packages/platform_wire/data/live.db',
                    'packages/platform_wire/__pycache__/module.pyc', 'three_mm_platform_wire/__init__.py',
                    'packages/protocol_other/models.py', 'packages/protocol/.env.local',
                    'packages/protocol/data/live.db', 'three_mm_protocol/__init__.py',
                    'packages/provisioning_other/models.py', 'packages/provisioning/.env.local',
                    'packages/provisioning/data/live.db', 'packages/provisioning/__pycache__/models.pyc',
                    'three_mm_provisioning/__init__.py', 'three_mm_application_sdk/__init__.py',
                    'packages/application_sdk_other/platform.py', 'packages/application_sdk/.env.local',
                    'packages/application_sdk/data/live.db', 'packages/application_sdk/__pycache__/platform.pyc']
        names = included + excluded
        for name in names:
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(name.encode())
        def git(_repo, *args):
            return b'a'*40 if args[0] == 'rev-parse' else b'\0'.join(name.encode() for name in names)
        with mock.patch.object(dev_lab, 'git', side_effect=git), mock.patch('builtins.print'):
            archive = dev_lab.pack(self.root)
        manifest = dev_lab.unpack(archive, self.root/'extracted')
        self.assertEqual(set(manifest['files']), set(included))
        for name in included:
            self.assertEqual((self.root/'extracted'/name).read_bytes(), name.encode())

    def test_optional_library_source_preserves_private_generated_and_path_guards(self):
        for name in ('libraries/x/../../outside.py', '/libraries/x/module.py',
                     'libraries\\x\\module.py', 'libraries/x/.git/config',
                     'libraries/x/.venv/lib/module.py', 'libraries/x/.env.local',
                     'libraries/x/secret.pem', 'libraries/x/.cache/value.json',
                     'libraries/x/coverage/index.html', 'libraries/x/dist-ssr/entry.js'):
            with self.subTest(name=name):
                self.assertFalse(dev_lab.source_path(name, with_libraries=True))

    def test_pack_refuses_symlink_escape(self):
        source = self.root / "repo"
        (source / "backend").mkdir(parents=True)
        outside = self.root / "secret"
        outside.write_text("private")
        try:
            (source / "backend/example.py").symlink_to(outside)
        except OSError:
            self.skipTest("Symlink creation is unavailable on this host")
        with mock.patch.object(dev_lab, "git", return_value=b"backend/example.py\0"):
            with self.assertRaises(ValueError):
                dev_lab.pack(source)

    def test_python_snapshot_stays_minimal_without_frontend_opt_in(self):
        names = ["backend/example.py", "frontend/package.json", "frontend/pnpm-lock.yaml",
                 "frontend/src/example.vue", "frontend/compiler/compile-ui-extension.mjs"]
        for name in names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"source")

        def git(_repo, *args):
            return b"a" * 40 if args[0] == "rev-parse" else b"\0".join(name.encode() for name in names)

        with mock.patch.object(dev_lab, "git", side_effect=git), mock.patch("builtins.print"):
            archive = dev_lab.pack(self.root)
        manifest = dev_lab.unpack(archive, self.root / "extracted")
        self.assertEqual(set(manifest["files"]), {
            "backend/example.py", "frontend/compiler/compile-ui-extension.mjs"})

    def test_opt_in_frontend_snapshot_preserves_manifests_locks_and_dirty_ui(self):
        names = ["frontend/package.json", "frontend/package-lock.json", "frontend/pnpm-lock.yaml",
                 "frontend/src/extension-ui/NewEditor.vue", "frontend/vite.config.ts",
                 "frontend/compiler/package.json", "modules/ui-reference/source/frontend/Reference.vue"]
        for index, name in enumerate(names):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"source {index}\r\n".encode())

        def git(_repo, *args):
            return b"a" * 40 if args[0] == "rev-parse" else b"\0".join(name.encode() for name in names)

        with mock.patch.object(dev_lab, "git", side_effect=git), mock.patch("builtins.print"):
            archive = dev_lab.pack(self.root, with_frontend=True)
        destination = self.root / "extracted"
        manifest = dev_lab.unpack(archive, destination)
        self.assertEqual(set(manifest["files"]), set(names))
        for name in names:
            self.assertEqual((destination / name).read_bytes(), (self.root / name).read_bytes())

    def test_frontend_opt_in_still_refuses_generated_private_and_unsafe_paths(self):
        for name in ("frontend/node_modules/reka-ui/package.json", "frontend/dist/index.html",
                     "frontend/dist-ssr/entry.js", "frontend/coverage/report.json",
                     "frontend/.vite/cache.json", "frontend/.cache/file.json",
                     "frontend/.env.production", "frontend/secret.pem", "frontend/data/live.db",
                     "frontend/../../outside.py", "frontend\\src\\example.vue"):
            with self.subTest(name=name):
                self.assertFalse(dev_lab.source_path(name, with_frontend=True))

    def test_verified_source_roundtrip_preserves_exact_bytes(self):
        content = b"# source\r\nprint('ok')\r\n"
        destination = self.root / "source"
        manifest = dev_lab.unpack(self.archive(content=content), destination)
        self.assertEqual((destination / "backend/example.py").read_bytes(), content)
        self.assertEqual(manifest["files"]["backend/example.py"], hashlib.sha256(content).hexdigest())

    def test_changed_bytes_are_rejected_before_any_extraction(self):
        destination = self.root / "source"
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            dev_lab.unpack(self.archive(stored=b"tampered"), destination)
        self.assertFalse(destination.exists())

    def test_traversal_link_and_unmanifested_members_are_refused(self):
        for name, kind in (("../escape.py", tarfile.REGTYPE),
                           ("backend/link.py", tarfile.SYMTYPE),
                           ("backend/unexpected.py", tarfile.REGTYPE)):
            with self.subTest(name=name):
                info = tarfile.TarInfo(name)
                info.type = kind
                info.linkname = "/etc/passwd" if kind == tarfile.SYMTYPE else ""
                destination = self.root / "source"
                with self.assertRaises(ValueError):
                    dev_lab.unpack(self.archive(extra=(info,)), destination)
                self.assertFalse(destination.exists())

    def test_duplicate_archive_member_is_refused(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            dev_lab.unpack(self.archive(duplicate=True), self.root / "source")

    def test_extraction_never_merges_into_an_existing_directory(self):
        destination = self.root / "source"
        destination.mkdir()
        marker = destination / "keep"
        marker.write_text("existing")
        with self.assertRaises(FileExistsError):
            dev_lab.unpack(self.archive(), destination)
        self.assertEqual(marker.read_text(), "existing")
        self.assertFalse((destination / "backend").exists())

    def test_environment_does_not_inherit_production_paths_or_credentials(self):
        with mock.patch.dict(dev_lab.os.environ, {
            "DATABASE_URL": "sqlite:////var/lib/3mm/live.db", "AI_SETTINGS_MASTER_KEY": "private",
            "PYTHONPATH": "/opt/3mm-dev", "THREE_MM_APPLICATION_ROOT": "/var/lib/3mm/apps",
        }):
            environment = dev_lab.lab_environment(self.root)
        self.assertNotIn("AI_SETTINGS_MASTER_KEY", environment)
        self.assertNotIn("THREE_MM_APPLICATION_ROOT", environment)
        self.assertNotIn("PYTHONPATH", environment)
        self.assertEqual(environment["THREE_MM_TEST_DATABASE_PATH"], str(self.root / "state/test.db"))
        self.assertNotIn("/var/lib/3mm", environment["DATABASE_URL"])
        self.assertEqual(environment["THREE_MM_CORE_AUTHORITY_SOCKET"], str(self.root / "authority.sock"))
        self.assertEqual(environment["THREE_MM_PLATFORM_RUNTIME_SOCKET"], str(self.root / "runtime.sock"))
        self.assertNotIn("THREE_MM_APPLICATION_PLATFORM_SOCKET", environment)

    def test_root_execution_is_refused_before_creating_a_lab(self):
        with mock.patch.object(dev_lab.sys, "platform", "linux"), \
                mock.patch.object(dev_lab.os, "geteuid", return_value=0, create=True), \
                mock.patch.object(dev_lab.tempfile, "mkdtemp") as create:
            with self.assertRaisesRegex(ValueError, "unprivileged"):
                dev_lab.run_lab(self.root / "source.tar", "p0")
        create.assert_not_called()

    def test_changed_cached_dependencies_are_refused_without_reinstall(self):
        source = self.root / "source"
        (source / "backend").mkdir(parents=True)
        for name in ("requirements.txt", "requirements-dev.txt"):
            (source / "backend" / name).write_bytes(b"pytest==8.4.1\n")
        requirements = b"pytest==8.4.1\n" * 2
        key = dev_lab.digest(requirements + dev_lab.sys.version.encode()
                             + dev_lab.platform.machine().encode())
        location = self.root / ".cache/3mm-dev-lab/envs" / key
        location.mkdir(parents=True)
        (location / "ready.json").write_text(json.dumps({
            "key": key, "freeze_sha256": dev_lab.digest(b"pytest==8.4.1\n"),
        }))
        with mock.patch.object(Path, "home", return_value=self.root), \
                mock.patch.object(dev_lab.subprocess, "check_output", return_value=b"pytest==9.0\n"), \
                mock.patch.object(dev_lab.subprocess, "run") as install:
            with self.assertRaisesRegex(ValueError, "environment changed"):
                dev_lab.environment(source, self.root, {}, fresh=False)
        install.assert_not_called()


if __name__ == "__main__":
    unittest.main()
