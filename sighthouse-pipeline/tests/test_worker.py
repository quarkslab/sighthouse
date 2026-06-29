from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import yaml

from sighthouse.pipeline.worker import (
    ExecutionStep,
    ExecutionChain,
    Job,
    CommonWorker,
    Compiler,
    _healthcheck_path,
)
from sighthouse.pipeline.parser import WorkerConfig, PipelineConfig


class TestExecutionStep(unittest.TestCase):

    def test_init_and_attributes(self):
        step = ExecutionStep(package="mypkg.tasks", args={"x": 1}, step="1.1")
        self.assertEqual(step.package, "mypkg.tasks")
        self.assertEqual(step.args, {"x": 1})
        self.assertEqual(step.step, "1.1")

    def test_to_dict(self):
        step = ExecutionStep(package="mypkg.tasks", args={"x": 1}, step="1.1")
        self.assertEqual(
            step.to_dict(),
            {"package": "mypkg.tasks", "args": {"x": 1}, "step": "1.1"},
        )


class TestExecutionChain(unittest.TestCase):
    def setUp(self):
        self.steps = [
            ExecutionStep("pkg", {"a": 1}, "1"),
            ExecutionStep("pkg", {"b": 2}, "2"),
            ExecutionStep("pkg", {"b1": 3}, "2.1"),
            ExecutionStep("pkg", {"c": 4}, "3"),
        ]
        self.chain = ExecutionChain(execution_steps=self.steps, current_step="1")

    def test_default_current_step(self):
        chain = ExecutionChain(execution_steps=self.steps)
        self.assertEqual(chain.current_step, ExecutionChain.DEFAULT_STEP)

    def test_from_dict_and_to_dict_roundtrip(self):
        data = {
            "execution_steps": [
                {"package": "pkg", "args": {"a": 1}, "step": "1"},
                {"package": "pkg", "args": {"b": 2}, "step": "2"},
            ],
            "current_step": "2",
        }
        chain = ExecutionChain.from_dict(data)
        self.assertEqual(chain.current_step, "2")
        self.assertEqual(len(chain.execution_steps), 2)
        self.assertEqual(chain.to_dict(), data)

    def test_get_step_found(self):
        s = self.chain.get_step("2.1")
        self.assertIsNotNone(s)
        self.assertEqual(s.args, {"b1": 3})

    def test_get_step_not_found(self):
        self.assertIsNone(self.chain.get_step("99"))

    def test_worker_args_for_current_step(self):
        self.chain.current_step = "2"
        self.assertEqual(self.chain.worker_args, {"b": 2})

    def test_worker_args_for_missing_step(self):
        self.chain.current_step = "99"
        self.assertEqual(self.chain.worker_args, {})

    def test_package_for_current_step(self):
        self.chain.current_step = "3"
        self.assertEqual(self.chain.package, "pkg")

    def test_package_for_missing_step(self):
        self.chain.current_step = "99"
        self.assertIsNone(self.chain.package)

    def test_get_next_worker_args_simple(self):
        self.chain.current_step = "1"
        next_args = self.chain.get_next_worker_args()
        self.assertEqual(len(next_args), 2)
        labels = {label for label, _ in next_args}
        self.assertEqual(labels, {"2", "2.1"})

    def test_get_next_worker_args_at_last_main(self):
        self.chain.current_step = "3"
        self.assertEqual(self.chain.get_next_worker_args(), [])

    def test_get_next_worker_args_invalid_current(self):
        self.chain.current_step = "abc"
        self.assertEqual(self.chain.get_next_worker_args(), [])

    def test_advance_to_next_step_moves_current_and_returns_substeps(self):
        self.chain.current_step = "1"
        next_steps = self.chain.advance_to_next_step()
        self.assertIsNotNone(next_steps)
        self.assertEqual({s.step for s in next_steps}, {"2", "2.1"})
        self.assertEqual(self.chain.current_step, "2")

    def test_advance_to_next_step_at_end_returns_none(self):
        self.chain.current_step = "3"
        self.assertIsNone(self.chain.advance_to_next_step())

    def test_advance_to_next_step_skips_invalid_labels(self):
        bad_steps = [
            ExecutionStep("pkg", {"x": 1}, "1"),
            ExecutionStep("pkg", {"y": 2}, "bad"),
            ExecutionStep("pkg", {"z": 3}, "2.1"),
        ]
        chain = ExecutionChain(execution_steps=bad_steps, current_step="1")
        next_steps = chain.advance_to_next_step()
        self.assertIsNotNone(next_steps)
        self.assertEqual({s.step for s in next_steps}, {"2.1"})
        self.assertEqual(chain.current_step, "2.1")


