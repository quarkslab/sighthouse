import io
import json
import logging
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

from sighthouse.pipeline.manage import RepoCache, PipelineManager
from sighthouse.pipeline.worker import ExecutionStep, ExecutionChain, Job


def _job_dict(package: str, job_id: str = "job-1", **metadata) -> dict:
    """Build a serialized Job dict whose current step targets ``package``."""
    chain = ExecutionChain([ExecutionStep(package, {}, "1")], current_step="1")
    meta = {"id": job_id}
    meta.update(metadata)
    return Job(chain, meta).to_dict()


class FakeRepo:
    """Minimal in-memory stand-in for sighthouse.core.utils.repo.Repo."""

    def __init__(self, files=None):
        # Mapping of repo path -> bytes content
        self.files = dict(files or {})
        self.deleted = []

    def get_file(self, path: str):
        return self.files.get(path)

    def delete_file(self, path: str) -> None:
        self.deleted.append(path)
        self.files.pop(path, None)

    def list_directory(self, path: str):
        """Return the full paths of files living directly under ``path``."""
        prefix = path.rstrip("/")
        results = []
        for f in self.files:
            if prefix:
                if not f.startswith(prefix + "/"):
                    continue
                remainder = f[len(prefix) + 1 :]
            else:
                remainder = f
            # Only direct children (no nested directories)
            if "/" not in remainder:
                results.append(f)
        return results


class TestRepoCache(unittest.TestCase):
    def setUp(self):
        self.cache_dir = Path(tempfile.mkdtemp())
        self.logger = logging.getLogger("test_repocache")

    def tearDown(self):
        shutil.rmtree(self.cache_dir, ignore_errors=True)

    def _cache(self, repo):
        return RepoCache(repo, self.cache_dir, self.logger)

    def test_get_file_fetches_from_repo_and_populates_caches(self):
        repo = FakeRepo({"a/b.txt": b"hello"})
        cache = self._cache(repo)

        # First access is a cache miss -> fetched from repo and persisted.
        self.assertEqual(cache.get_file("a/b.txt"), b"hello")
        self.assertIn("a/b.txt", cache._memory_cache)
        self.assertTrue((self.cache_dir / "a" / "b.txt").exists())

    def test_get_file_uses_memory_cache_without_hitting_repo(self):
        repo = FakeRepo({"x.txt": b"data"})
        cache = self._cache(repo)
        cache.get_file("x.txt")  # warm the cache

        # Repo would now return something different; cache must shadow it.
        repo.files["x.txt"] = b"CHANGED"
        self.assertEqual(cache.get_file("x.txt"), b"data")

    def test_get_file_uses_disk_cache_when_memory_empty(self):
        repo = FakeRepo({"y.txt": b"persisted"})
        self._cache(repo).get_file("y.txt")  # write to disk

        # A brand-new cache instance repopulates from disk on construction.
        repo.files.clear()
        fresh = self._cache(repo)
        self.assertEqual(fresh.get_file("y.txt"), b"persisted")

    def test_get_file_missing_in_repo_raises(self):
        cache = self._cache(FakeRepo())
        with self.assertRaises(Exception):
            cache.get_file("nope.txt")

    def test_get_file_missing_evicts_stale_cache_entry(self):
        repo = FakeRepo({"gone.txt": b"old"})
        cache = self._cache(repo)
        cache.get_file("gone.txt")
        self.assertTrue((self.cache_dir / "gone.txt").exists())

        # File disappears from the repo: the next fetch must evict it. Drop the
        # memory and disk copies (but keep the bookkeeping entry) so the lookup
        # falls through to the repo and hits the eviction path.
        del repo.files["gone.txt"]
        cache._memory_cache.clear()
        (self.cache_dir / "gone.txt").unlink()
        self.assertIn("gone.txt", cache._cached_files)
        with self.assertRaises(Exception):
            cache.get_file("gone.txt")
        self.assertNotIn("gone.txt", cache._cached_files)
        self.assertFalse((self.cache_dir / "gone.txt").exists())

    def test_list_directory_caches_new_and_evicts_removed(self):
        repo = FakeRepo({"d/a.txt": b"A", "d/b.txt": b"B"})
        cache = self._cache(repo)

        listed = cache.list_directory("d/")
        self.assertEqual(set(listed), {"d/a.txt", "d/b.txt"})
        self.assertTrue((self.cache_dir / "d" / "a.txt").exists())
        self.assertTrue((self.cache_dir / "d" / "b.txt").exists())

        # Remove one file from the repo and re-list: cache must drop it.
        del repo.files["d/b.txt"]
        cache.list_directory("d/")
        self.assertFalse((self.cache_dir / "d" / "b.txt").exists())
        self.assertTrue((self.cache_dir / "d" / "a.txt").exists())

    def test_delete_file_removes_from_repo_and_cache(self):
        repo = FakeRepo({"del.txt": b"x"})
        cache = self._cache(repo)
        cache.get_file("del.txt")

        cache.delete_file("del.txt")
        self.assertIn("del.txt", repo.deleted)
        self.assertNotIn("del.txt", cache._memory_cache)
        self.assertFalse((self.cache_dir / "del.txt").exists())

    def test_clear_cache_empties_everything(self):
        repo = FakeRepo({"c.txt": b"x"})
        cache = self._cache(repo)
        cache.get_file("c.txt")

        cache.clear_cache()
        self.assertEqual(cache._memory_cache, {})
        self.assertEqual(cache._cached_files, set())

    def test_get_cache_stats_reports_counts_and_sizes(self):
        repo = FakeRepo({"f1.txt": b"abc", "f2.txt": b"defgh"})
        cache = self._cache(repo)
        cache.get_file("f1.txt")
        cache.get_file("f2.txt")

        stats = cache.get_cache_stats()
        self.assertEqual(stats["cached_files_count"], 2)
        self.assertEqual(stats["memory_cached_files_count"], 2)
        self.assertGreater(stats["disk_cache_size_mb"], 0)
        self.assertEqual(str(self.cache_dir), stats["cache_directory"])


