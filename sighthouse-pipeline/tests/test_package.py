import io
import tarfile
import shutil
import tempfile
import unittest
from pathlib import Path
from logging import Logger
from unittest.mock import MagicMock, patch

from sighthouse.pipeline.package import (
    PackageLoader,
    PackageMetadata,
    MonkeyPatchWorker,
)
from sighthouse.pipeline.worker import CommonWorker, ExecutionStep, ExecutionChain, Job


class TestPackageLoader(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for each test
        self.tmpdir = Path(tempfile.mkdtemp())
        # Separate directory standing in for the bundled core_modules/ dir
        self.coredir = Path(tempfile.mkdtemp())
        # Mock logger
        self.logger = Logger(__name__)

        # DEFAULT_PACKAGE_PATH and CORE_MODULES_PATH are *class* attributes;
        # save them so our overrides don't leak into other tests sharing the
        # same interpreter, then restore in tearDown.
        self._orig_default_path = PackageLoader.DEFAULT_PACKAGE_PATH
        self._orig_core_path = PackageLoader.CORE_MODULES_PATH
        # NOP default directory installation
        PackageLoader.DEFAULT_PACKAGE_PATH = None
        # Point the bundled-module lookup at an isolated temp dir
        PackageLoader.CORE_MODULES_PATH = self.coredir

        # Default paths include temp dir
        self.loader = PackageLoader(logger=self.logger, paths=[self.tmpdir])

    def tearDown(self):
        PackageLoader.DEFAULT_PACKAGE_PATH = self._orig_default_path
        PackageLoader.CORE_MODULES_PATH = self._orig_core_path
        shutil.rmtree(self.tmpdir)
        shutil.rmtree(self.coredir)

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

    def test_install_from_bundled_core_module_name(self):
        # A module shipped under CORE_MODULES_PATH can be installed by bare name
        bundled = self.coredir / "BundledWorker"
        bundled.mkdir()
        self._write_package_yml(bundled, "name: bundledworker\nversion: 1.0.0\n")

        meta = self.loader.install("BundledWorker")
        # install() returns the installed package's metadata
        self.assertIsNotNone(meta)
        self.assertEqual(meta.name, "bundledworker")
        self.assertTrue((self.tmpdir / "bundledworker").exists())

    # ---- resolve_source tests ----

    def test_resolve_source_returns_existing_path(self):
        pkg_dir = self.tmpdir / "somepkg"
        pkg_dir.mkdir()
        self.assertEqual(self.loader._resolve_source(pkg_dir), pkg_dir)

    def test_resolve_source_accepts_str_and_returns_path(self):
        pkg_dir = self.tmpdir / "somepkg2"
        pkg_dir.mkdir()
        result = self.loader._resolve_source(str(pkg_dir))
        self.assertIsInstance(result, Path)
        self.assertEqual(result, pkg_dir)

    def test_resolve_source_falls_back_to_bundled_core_module(self):
        (self.coredir / "FakeModule").mkdir()
        result = self.loader._resolve_source("FakeModule")
        self.assertEqual(result, self.coredir / "FakeModule")

    def test_resolve_source_uses_basename_for_bundled_lookup(self):
        # A non-existent path whose final component matches a bundled module
        # still resolves to the bundled module.
        (self.coredir / "FakeModule").mkdir()
        result = self.loader._resolve_source("does/not/exist/FakeModule")
        self.assertEqual(result, self.coredir / "FakeModule")

    def test_resolve_source_existing_path_takes_precedence_over_bundled(self):
        # A real filesystem path wins even if a bundled module shares its name.
        (self.coredir / "Collide").mkdir()
        real = self.tmpdir / "Collide"
        real.mkdir()
        self.assertEqual(self.loader._resolve_source(real), real)

    def test_resolve_source_unresolved_returns_original(self):
        missing = self.tmpdir / "definitely_missing"
        self.assertEqual(self.loader._resolve_source(missing), missing)

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

    # ---- install edge cases ----

    def test_install_nonexistent_source_returns_none(self):
        missing = self.tmpdir / "not_here"
        self.assertIsNone(self.loader.install(missing))

    def test_install_archive_with_invalid_structure_returns_none(self):
        # Archive with two top-level entries is rejected (expects exactly one
        # package folder).
        archive_path = self.tmpdir / "bad.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tf:
            for name in ("a", "b"):
                d = self.tmpdir / name
                d.mkdir()
                tf.add(d, arcname=name)
        self.assertIsNone(self.loader.install(archive_path))

    def test_install_aborts_when_requirement_install_fails(self):
        source_dir = self.tmpdir / "needs_reqs"
        source_dir.mkdir()
        self._write_package_yml(
            source_dir,
            "name: reqpkg\nversion: 1.0.0\nrequirements:\n  - some-dep\n",
        )

        # quick_check=False reaches the requirement-installation step.
        with patch.object(
            self.loader, "_install_package_requirement", return_value=False
        ) as mock_req:
            result = self.loader.install(source_dir, quick_check=False)
        self.assertIsNone(result)
        mock_req.assert_called_once_with("some-dep")
        self.assertFalse((self.tmpdir / "reqpkg").exists())

    def test_export_appends_tar_gz_extension(self):
        pkg_dir = self.tmpdir / "extpkg"
        pkg_dir.mkdir()
        self._write_package_yml(pkg_dir, "name: extpkg\nversion: 1.0.0\n")

        # Destination lacks the .tar.gz suffix; it should be added automatically.
        destination = self.tmpdir / "myexport"
        ok = self.loader.export_package("extpkg", destination)
        self.assertTrue(ok)
        self.assertTrue((self.tmpdir / "myexport.tar.gz").exists())

    def test_run_with_job_processes_single_job(self):
        # End-to-end: `run(..., job=...)` loads the package and processes one job.
        pkg_dir = self.tmpdir / "jobpkg_src"
        pkg_dir.mkdir()
        (pkg_dir / "package.yml").write_text(
            "name: jobpkg\nversion: 1.0.0\n", encoding="utf-8"
        )
        (pkg_dir / "__init__.py").write_text(
            "from sighthouse.pipeline.worker import Scrapper\n"
            "\n"
            "class JobWorker(Scrapper):\n"
            "    def do_work(self, job):\n"
            "        job.job_data['processed'] = True\n"
            "\n"
            "JobWorker('jobpkg', 'redis://localhost:6379').run()\n",
            encoding="utf-8",
        )
        self.assertTrue(self.loader.install(pkg_dir))

        chain = ExecutionChain([ExecutionStep("jobpkg", {}, "1")], current_step="1")
        job = Job(chain, {"id": "orig"})

        self.assertTrue(self.loader.run("jobpkg", job=job))
        # do_work ran against our job and the patched runner marked it successful.
        self.assertTrue(job.job_data.get("processed"))
        self.assertEqual(job.job_metadata.get("state"), "success")
        self.assertEqual(job.job_metadata.get("id"), "fakejob")


class TestPackageMetadata(unittest.TestCase):
    def test_equality_by_name_and_version(self):
        a = PackageMetadata(name="pkg", version="1.0.0")
        b = PackageMetadata(name="pkg", version="1.0.0")
        c = PackageMetadata(name="pkg", version="2.0.0")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_equality_with_other_type_raises(self):
        meta = PackageMetadata(name="pkg")
        with self.assertRaises(NotImplementedError):
            meta == "not a metadata object"

    def test_str_is_human_friendly(self):
        meta = PackageMetadata(name="pkg", version="1.2.3", author="Alice")
        self.assertEqual(str(meta), "pkg v1.2.3 by Alice")

    def test_repr_contains_key_fields(self):
        meta = PackageMetadata(
            name="pkg", version="1.2.3", author="Alice", requirements=["dep"]
        )
        text = repr(meta)
        self.assertIn("pkg", text)
        self.assertIn("1.2.3", text)
        self.assertIn("dep", text)

    def test_defaults(self):
        meta = PackageMetadata(name="pkg")
        self.assertEqual(meta.version, "1.0.0")
        self.assertEqual(meta.requirements, [])
        self.assertIsNone(meta.path)


class _RecordingWorker(CommonWorker):
    """A CommonWorker that skips Celery setup and records interactions."""

    def __init__(self):  # noqa: D401 - intentionally bypass base __init__
        self.worked_job = None
        self.success_result = None

    def _on_task_success(self, sender=None, result=None, **kwargs):
        self.success_result = result


class _SuccessWorker(_RecordingWorker):
    def do_work(self, job):
        self.worked_job = job


class _FailingWorker(_RecordingWorker):
    def do_work(self, job):
        raise RuntimeError("boom in do_work")


class TestMonkeyPatchWorker(unittest.TestCase):
    def setUp(self):
        self._orig_run = CommonWorker.run

    def tearDown(self):
        # The context manager should already have restored this; assert it did.
        self.assertIs(CommonWorker.run, self._orig_run)

    def _job(self):
        chain = ExecutionChain([ExecutionStep("p", {}, "1")], current_step="1")
        return Job(chain, {"id": "orig"})

    def test_successful_run_marks_state_and_invokes_callback(self):
        worker = _SuccessWorker()
        job = self._job()
        with MonkeyPatchWorker(job):
            worker.run()  # patched to process the single job

        self.assertIs(worker.worked_job, job)
        self.assertEqual(job.job_metadata["state"], "success")
        self.assertEqual(job.job_metadata["id"], "fakejob")
        self.assertEqual(worker.success_result, job.to_dict())

    def test_failing_run_records_error_state(self):
        worker = _FailingWorker()
        job = self._job()
        with MonkeyPatchWorker(job):
            worker.run()

        self.assertEqual(job.job_metadata["state"], "failed")
        self.assertIn("boom in do_work", job.job_metadata["error"])

    def test_no_job_leaves_run_untouched(self):
        with MonkeyPatchWorker(None):
            # With no job, the runner is not patched at all.
            self.assertIs(CommonWorker.run, self._orig_run)


if __name__ == "__main__":
    unittest.main()