class TestJob(unittest.TestCase):
    def setUp(self):
        steps = [
            ExecutionStep("pkg1", {"a": 1}, "1"),
            ExecutionStep("pkg2", {"b": 2}, "2"),
        ]
        chain = ExecutionChain(execution_steps=steps, current_step="1")
        self.metadata = {"id": "job-1"}
        self.job = Job(execution_chain=chain, job_metadata=self.metadata)

    def test_worker_args_delegation(self):
        self.assertEqual(self.job.worker_args, {"a": 1})
        self.job.execution_chain.current_step = "2"
        self.assertEqual(self.job.worker_args, {"b": 2})

    def test_package_delegation(self):
        self.assertEqual(self.job.package, "pkg1")
        self.job.execution_chain.current_step = "2"
        self.assertEqual(self.job.package, "pkg2")

    def test_get_next_worker_args_delegation(self):
        args = self.job.get_next_worker_args()
        self.assertEqual(len(args), 1)
        self.assertEqual(args[0][0], "2")
        self.assertEqual(args[0][1], {"b": 2})


class TestWorkerConfig(unittest.TestCase):
    def test_from_dict_minimal_valid(self):
        data = {"name": "A", "package": "pkg1"}
        wc = WorkerConfig.from_dict(data)
        self.assertIsInstance(wc, WorkerConfig)
        self.assertEqual(wc.name, "A")
        self.assertEqual(wc.package, "pkg1")
        self.assertEqual(wc.args, {})
        self.assertIsNone(wc.target)
        self.assertIsNone(wc.foreach)

    def test_from_dict_full_valid(self):
        data = {
            "name": "B",
            "package": "pkg2",
            "target": "C",
            "args": {"x": 1},
            "foreach": [1, 2, 3],
        }
        wc = WorkerConfig.from_dict(data)
        self.assertEqual(wc.name, "B")
        self.assertEqual(wc.package, "pkg2")
        self.assertEqual(wc.target, "C")
        self.assertEqual(wc.args, {"x": 1})
        self.assertEqual(wc.foreach, [1, 2, 3])

    def test_from_dict_missing_mandatory_key_raises(self):
        data = {"name": "A"}  # missing package
        with self.assertRaises(ValueError):
            WorkerConfig.from_dict(data)

    def test_from_dict_unknown_key_raises(self):
        data = {"name": "A", "package": "pkg1", "unknown": 42}
        with self.assertRaises(ValueError):
            WorkerConfig.from_dict(data)

    def test_to_dict_matches_input(self):
        data = {
            "name": "B",
            "package": "pkg2",
            "target": "C",
            "args": {"k": "v"},
            "foreach": ["x"],
        }
        wc = WorkerConfig.from_dict(data)
        out = wc.to_dict()
        self.assertEqual(out["name"], "B")
        self.assertEqual(out["package"], "pkg2")
        self.assertEqual(out["target"], "C")
        self.assertEqual(out["args"], {"k": "v"})
        self.assertEqual(out["foreach"], ["x"])

    def test_to_dict_omits_none_fields_if_desired(self):
        # Depending on your implementation, you may or may not omit None fields.
        wc = WorkerConfig.from_dict({"name": "A", "package": "pkg1"})
        out = wc.to_dict()
        self.assertEqual(out["name"], "A")
        self.assertEqual(out["package"], "pkg1")
        # Adjust these asserts if you always include keys with None.
        self.assertNotIn("target", out)
        self.assertNotIn("foreach", out)