def _make_manager():
    """Construct a PipelineManager with all external collaborators mocked out."""
    logger = logging.getLogger("test_pipelinemanager")
    with (
        patch("sighthouse.pipeline.manage.Repo"),
        patch("sighthouse.pipeline.manage.RepoCache"),
        patch("sighthouse.pipeline.manage.Celery"),
    ):
        manager = PipelineManager("redis://worker", "redis://repo", logger)
    manager._repo = MagicMock()
    manager._celery_app = MagicMock()
    return manager


class TestPipelineManagerStats(unittest.TestCase):
    def setUp(self):
        self.manager = _make_manager()

    def _wire_directories(self):
        def list_directory(path):
            return {
                "success/": ["success/WorkerA"],
                "success/WorkerA/": [
                    "success/WorkerA/j1.json",
                    "success/WorkerA/j2.json",
                ],
                "failed/": ["failed/WorkerA"],
                "failed/WorkerA/": ["failed/WorkerA/j3.json"],
            }.get(path, [])

        self.manager._repo.list_directory.side_effect = list_directory

    def test_stats_aggregates_success_failure_and_processing(self):
        self._wire_directories()
        self.manager._get_processing_jobs = MagicMock(
            return_value=[_job_dict("WorkerA")]
        )

        stats = self.manager.stats()
        self.assertEqual(
            stats["WorkerA"], {"success": 2, "failure": 1, "processing": 1}
        )

    def test_stats_state_filter_limits_to_success(self):
        self._wire_directories()
        self.manager._get_processing_jobs = MagicMock(return_value=[])

        stats = self.manager.stats(state="success")
        self.assertEqual(stats["WorkerA"]["success"], 2)
        self.assertEqual(stats["WorkerA"]["failure"], 0)

    def test_stats_package_filter_excludes_other_workers(self):
        def list_directory(path):
            return {
                "success/": ["success/WorkerA", "success/WorkerB"],
                "success/WorkerA/": ["success/WorkerA/j1.json"],
                "success/WorkerB/": ["success/WorkerB/j2.json"],
            }.get(path, [])

        self.manager._repo.list_directory.side_effect = list_directory
        self.manager._get_processing_jobs = MagicMock(return_value=[])

        stats = self.manager.stats(state="success", package="WorkerA")
        self.assertIn("WorkerA", stats)
        self.assertNotIn("WorkerB", stats)

    def test_stats_invalid_state_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.manager.stats(state="bogus")

    def test_stats_invalid_package_type_raises_type_error(self):
        with self.assertRaises(TypeError):
            self.manager.stats(package=123)


