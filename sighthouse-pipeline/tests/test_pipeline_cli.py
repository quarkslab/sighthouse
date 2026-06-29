import io
import json
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch, MagicMock

from sighthouse.pipeline.cli import (
    run_package_cmd_handler,
    install_package_cmd_handler,
    uninstall_package_cmd_handler,
    list_package_cmd_handler,
    export_package_cmd_handler,
    stats_pipeline_cmd_handler,
    list_pipeline_cmd_handler,
    worker_pipeline_cmd_handler,
    restart_pipeline_cmd_handler,
    start_pipeline_cmd_handler,
    add_to_cli,
)


def _run_args(**overrides):
    """Build a Namespace with the defaults expected by run_package_cmd_handler."""
    args = Namespace(
        debug=False,
        install=False,
        force=False,
        job=None,
        package="Some Package",
    )
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


@patch("sighthouse.pipeline.cli.PackageLoader")
class TestRunPackageCmdHandler(unittest.TestCase):
    def test_run_without_install_runs_by_name(self, MockLoader):
        loader = MockLoader.return_value
        loader.run.return_value = True

        args = _run_args(package="Ghidra Analyzer")
        run_package_cmd_handler(None, args, ["-w", "redis://x"])

        # No install flow when -i is absent
        loader.install.assert_not_called()
        loader.run.assert_called_once_with(
            "Ghidra Analyzer", args=["-w", "redis://x"], job=None
        )

    def test_run_with_install_runs_by_returned_metadata_name(self, MockLoader):
        loader = MockLoader.return_value
        # install() now returns the installed package's metadata (it resolves
        # the source itself, including bundled core-module names like
        # "GhidraAnalyzer"); the handler runs it by that real name.
        meta = MagicMock()
        meta.name = "Ghidra Analyzer"
        loader.install.return_value = meta
        loader.run.return_value = True

        args = _run_args(install=True, force=True, package="GhidraAnalyzer")
        run_package_cmd_handler(None, args, ["-w", "redis://x"])

        loader.install.assert_called_once_with("GhidraAnalyzer", overwrite=True)
        # The handler must NOT re-derive the name from the raw source path.
        loader.load_metadata.assert_not_called()
        loader.run.assert_called_once_with(
            "Ghidra Analyzer", args=["-w", "redis://x"], job=None
        )

    def test_run_with_install_failure_does_not_run(self, MockLoader):
        loader = MockLoader.return_value
        loader.install.return_value = None

        args = _run_args(install=True, package="Nope")
        run_package_cmd_handler(None, args, [])

        loader.install.assert_called_once()
        loader.run.assert_not_called()


@patch("sighthouse.pipeline.cli.PackageLoader")
class TestInstallPackageCmdHandler(unittest.TestCase):
    def test_install_forwards_package_and_force(self, MockLoader):
        loader = MockLoader.return_value
        loader.install.return_value = True

        args = Namespace(debug=False, package="GhidraAnalyzer", force=True)
        install_package_cmd_handler(None, args, [])

        loader.install.assert_called_once_with("GhidraAnalyzer", overwrite=True)