class TestPipelineConfigLoadAndGraph(unittest.TestCase):
    def _write_yaml_tempfile(self, content: str) -> Path:
        fd, path_str = tempfile.mkstemp(suffix=".yaml")
        path = Path(path_str)
        path.write_text(content, encoding="utf-8")
        return path

    def test_load_valid_yaml_file(self):
        yaml_content = """
name: My pipeline
description: A great pipeline
workers:
  - name: A
    package: pkg1
    target: B
  - name: B
    package: pkg2
    args:
      my-args: "aaaa"
"""
        path = self._write_yaml_tempfile(yaml_content)
        try:
            cfg = PipelineConfig.load(path)
            self.assertIsInstance(cfg, PipelineConfig)
            self.assertEqual(cfg.name, "My pipeline")
            self.assertEqual(cfg.description, "A great pipeline")
            self.assertEqual(len(cfg.workers), 2)
            names = {w.name for w in cfg.workers}
            self.assertEqual(names, {"A", "B"})
        finally:
            path.unlink(missing_ok=True)

    def test_load_nonexistent_file_raises(self):
        path = Path("nonexistent_pipeline.yaml")
        with self.assertRaises(FileNotFoundError):
            PipelineConfig.load(path)

    def test_load_invalid_yaml_raises(self):
        # invalid YAML syntax
        yaml_content = "name: [unclosed\n"
        path = self._write_yaml_tempfile(yaml_content)
        try:
            with self.assertRaises(yaml.YAMLError):
                PipelineConfig.load(path)
        finally:
            path.unlink(missing_ok=True)

    def test_init_invalid_graph_missing_target_raises(self):
        # Worker A targets "C" which does not exist
        workers = [
            WorkerConfig.from_dict({"name": "A", "package": "pkg1", "target": "C"}),
            WorkerConfig.from_dict({"name": "B", "package": "pkg2"}),
        ]
        with self.assertRaises(ValueError):
            PipelineConfig(name="Bad", description="Missing target", workers=workers)

    def test_roots_detected_correctly(self):
        # A -> B, C is standalone
        workers = [
            WorkerConfig.from_dict({"name": "A", "package": "pkg1", "target": "B"}),
            WorkerConfig.from_dict({"name": "B", "package": "pkg2"}),
            WorkerConfig.from_dict({"name": "C", "package": "pkg3"}),
        ]
        cfg = PipelineConfig(name="P", description="desc", workers=workers)
        roots = cfg.roots
        root_names = {w.name for w in roots}
        # B has incoming edge from A, so roots should be A and C
        self.assertEqual(root_names, {"A", "C"})

    def test_to_dict_roundtrip(self):
        workers = [
            WorkerConfig.from_dict({"name": "A", "package": "pkg1", "target": "B"}),
            WorkerConfig.from_dict(
                {"name": "B", "package": "pkg2", "args": {"my-args": "aaaa"}}
            ),
        ]
        cfg = PipelineConfig(
            name="My pipeline", description="A great pipeline", workers=workers
        )
        d = cfg.to_dict()
        self.assertEqual(d["name"], "My pipeline")
        self.assertEqual(d["description"], "A great pipeline")
        self.assertEqual(len(d["workers"]), 2)
        self.assertEqual(d["workers"][0]["name"], "A")
        self.assertEqual(d["workers"][1]["args"]["my-args"], "aaaa")


