from pathlib import Path
import tempfile
import unittest
import yaml

from sighthouse.pipeline.worker import ExecutionStep, ExecutionChain, Job
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


if __name__ == "__main__":
    unittest.main()