class TestPipelineManagerListJobs(unittest.TestCase):
    def setUp(self):
        self.manager = _make_manager()

    def test_list_jobs_invalid_state_raises(self):
        with self.assertRaises(ValueError):
            self.manager.list_jobs(state="bogus")

    def test_list_jobs_invalid_filter_type_raises(self):
        with self.assertRaises(TypeError):
            self.manager.list_jobs(filters=123)

    def test_list_jobs_prints_job_ids(self):
        def list_directory(path):
            return {
                "success/": ["success/WorkerA"],
                "success/WorkerA/": ["success/WorkerA/uuid-1.json"],
                "failed/": [],
            }.get(path, [])

        self.manager._repo.list_directory.side_effect = list_directory
        self.manager._get_processing_jobs = MagicMock(return_value=[])

        buf = io.StringIO()
        with redirect_stdout(buf):
            self.manager.list_jobs(state="success")
        self.assertIn("uuid-1", buf.getvalue())

    def test_list_jobs_filter_keeps_matching_jobs(self):
        def list_directory(path):
            return {
                "success/": [],
                "failed/": ["failed/WorkerA"],
                "failed/WorkerA/": [
                    "failed/WorkerA/a.json",
                    "failed/WorkerA/b.json",
                ],
            }.get(path, [])

        self.manager._repo.list_directory.side_effect = list_directory
        self.manager._get_processing_jobs = MagicMock(return_value=[])

        def get_file(path):
            data = {
                "failed/WorkerA/a.json": {"error": "build.ini missing"},
                "failed/WorkerA/b.json": {"error": "segfault"},
            }[path]
            return json.dumps(data).encode()

        self.manager._repo.get_file.side_effect = get_file

        buf = io.StringIO()
        with redirect_stdout(buf):
            self.manager.list_jobs(state="failed", filters="'.ini' in error")
        out = buf.getvalue()
        self.assertIn("a", out)
        self.assertNotIn("b.json", out)

    def test_list_jobs_group_by_reports_occurrences(self):
        def list_directory(path):
            return {
                "success/": [],
                "failed/": ["failed/WorkerA"],
                "failed/WorkerA/": [
                    "failed/WorkerA/a.json",
                    "failed/WorkerA/b.json",
                ],
            }.get(path, [])

        self.manager._repo.list_directory.side_effect = list_directory
        self.manager._get_processing_jobs = MagicMock(return_value=[])
        self.manager._repo.get_file.side_effect = lambda p: json.dumps(
            {"error": "same error"}
        ).encode()

        buf = io.StringIO()
        with redirect_stdout(buf):
            self.manager.list_jobs(state="failed", group_by="error")
        out = buf.getvalue()
        self.assertIn("#2", out)
        self.assertIn("same error", out)