@patch("sighthouse.pipeline.cli.PackageLoader")
class TestRunPackageWithJob(unittest.TestCase):
    """The `-j/--job` option makes `run` process a single job from a JSON file."""

    def _write_job(self, state="success"):
        job = {
            "execution_chain": {
                "execution_steps": [{"package": "P", "args": {}, "step": "1"}],
                "current_step": "1",
            },
            # The handler inspects job_data["state"] for its exit code, and
            # strips a stale job_data["error"] before running.
            "job_data": {"error": "old error to be dropped", "state": state},
            "job_metadata": {"id": "x"},
        }
        fd = tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(job, fd)
        fd.close()
        return Path(fd.name)

    def test_run_with_job_loads_file_and_passes_job(self, MockLoader):
        loader = MockLoader.return_value
        loader.run.return_value = True

        job_path = self._write_job(state="success")
        try:
            args = _run_args(package="P", job=str(job_path))
            with self.assertRaises(SystemExit) as ctx:
                run_package_cmd_handler(None, args, [])
            # state == success -> exit code 0
            self.assertEqual(ctx.exception.code, 0)

            # The job was forwarded and its stale "error" data was stripped.
            _, kwargs = loader.run.call_args
            job = kwargs["job"]
            self.assertNotIn("error", job.job_data)
        finally:
            job_path.unlink(missing_ok=True)

    def test_run_with_failed_job_exits_nonzero(self, MockLoader):
        loader = MockLoader.return_value
        loader.run.return_value = True

        job_path = self._write_job(state="failed")
        try:
            args = _run_args(package="P", job=str(job_path))
            with self.assertRaises(SystemExit) as ctx:
                run_package_cmd_handler(None, args, [])
            self.assertEqual(ctx.exception.code, 1)
        finally:
            job_path.unlink(missing_ok=True)

    def test_run_with_invalid_job_path_does_not_run(self, MockLoader):
        loader = MockLoader.return_value
        args = _run_args(package="P", job="/no/such/job.json")
        buf = io.StringIO()
        with redirect_stdout(buf):
            run_package_cmd_handler(None, args, [])
        self.assertIn("Invalid job file", buf.getvalue())
        loader.run.assert_not_called()


@patch("sighthouse.pipeline.cli.PackageLoader")
class TestSimplePackageHandlers(unittest.TestCase):
    def test_uninstall_success_message(self, MockLoader):
        loader = MockLoader.return_value
        loader.uninstall.return_value = True
        args = Namespace(debug=False, package="P")
        buf = io.StringIO()
        with redirect_stdout(buf):
            uninstall_package_cmd_handler(None, args, [])
        loader.uninstall.assert_called_once_with("P")
        self.assertIn("Successfully uninstalled", buf.getvalue())

    def test_uninstall_failure_message(self, MockLoader):
        loader = MockLoader.return_value
        loader.uninstall.return_value = False
        args = Namespace(debug=False, package="P")
        buf = io.StringIO()
        with redirect_stdout(buf):
            uninstall_package_cmd_handler(None, args, [])
        self.assertIn("Fail to uninstall", buf.getvalue())

    def test_list_prints_each_package(self, MockLoader):
        loader = MockLoader.return_value
        meta = MagicMock()
        meta.__str__ = lambda self: "pkgA v1.0"
        meta.description = "the A package"
        loader.list_modules.return_value = [meta]
        args = Namespace(debug=False)
        buf = io.StringIO()
        with redirect_stdout(buf):
            list_package_cmd_handler(None, args, [])
        out = buf.getvalue()
        self.assertIn("pkgA v1.0", out)
        self.assertIn("the A package", out)

    def test_export_uses_package_name_when_no_output(self, MockLoader):
        loader = MockLoader.return_value
        loader.export_package.return_value = True
        args = Namespace(debug=False, package="P", output=None)
        buf = io.StringIO()
        with redirect_stdout(buf):
            export_package_cmd_handler(None, args, [])
        # Falls back to the package name as destination.
        loader.export_package.assert_called_once_with("P", "P")
        self.assertIn("Successfully exported", buf.getvalue())

    def test_export_failure_message(self, MockLoader):
        loader = MockLoader.return_value
        loader.export_package.return_value = False
        args = Namespace(debug=False, package="P", output="out.tar.gz")
        buf = io.StringIO()
        with redirect_stdout(buf):
            export_package_cmd_handler(None, args, [])
        loader.export_package.assert_called_once_with("P", "out.tar.gz")
        self.assertIn("Fail to export", buf.getvalue())


