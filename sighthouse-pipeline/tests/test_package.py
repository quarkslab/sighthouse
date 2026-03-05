import io
import tarfile
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sighthouse.pipeline.package import PackageLoader


class TestPackageLoader(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for each test
        self.tmpdir = Path(tempfile.mkdtemp())
        # Mock logger
        from logging import basicConfig, Logger, DEBUG

        basicConfig(level=DEBUG)
        self.logger = Logger(__name__)  # MagicMock()

        # NOP default directory installation
        PackageLoader.DEFAULT_PACKAGE_PATH = None

        # Default paths include temp dir
        self.loader = PackageLoader(logger=self.logger, paths=[self.tmpdir])

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    # ---- __init__ tests ----

    def test_init_accepts_valid_paths(self):
        # Should not raise for list of Path/str
        loader = PackageLoader(
            logger=self.logger, paths=[self.tmpdir, str(self.tmpdir)]
        )
        self.assertIsNotNone(loader)

        # Reject invalid arguments
        with self.assertRaises(TypeError):
            PackageLoader(logger=self.logger, paths="not-a-list")

        # Reject invalid Path
        invalid = self.tmpdir / "does_not_exist"
        with self.assertRaises(ValueError):
            PackageLoader(logger=self.logger, paths=[invalid])

    # ---- load_metadata tests ----

    def _write_package_yml(self, dir_path: Path, content: str):
        (dir_path / "package.yml").write_text(content, encoding="utf-8")
        (dir_path / "__init__.py").write_text("print('Hello World')", encoding="utf-8")

    def test_load_metadata_returns_none_when_missing(self):
        pkg_dir = self.tmpdir / "pkg1"
        pkg_dir.mkdir()
        result = self.loader.load_metadata(pkg_dir)
        self.assertIsNone(result)

    def test_load_metadata_parses_valid_metadata(self):
        pkg_dir = self.tmpdir / "pkg2"
        pkg_dir.mkdir()
        # Adjust to format that your implementation expects (YAML keys, etc.)
        self._write_package_yml(pkg_dir, "name: testpkg\nversion: 1.2.3\n")
        result = self.loader.load_metadata(pkg_dir)
        self.assertIsNotNone(result)
        self.assertEqual(getattr(result, "name", None), "testpkg")
        self.assertEqual(getattr(result, "version", None), "1.2.3")

    def test_load_metadata_invalid_file_returns_none(self):
        pkg_dir = self.tmpdir / "pkg3"
        pkg_dir.mkdir()
        # Malformed YAML or missing required fields
        self._write_package_yml(pkg_dir, ":::: not yaml :::")
        result = self.loader.load_metadata(pkg_dir)
        self.assertIsNone(result)

    # ---- get_metadata tests ----

    def test_get_metadata_returns_previously_loaded(self):
        pkg_dir = self.tmpdir / "pkg4"
        pkg_dir.mkdir()
        self._write_package_yml(pkg_dir, "name: loadedpkg\nversion: 0.1.0\n")

        # Force a scan/load so the loader caches metadata
        meta = self.loader.load_metadata(pkg_dir)
        self.assertIsNotNone(meta)

        # Depending on your implementation, the key may be name or directory name
        result = self.loader.get_metadata("loadedpkg")
        self.assertEqual(result, meta)

    def test_get_metadata_unknown_name_returns_none(self):
        result = self.loader.get_metadata("nonexistent")
        self.assertIsNone(result)

    # ---- install tests ----

    def test_install_from_directory_success(self):
        source_dir = self.tmpdir / "source_pkg"
        source_dir.mkdir()
        self._write_package_yml(source_dir, "name: mypkgsrc\nversion: 1.0.0\n")

        success = self.loader.install(source_dir)
        self.assertTrue(success)

        installed_dir = self.tmpdir / "mypkgsrc"
        self.assertTrue(installed_dir.exists())

    def test_install_from_archive_success(self):
        source_dir = self.tmpdir / "archive_src"
        source_dir.mkdir()
        self._write_package_yml(source_dir, "name: archpkg\nversion: 2.0.0\n")

        archive_path = self.tmpdir / "archpkg.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tf:
            tf.add(source_dir, arcname="archpkg")

        success = self.loader.install(archive_path)
        self.assertTrue(success)

    def test_install_respects_overwrite_false(self):
        source_dir = self.tmpdir / "source_pkg2"
        source_dir.mkdir()
        self._write_package_yml(source_dir, "name: pkg2\nversion: 1.0.0\n")

        # First install
        self.assertTrue(self.loader.install(source_dir))
        # Second install without overwrite should fail or return False
        success = self.loader.install(source_dir, overwrite=False)
        self.assertFalse(success)

    def test_install_with_quick_check_invalid_metadata(self):
        source_dir = self.tmpdir / "bad_meta"
        source_dir.mkdir()
        self._write_package_yml(source_dir, ":::: bad ::::")
        success = self.loader.install(source_dir, quick_check=True)
        self.assertFalse(success)

    # ---- export_package tests ----

    def test_export_package_creates_tar_gz(self):
        # Simulate installed package layout
        pkg_dir = self.tmpdir / "pkg_to_export"
        pkg_dir.mkdir()
        self._write_package_yml(pkg_dir, "name: exportpkg\nversion: 1.0.0\n")

        # Many implementations resolve directories from name; if needed, stub that logic
        destination = self.tmpdir / "exportpkg.tar.gz"
        ok = self.loader.export_package("exportpkg", destination)
        self.assertTrue(ok)
        self.assertTrue(destination.exists())

        # Verify that it is a valid tar.gz
        with tarfile.open(destination, "r:gz") as tf:
            names = tf.getnames()
            self.assertTrue(any("package.yml" in n for n in names))

    def test_export_package_invalid_name_returns_false(self):
        destination = self.tmpdir / "missing.tar.gz"
        ok = self.loader.export_package("doesnotexist", destination)
        self.assertFalse(ok)
        self.assertFalse(destination.exists())

    # ---- run tests ----

    def test_run_calls_package_entrypoint(self):
        source_dir = self.tmpdir / "source_pkg"
        source_dir.mkdir()
        self._write_package_yml(source_dir, "name: pkgtorun\nversion: 1.0.0\n")

        success = self.loader.install(source_dir)
        self.assertTrue(success)

        result = self.loader.run("pkgtorun")
        self.assertTrue(result)

    def test_run_unknown_package_returns_false(self):
        result = self.loader.run("unknown_pkg")
        self.assertFalse(result)

    # ---- uninstall tests ----

    def test_uninstall_existing_package(self):
        pkg_dir = self.tmpdir / "toremove"
        pkg_dir.mkdir()
        self._write_package_yml(pkg_dir, "name: pkgtoremove\nversion: 0.0.1\n")
        self.assertTrue(self.loader.install(pkg_dir))

        ok = self.loader.uninstall("pkgtoremove")
        self.assertTrue(ok)
        # Directory should be gone
        self.assertFalse((self.tmpdir / "pkgtoremove").exists())

    def test_uninstall_nonexistent_package(self):
        ok = self.loader.uninstall("no_such")
        self.assertFalse(ok)

    # ---- list_modules tests ----

    def test_list_modules_returns_metadata_list(self):
        # Create two packages
        for name in ("pkgA", "pkgB"):
            d = self.tmpdir / name
            d.mkdir()
            self._write_package_yml(d, f"name: {name}\nversion: 1.0\n")
            self.loader.install(d)

        modules = self.loader.list_modules()
        self.assertIsInstance(modules, list)
        names = {getattr(m, "name", None) for m in modules}
        self.assertTrue({"pkgA", "pkgB"}.issubset(names))

    def test_list_modules_empty_when_no_packages(self):
        modules = self.loader.list_modules()
        self.assertEqual(modules, [])


if __name__ == "__main__":
    unittest.main()