class TestPipelineManagerRestart(unittest.TestCase):
    def setUp(self):
        self.manager = _make_manager()

    def _wire_repo(self):
        def list_directory(path):
            return {
                "success/": ["success/WorkerA"],
                "success/WorkerA/": ["success/WorkerA/uuid-1.json"],
                "failed/": ["failed/WorkerA"],
                "failed/WorkerA/": ["failed/WorkerA/uuid-2.json"],
            }.get(path, [])

        self.manager._repo.list_directory.side_effect = list_directory
        self.manager._repo.get_file.side_effect = lambda p: json.dumps(
            _job_dict("WorkerA", job_id="uuid-2", state="failed", error="boom")
        ).encode()

    def test_restart_invalid_type_raises(self):
        with self.assertRaises(TypeError):
            self.manager.restart_jobs("not-a-list")

    def test_restart_missing_job_raises(self):
        self._wire_repo()
        with self.assertRaises(Exception):
            self.manager.restart_jobs(["does-not-exist"])

    def test_restart_resends_failed_job_and_cleans_metadata(self):
        self._wire_repo()

        result = self.manager.restart_jobs(["uuid-2"])
        self.assertTrue(result)

        # Job file deleted from the repo before re-queueing.
        self.manager._repo.delete_file.assert_called_once_with(
            "failed/WorkerA/uuid-2.json"
        )

        # Re-queued onto the worker's queue, keeping the original UUID.
        self.manager._celery_app.send_task.assert_called_once()
        _, kwargs = self.manager._celery_app.send_task.call_args
        self.assertEqual(kwargs["queue"], "WorkerA")
        self.assertEqual(kwargs["task_id"], "uuid-2")
        # The transient state/error/id keys are stripped from the resent job.
        resent_meta = kwargs["kwargs"]["job_dict"]["job_metadata"]
        self.assertNotIn("state", resent_meta)
        self.assertNotIn("error", resent_meta)


class TestPipelineManagerWorkersAndStart(unittest.TestCase):
    def setUp(self):
        self.manager = _make_manager()

    def test_inspect_workers_shapes_per_worker_report(self):
        inspect = self.manager._celery_app.control.inspect.return_value
        inspect._request.return_value = {"node-1": {"id": "WorkerA"}}
        inspect.scheduled.return_value = {"node-1": ["s"]}
        inspect.active.return_value = {"node-1": ["a"]}
        inspect.reserved.return_value = {"node-1": ["r"]}

        report = self.manager.inspect_workers()
        self.assertEqual(
            report,
            {
                "workers": [
                    {
                        "WorkerA": {
                            "scheduled": ["s"],
                            "active": ["a"],
                            "reserved": ["r"],
                        }
                    }
                ]
            },
        )

    def test_get_processing_jobs_requires_redis_backend(self):
        # A backend without a `redis` attribute is unsupported.
        self.manager._celery_app.backend = object()
        with self.assertRaises(NotImplementedError):
            self.manager._get_processing_jobs()

    def _write_pipeline(self, tmpdir, package="WorkerA"):
        path = Path(tmpdir) / "pipeline.yml"
        path.write_text(
            "name: P\n"
            "description: d\n"
            "workers:\n"
            f"  - name: root\n    package: {package}\n",
            encoding="utf-8",
        )
        return path

    def test_start_pipeline_sends_root_task_when_workers_present(self):
        tmpdir = tempfile.mkdtemp()
        try:
            path = self._write_pipeline(tmpdir)
            inspect = self.manager._celery_app.control.inspect.return_value
            inspect._request.return_value = {"node-1": {"id": "WorkerA"}}

            self.manager.start_pipeline(path)
            self.manager._celery_app.send_task.assert_called_once()
            _, kwargs = self.manager._celery_app.send_task.call_args
            self.assertEqual(kwargs["queue"], "WorkerA")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_start_pipeline_raises_when_worker_missing(self):
        tmpdir = tempfile.mkdtemp()
        try:
            path = self._write_pipeline(tmpdir, package="WorkerA")
            inspect = self.manager._celery_app.control.inspect.return_value
            # No workers registered -> the required WorkerA is missing.
            inspect._request.return_value = {}

            with self.assertRaises(ValueError):
                self.manager.start_pipeline(path)
            self.manager._celery_app.send_task.assert_not_called()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