class TestPipelineConfigExecutionChain(unittest.TestCase):
    def setUp(self):
        # Simple linear pipeline A -> B -> C
        self.workers_linear = [
            WorkerConfig.from_dict({"name": "A", "package": "pkg1", "target": "B"}),
            WorkerConfig.from_dict({"name": "B", "package": "pkg2", "target": "C"}),
            WorkerConfig.from_dict({"name": "C", "package": "pkg3"}),
        ]
        self.cfg_linear = PipelineConfig(
            name="Linear", description="A -> B -> C", workers=self.workers_linear
        )

    def test_create_execution_chain_from_root_linear(self):
        chain = self.cfg_linear.create_execution_chain("A")
        self.assertIsInstance(chain, ExecutionChain)
        steps = chain.execution_steps
        self.assertEqual(len(steps), 3)
        self.assertEqual([s.package for s in steps], ["pkg1", "pkg2", "pkg3"])
        self.assertEqual([s.step for s in steps], ["1", "2", "3"])

    def test_create_execution_chain_unknown_root_raises(self):
        with self.assertRaises(ValueError):
            self.cfg_linear.create_execution_chain("Unknown")

    def test_create_execution_chain_cycle_raises(self):
        # A -> B, B -> A (cycle)
        workers_cycle = [
            WorkerConfig.from_dict({"name": "A", "package": "pkg1", "target": "B"}),
            WorkerConfig.from_dict({"name": "B", "package": "pkg2", "target": "A"}),
        ]
        cfg_cycle = PipelineConfig(
            name="Cycle", description="A <-> B", workers=workers_cycle
        )
        with self.assertRaises(ValueError):
            cfg_cycle.create_execution_chain("A")

    def test_create_execution_chain_fans_out_foreach(self):
        # A worker with `foreach` expands into numbered substeps (1.1, 1.2, ...).
        workers = [
            WorkerConfig.from_dict(
                {
                    "name": "A",
                    "package": "pkg1",
                    "foreach": [{"x": 1}, {"x": 2}],
                    "target": "B",
                }
            ),
            WorkerConfig.from_dict({"name": "B", "package": "pkg2"}),
        ]
        cfg = PipelineConfig(name="Fan", description="fanout", workers=workers)
        chain = cfg.create_execution_chain("A")

        steps = {s.step: s for s in chain.execution_steps}
        self.assertIn("1.1", steps)
        self.assertIn("1.2", steps)
        self.assertEqual(steps["1.1"].args, {"x": 1})
        self.assertEqual(steps["1.2"].args, {"x": 2})
        # The downstream worker keeps a plain numbered step.
        self.assertIn("2", steps)


class TestWorkerConfigValidation(unittest.TestCase):
    def test_empty_mandatory_string_raises(self):
        with self.assertRaises(ValueError):
            WorkerConfig.from_dict({"name": "  ", "package": "pkg1"})

    def test_target_must_be_non_empty_string(self):
        with self.assertRaises(ValueError):
            WorkerConfig.from_dict({"name": "A", "package": "pkg1", "target": ""})

    def test_foreach_must_be_non_empty_list(self):
        with self.assertRaises(ValueError):
            WorkerConfig.from_dict({"name": "A", "package": "pkg1", "foreach": []})

    def test_repr_returns_string(self):
        wc = WorkerConfig.from_dict({"name": "A", "package": "pkg1"})
        self.assertIsInstance(repr(wc), str)


class TestPipelineConfigValidation(unittest.TestCase):
    def _write_yaml(self, content):
        fd, path_str = tempfile.mkstemp(suffix=".yaml")
        path = Path(path_str)
        path.write_text(content, encoding="utf-8")
        return path

    def test_root_not_a_mapping_raises(self):
        path = self._write_yaml("- just\n- a\n- list\n")
        try:
            with self.assertRaises(ValueError):
                PipelineConfig.load(path)
        finally:
            path.unlink(missing_ok=True)

    def test_invalid_top_level_key_raises(self):
        path = self._write_yaml(
            "name: P\nbogus: 1\nworkers:\n  - name: A\n    package: pkg1\n"
        )
        try:
            with self.assertRaises(ValueError):
                PipelineConfig.load(path)
        finally:
            path.unlink(missing_ok=True)

    def test_no_workers_raises(self):
        path = self._write_yaml("name: P\ndescription: d\nworkers: []\n")
        try:
            with self.assertRaises(ValueError):
                PipelineConfig.load(path)
        finally:
            path.unlink(missing_ok=True)

    def test_duplicate_worker_names_raises(self):
        path = self._write_yaml(
            "name: P\nworkers:\n"
            "  - name: A\n    package: pkg1\n"
            "  - name: A\n    package: pkg2\n"
        )
        try:
            with self.assertRaises(ValueError):
                PipelineConfig.load(path)
        finally:
            path.unlink(missing_ok=True)

    def test_self_reference_raises(self):
        workers = [
            WorkerConfig.from_dict({"name": "A", "package": "pkg1", "target": "A"})
        ]
        with self.assertRaises(ValueError):
            PipelineConfig(name="P", description="d", workers=workers)

    def test_repr_reports_worker_count(self):
        workers = [
            WorkerConfig.from_dict({"name": "A", "package": "pkg1"}),
            WorkerConfig.from_dict({"name": "B", "package": "pkg2"}),
        ]
        cfg = PipelineConfig(name="P", description="d", workers=workers)
        self.assertIn("2", repr(cfg))


