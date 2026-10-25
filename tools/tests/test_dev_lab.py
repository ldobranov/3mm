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