@patch("sighthouse.pipeline.cli.PipelineManager")
class TestPipelineHandlers(unittest.TestCase):
    def _args(self, **overrides):
        args = Namespace(
            debug=False,
            worker="redis://w",
            repo="redis://r",
            state=None,
            package=None,
            filter=None,
            group_by=None,
            max=-1,
            jobs=[],
            pipeline="pipeline.yml",
        )
        for k, v in overrides.items():
            setattr(args, k, v)
        return args

    def test_stats_prints_json(self, MockManager):
        manager = MockManager.return_value
        manager.stats.return_value = {"WorkerA": {"success": 1}}
        buf = io.StringIO()
        with redirect_stdout(buf):
            stats_pipeline_cmd_handler(None, self._args(), [])
        self.assertIn("WorkerA", buf.getvalue())
        manager.stats.assert_called_once_with(state=None, package=None)

    def test_stats_empty_prints_error(self, MockManager):
        manager = MockManager.return_value
        manager.stats.return_value = {}
        buf = io.StringIO()
        with redirect_stdout(buf):
            stats_pipeline_cmd_handler(None, self._args(), [])
        self.assertIn("Failed to gather stats", buf.getvalue())

    def test_list_pipeline_forwards_all_filters(self, MockManager):
        manager = MockManager.return_value
        args = self._args(
            state="failed", package="P", filter="x", group_by="error", max=5
        )
        list_pipeline_cmd_handler(None, args, [])
        manager.list_jobs.assert_called_once_with(
            state="failed", package="P", filters="x", group_by="error", max_jobs=5
        )

    def test_worker_prints_json(self, MockManager):
        manager = MockManager.return_value
        manager.inspect_workers.return_value = {"workers": []}
        buf = io.StringIO()
        with redirect_stdout(buf):
            worker_pipeline_cmd_handler(None, self._args(), [])
        self.assertIn("workers", buf.getvalue())

    def test_worker_empty_prints_error(self, MockManager):
        manager = MockManager.return_value
        manager.inspect_workers.return_value = {}
        buf = io.StringIO()
        with redirect_stdout(buf):
            worker_pipeline_cmd_handler(None, self._args(), [])
        self.assertIn("Failed to gather stats on workers", buf.getvalue())

    def test_restart_forwards_explicit_jobs(self, MockManager):
        manager = MockManager.return_value
        with patch("sighthouse.pipeline.cli.is_stdin_piped", return_value=False):
            restart_pipeline_cmd_handler(None, self._args(jobs=["a", "b"]), [])
        manager.restart_jobs.assert_called_once_with(["a", "b"])

    def test_restart_reads_jobs_from_stdin(self, MockManager):
        manager = MockManager.return_value
        with (
            patch("sighthouse.pipeline.cli.is_stdin_piped", return_value=True),
            patch("sighthouse.pipeline.cli.sys.stdin", io.StringIO("j1\n\nj2\n")),
        ):
            restart_pipeline_cmd_handler(None, self._args(jobs=[]), [])
        # Empty lines are skipped.
        manager.restart_jobs.assert_called_once_with(["j1", "j2"])

    def test_start_pipeline_forwards_path(self, MockManager):
        manager = MockManager.return_value
        start_pipeline_cmd_handler(None, self._args(pipeline="my.yml"), [])
        manager.start_pipeline.assert_called_once_with("my.yml")


class TestAddToCli(unittest.TestCase):
    """`add_to_cli` must register the package and pipeline command groups."""

    def test_registers_package_and_pipeline_commands(self):
        import argparse
        from sighthouse.cli import SightHouseCommandLine

        app = SightHouseCommandLine(prog="sighthouse")
        app.add_subparsers(dest="command")

        add_to_cli(app)

        # Both top-level groups are registered on the app.
        self.assertIn("package", app._commands)
        self.assertIn("pipeline", app._commands)

        # Sub-commands are registered on their respective group parsers.
        sub = next(a for a in app._actions if isinstance(a, argparse._SubParsersAction))
        package_parser = sub.choices["package"]
        pipeline_parser = sub.choices["pipeline"]
        for cmd in ("install", "uninstall", "run", "list", "export"):
            self.assertIn(cmd, package_parser._commands)
        for cmd in ("worker", "stats", "ls", "restart", "start"):
            self.assertIn(cmd, pipeline_parser._commands)


if __name__ == "__main__":
    unittest.main()