class TestExecutionStepRepr(unittest.TestCase):
    def test_repr_contains_fields(self):
        step = ExecutionStep("pkg", {"x": 1}, "2.1")
        text = repr(step)
        self.assertIn("pkg", text)
        self.assertIn("2.1", text)
        self.assertIn("x", text)


class TestJobSerialization(unittest.TestCase):
    def test_from_dict_to_dict_roundtrip(self):
        data = {
            "execution_chain": {
                "execution_steps": [{"package": "p", "args": {"a": 1}, "step": "1"}],
                "current_step": "1",
            },
            "job_data": {"file": "x.tar.gz"},
            "job_metadata": {"id": "j1", "state": "success"},
        }
        job = Job.from_dict(data)
        self.assertEqual(job.to_dict(), data)

    def test_repr_summarizes_metadata(self):
        chain = ExecutionChain([ExecutionStep("p", {}, "1")], current_step="1")
        job = Job(chain, {"id": "j1", "state": "failed", "from": "j0"})
        text = repr(job)
        self.assertIn("j1", text)
        self.assertIn("failed", text)


def _make_worker(with_repo=True):
    """Construct a CommonWorker with Celery and Repo replaced by mocks."""
    with (
        patch("sighthouse.pipeline.worker.CeleryWorker") as MockCelery,
        patch("sighthouse.pipeline.worker.Repo") as MockRepo,
    ):
        celery = MagicMock()
        celery.worker_metadata = {"id": "WorkerA"}
        MockCelery.return_value = celery
        repo = MagicMock()
        MockRepo.return_value = repo
        worker = CommonWorker(
            "WorkerA",
            "redis://broker",
            repo_url="local:///tmp/repo" if with_repo else None,
        )
    return worker, celery, (repo if with_repo else None)


class TestCommonWorkerRepoWrappers(unittest.TestCase):
    """The repo wrapper methods prefix paths with 'artifacts/' and degrade
    gracefully when the worker has no repository."""

    def test_push_file_prefixes_artifacts(self):
        worker, _celery, repo = _make_worker(with_repo=True)
        repo.push_file.return_value = True
        self.assertTrue(worker.push_file("out/result.bin", b"data"))
        repo.push_file.assert_called_once_with("artifacts/out/result.bin", b"data")

    def test_push_file_without_repo_returns_false(self):
        worker, _celery, _ = _make_worker(with_repo=False)
        self.assertFalse(worker.push_file("x", b"data"))

    def test_get_file_prefixes_artifacts(self):
        worker, _celery, repo = _make_worker(with_repo=True)
        repo.get_file.return_value = b"content"
        self.assertEqual(worker.get_file("a.txt"), b"content")
        repo.get_file.assert_called_once_with("artifacts/a.txt")

    def test_get_file_without_repo_returns_empty(self):
        worker, _celery, _ = _make_worker(with_repo=False)
        self.assertEqual(worker.get_file("a.txt"), b"")

    def test_delete_file_prefixes_artifacts(self):
        worker, _celery, repo = _make_worker(with_repo=True)
        worker.delete_file("a.txt")
        repo.delete_file.assert_called_once_with("artifacts/a.txt")

    def test_get_sharefile_without_repo_returns_empty(self):
        worker, _celery, _ = _make_worker(with_repo=False)
        self.assertEqual(worker.get_sharefile("a.txt"), "")


class TestCommonWorkerSendTask(unittest.TestCase):
    def _job(self):
        steps = [
            ExecutionStep("pkg1", {"a": 1}, "1"),
            ExecutionStep("pkg2", {"b": 2}, "2"),
        ]
        chain = ExecutionChain(steps, current_step="1")
        return Job(chain, {"id": "j1"})

    def test_send_task_advances_to_next_step_and_queues(self):
        worker, celery, _ = _make_worker(with_repo=False)
        job = self._job()

        worker.send_task(job)

        celery.send_task.assert_called_once()
        args, kwargs = celery.send_task.call_args
        self.assertEqual(args[0], "do_work")
        # The next step targets pkg2's queue.
        self.assertEqual(kwargs["queue"], "pkg2")
        sent = kwargs["kwargs"]["job_dict"]
        self.assertEqual(sent["execution_chain"]["current_step"], "2")
        # A fresh UUID is assigned and used as the task id.
        self.assertEqual(kwargs["task_id"], sent["job_metadata"]["id"])

    def test_send_task_explicit_step(self):
        worker, celery, _ = _make_worker(with_repo=False)
        job = self._job()

        worker.send_task(job, step="2")
        _, kwargs = celery.send_task.call_args
        self.assertEqual(kwargs["queue"], "pkg2")

    def test_send_task_invalid_step_raises(self):
        worker, _celery, _ = _make_worker(with_repo=False)
        with self.assertRaises(ValueError):
            worker.send_task(self._job(), step="99")

    def test_send_task_propagates_next_from(self):
        worker, celery, _ = _make_worker(with_repo=False)
        job = self._job()
        job._next_from = "previous-id"

        worker.send_task(job)
        _, kwargs = celery.send_task.call_args
        self.assertEqual(
            kwargs["kwargs"]["job_dict"]["job_metadata"]["from"], "previous-id"
        )


class TestCommonWorkerSignals(unittest.TestCase):
    def test_on_task_success_uploads_result_to_state_path(self):
        worker, _celery, repo = _make_worker(with_repo=True)
        repo.push_file.return_value = True

        chain = ExecutionChain([ExecutionStep("pkg1", {}, "1")], current_step="1")
        result = Job(chain, {"id": "job-42", "state": "success"}).to_dict()
        sender = type("FakeSender", (object,), {"name": "do_work"})()

        worker._on_task_success(sender=sender, result=result)

        repo.push_file.assert_called_once()
        path, content = repo.push_file.call_args[0]
        self.assertEqual(path, "success/WorkerA/job-42.json")
        # The uploaded content is the JSON-serialized result.
        self.assertEqual(json.loads(content.decode()), result)

    def test_on_task_failure_uploads_failed_job(self):
        worker, _celery, repo = _make_worker(with_repo=True)
        repo.push_file.return_value = True

        chain = ExecutionChain([ExecutionStep("pkg1", {}, "1")], current_step="1")
        job_dict = Job(chain, {"id": "job-99"}).to_dict()
        sender = type("FakeSender", (object,), {"name": "do_work"})()

        worker._on_task_failure(
            sender=sender,
            args=[job_dict],
            exception=RuntimeError("kaboom"),
            einfo="trace",
        )

        repo.push_file.assert_called_once()
        path, content = repo.push_file.call_args[0]
        self.assertEqual(path, "failed/WorkerA/job-99.json")
        # The failed job is serialized to JSON (regression: the Job object must
        # be converted to a dict first, otherwise json.dumps would crash).
        self.assertEqual(json.loads(content.decode()), job_dict)

    def test_on_task_failure_without_args_does_not_upload(self):
        worker, _celery, repo = _make_worker(with_repo=True)
        sender = type("FakeSender", (object,), {"name": "do_work"})()

        worker._on_task_failure(sender=sender, args=None, exception=RuntimeError("x"))
        repo.push_file.assert_not_called()


class TestCommonWorkerPackAndSend(unittest.TestCase):
    def _job(self):
        steps = [
            ExecutionStep("pkg1", {}, "1"),
            ExecutionStep("pkg2", {}, "2"),
        ]
        return Job(ExecutionChain(steps, current_step="1"), {"id": "j1"})

    def test_empty_files_is_a_noop(self):
        worker, celery, _ = _make_worker(with_repo=False)
        worker.pack_and_send_task(self._job(), [])
        celery.send_task.assert_not_called()

    def test_packs_uploads_and_forwards(self):
        worker, celery, repo = _make_worker(with_repo=True)
        repo.push_file.return_value = True
        job = self._job()

        fake_tar = MagicMock()
        fake_tar.read.return_value = b"tar-bytes"
        with (
            patch(
                "sighthouse.pipeline.worker.get_minimal_paths",
                return_value=(".", ["a.bin"]),
            ),
            patch("sighthouse.pipeline.worker.create_tar", return_value=fake_tar),
            patch("sighthouse.pipeline.worker.get_hash", return_value="deadbeef"),
        ):
            worker.pack_and_send_task(job, ["a.bin"])

        # Archive uploaded under a hash-derived name and recorded on the job.
        repo.push_file.assert_called_once_with(
            "artifacts/deadbeef.tar.gz", b"tar-bytes"
        )
        self.assertEqual(job.job_data["file"], "deadbeef.tar.gz")
        # Job forwarded to the next worker in the chain.
        celery.send_task.assert_called_once()

    def test_raises_when_upload_fails(self):
        worker, _celery, repo = _make_worker(with_repo=True)
        repo.push_file.return_value = False

        fake_tar = MagicMock()
        fake_tar.read.return_value = b"tar"
        with (
            patch(
                "sighthouse.pipeline.worker.get_minimal_paths",
                return_value=(".", ["a.bin"]),
            ),
            patch("sighthouse.pipeline.worker.create_tar", return_value=fake_tar),
            patch("sighthouse.pipeline.worker.get_hash", return_value="h"),
        ):
            with self.assertRaises(Exception):
                worker.pack_and_send_task(self._job(), ["a.bin"])


class TestHealthcheckPath(unittest.TestCase):
    def test_sanitizes_spaces_and_includes_pid(self):
        import os

        path = _healthcheck_path("My Worker")
        self.assertIn("My_Worker", str(path))
        self.assertIn(str(os.getpid()), str(path))
        self.assertTrue(str(path).endswith(".ready"))


class TestCompilerVariants(unittest.TestCase):
    def test_valid_variants_returned_as_pairs(self):
        data = {
            "compiler_variants": {
                "gcc-arm": {"cc": "arm-gcc", "cflags": "-O2"},
                "clang": {"cc": "clang", "cflags": "-O0"},
            }
        }
        result = Compiler.validate_compiler_variants(data)
        self.assertEqual(len(result), 2)
        names = {name for name, _ in result}
        self.assertEqual(names, {"gcc-arm", "clang"})

    def test_missing_top_level_key_raises(self):
        with self.assertRaises(ValueError):
            Compiler.validate_compiler_variants({"something_else": {}})

    def test_compiler_variants_not_a_dict_raises(self):
        with self.assertRaises(ValueError):
            Compiler.validate_compiler_variants({"compiler_variants": ["not", "dict"]})

    def test_variant_not_a_dict_raises(self):
        with self.assertRaises(ValueError):
            Compiler.validate_compiler_variants(
                {"compiler_variants": {"v1": "not-a-dict"}}
            )

    def test_missing_required_fields_raises(self):
        with self.assertRaises(ValueError):
            Compiler.validate_compiler_variants(
                {"compiler_variants": {"v1": {"cc": "gcc"}}}  # no cflags
            )

    def test_non_string_field_value_raises(self):
        with self.assertRaises(ValueError):
            Compiler.validate_compiler_variants(
                {"compiler_variants": {"v1": {"cc": "gcc", "cflags": 123}}}
            )

    def test_pack_and_send_task_injects_metadata(self):
        # Build a Compiler with Celery/Repo mocked out.
        with (
            patch("sighthouse.pipeline.worker.CeleryWorker") as MockCelery,
            patch("sighthouse.pipeline.worker.Repo") as MockRepo,
        ):
            celery = MagicMock()
            celery.worker_metadata = {"id": "WorkerA"}
            MockCelery.return_value = celery
            repo = MagicMock()
            repo.push_file.return_value = True
            MockRepo.return_value = repo
            compiler = Compiler("WorkerA", "redis://b", repo_url="local:///tmp/repo")

        steps = [ExecutionStep("pkg1", {}, "1"), ExecutionStep("pkg2", {}, "2")]
        job = Job(ExecutionChain(steps, current_step="1"), {"id": "j1"})
        metadata = [("gcc-arm", "arm-gcc")]

        fake_tar = MagicMock()
        fake_tar.read.return_value = b"tar"
        with (
            patch(
                "sighthouse.pipeline.worker.get_minimal_paths",
                return_value=(".", ["a.bin"]),
            ),
            patch("sighthouse.pipeline.worker.create_tar", return_value=fake_tar),
            patch("sighthouse.pipeline.worker.get_hash", return_value="h"),
        ):
            compiler.pack_and_send_task(job, ["a.bin"], metadata)

        # The compiler variants metadata is attached to the job before sending.
        self.assertEqual(job.job_data["metadata"], metadata)
        celery.send_task.assert_called_once()


if __name__ == "__main__":
    unittest.main()
