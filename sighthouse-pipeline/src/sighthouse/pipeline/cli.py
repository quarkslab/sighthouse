"""SightHouse pipeline command-line"""

from logging import getLogger, basicConfig, INFO, DEBUG
from typing import List
from argparse import Namespace
from pathlib import Path
import json
import sys

from sighthouse.cli import SightHouseCommandLine
from sighthouse.pipeline.worker import Job
from sighthouse.pipeline.package import PackageLoader
from sighthouse.pipeline.manage import PipelineManager
from sighthouse.core.utils import is_stdin_piped


def install_package_cmd_handler(self, args: Namespace, remaining: List[str]) -> None:
    """Install a sighthouse package"""
    basicConfig(level=INFO if not args.debug else DEBUG)
    logger = getLogger(__name__)
    loader = PackageLoader(logger)
    if loader.install(args.package, overwrite=args.force):
        print("Successfully installed package")
    else:
        print("Fail to install package")


def uninstall_package_cmd_handler(self, args: Namespace, remaining: List[str]) -> None:
    """Delete a sighthouse package"""
    basicConfig(level=INFO if not args.debug else DEBUG)
    logger = getLogger(__name__)
    loader = PackageLoader(logger)
    if loader.uninstall(args.package):
        print("Successfully uninstalled package")
    else:
        print("Fail to uninstall package")


def run_package_cmd_handler(self, args: Namespace, remaining: List[str]) -> None:
    """Run a sighthouse package"""
    basicConfig(level=INFO if not args.debug else DEBUG)
    logger = getLogger(__name__)
    loader = PackageLoader(logger)
    package = args.package

    if args.install:
        package = Path(package)
        if loader.install(package, overwrite=args.force):
            print("Successfully installed package")
            meta = loader.load_metadata(package)
            if not meta:
                print("Fail to get metadata of installed package")
                return
            package = meta.name
        else:
            print("Fail to install package")
            return

    job = None
    job_path = Path(args.job) if args.job else None
    if job_path and (not job_path.exists() or not job_path.is_file()):
        print("Invalid job file")
        return

    if job_path:
        try:
            with open(job_path, "r", encoding="utf-8") as fp:
                job = Job.from_dict(json.load(fp))
                if "error" in job.job_data:
                    del job.job_data["error"]
        except Exception as e:
            print(f"Error: {e}")
            return

    if loader.run(package, args=remaining, job=job):
        print("Successfully run package")
        if job is not None:
            state = job.job_data.get("state")
            sys.exit(int(state == "failed"))

    print("Fail to run package")


def list_package_cmd_handler(self, args: Namespace, remaining: List[str]) -> None:
    """List install sighthouse packages"""
    basicConfig(level=INFO if not args.debug else DEBUG)
    logger = getLogger(__name__)
    loader = PackageLoader(logger)
    modules = loader.list_modules()
    for meta in modules:
        print(f"{meta} — {meta.description}")


def export_package_cmd_handler(self, args: Namespace, remaining: List[str]) -> None:
    """Export a sighthouse package"""
    basicConfig(level=INFO if not args.debug else DEBUG)
    logger = getLogger(__name__)
    loader = PackageLoader(logger)
    # Use <name>.tar.gz as output if not defined
    if loader.export_package(args.package, args.output or args.package):
        print("Successfully exported package")
    else:
        print("Fail to export package")


def stats_pipeline_cmd_handler(self, args: Namespace, remaining: List[str]) -> None:
    """Give some stats about sighthouse pipeline"""
    basicConfig(level=INFO if not args.debug else DEBUG)
    logger = getLogger(__name__)
    manager = PipelineManager(args.worker, args.repo, logger)
    stats = manager.stats(state=args.state, package=args.package)
    if not stats:
        print("Error: Failed to gather stats on pipeline")
    else:
        print(json.dumps(stats, indent=2))


def list_pipeline_cmd_handler(self, args: Namespace, remaining: List[str]) -> None:
    """List sighthouse pipeline"""
    basicConfig(level=INFO if not args.debug else DEBUG)
    logger = getLogger(__name__)
    manager = PipelineManager(args.worker, args.repo, logger)
    manager.list_jobs(
        state=args.state,
        package=args.package,
        filters=args.filter,
        group_by=args.group_by,
        max_jobs=args.max,
    )


def worker_pipeline_cmd_handler(self, args: Namespace, remaining: List[str]) -> None:
    """Give some stats about sighthouse workers"""
    basicConfig(level=INFO if not args.debug else DEBUG)
    logger = getLogger(__name__)
    manager = PipelineManager(args.worker, args.repo, logger)
    stats = manager.inspect_workers()
    if not stats:
        print("Error: Failed to gather stats on workers")
    else:
        print(json.dumps(stats, indent=2))


def restart_pipeline_cmd_handler(self, args: Namespace, remaining: List[str]) -> None:
    """Restart sighthouse pipeline"""
    basicConfig(level=INFO if not args.debug else DEBUG)
    logger = getLogger(__name__)
    manager = PipelineManager(args.worker, args.repo, logger)
    jobs = args.jobs or []
    if is_stdin_piped():
        # Read job from stdin, one per line
        jobs += [line.strip() for line in sys.stdin if len(line.strip()) > 0]

    manager.restart_jobs(jobs)


def start_pipeline_cmd_handler(self, args: Namespace, remaining: List[str]) -> None:
    """Start sighthouse pipeline"""
    basicConfig(level=INFO if not args.debug else DEBUG)
    logger = getLogger(__name__)
    manager = PipelineManager(args.worker, args.repo, logger)
    manager.start_pipeline(args.pipeline)


def add_to_cli(app: SightHouseCommandLine) -> None:
    """Add pipeline argument parser to main command-line app"""
    # Setup package argument parser
    parser_package = app.add_command_group(
        "package", "package_command", help="Handle %(prog)s package"
    )
    if parser_package is not None:
        parser_package_install = parser_package.add_command(
            "install", install_package_cmd_handler, help="Add %(prog)s packages"
        )
        if parser_package_install is not None:
            parser_package_install.add_argument(
                "package", help="The path to the package to install"
            )
            parser_package_install.add_argument(
                "-f", "--force", action="store_true", help="Overwrite existing package"
            )

        parser_package_uninstall = parser_package.add_command(
            "uninstall",
            uninstall_package_cmd_handler,
            help="uninstall %(prog)s packages",
        )
        if parser_package_uninstall is not None:
            parser_package_uninstall.add_argument(
                "package", help="The path to the package to uninstall"
            )

        parser_package_run = parser_package.add_command(
            "run", run_package_cmd_handler, add_help=False, help="run %(prog)s packages"
        )
        if parser_package_run is not None:
            parser_package_run.add_argument(
                "-j",
                "--job",
                type=str,
                help="JSON job to debug. The package will only process this job and exits",
            )
            parser_package_run.add_argument(
                "-f", "--force", action="store_true", help="Overwrite existing package"
            )
            parser_package_run.add_argument(
                "-i",
                "--install",
                action="store_true",
                help="Install the given package before running it",
            )
            parser_package_run.add_argument(
                "package", help="The path to the package to run"
            )

        parser_package.add_command(
            "list", list_package_cmd_handler, help="List %(prog)s packages"
        )
        parser_package_export = parser_package.add_command(
            "export", export_package_cmd_handler, help="Export %(prog)s packages"
        )
        if parser_package_export is not None:
            parser_package_export.add_argument(
                "package", help="The name to the package to export"
            )
            parser_package_export.add_argument(
                "-o", "--output", help="The path to the exported package"
            )

    # Setup pipeline argument parser
    parser_pipeline = app.add_command_group(
        "pipeline", "pipeline_command", help="Handle %(prog)s pipeline"
    )
    if parser_pipeline is not None:
        parser_pipeline.add_argument("-w", "--worker", help="Url of the worker server")
        parser_pipeline.add_argument("-r", "--repo", help="Url of the repo")

        parser_pipeline.add_command(
            "worker",
            worker_pipeline_cmd_handler,
            help="Give some stats about %(prog)s workers",
        )
        parser_pipeline_stats = parser_pipeline.add_command(
            "stats",
            stats_pipeline_cmd_handler,
            help="Give some stats on %(prog)s pipeline",
        )
        if parser_pipeline_stats is not None:
            parser_pipeline_stats.add_argument(
                "-s",
                "--state",
                choices=["success", "failed", "processing"],
                help="Optional filter for jobs",
            )
            parser_pipeline_stats.add_argument(
                "-p", "--package", help="Optional filter for jobs"
            )

        parser_pipeline_list = parser_pipeline.add_command(
            "ls", list_pipeline_cmd_handler, help="List %(prog)s pipeline"
        )
        if parser_pipeline_list is not None:
            parser_pipeline_list.add_argument(
                "-s",
                "--state",
                choices=["success", "failed", "processing"],
                help="Optional filter for jobs",
            )
            parser_pipeline_list.add_argument(
                "-p", "--package", help="Optional filter for jobs"
            )
            parser_pipeline_list.add_argument(
                "-f",
                "--filter",
                help="A Python expression that will filter the jobs. "
                "Example: '\".ini\" not in error'",
            )
            parser_pipeline_list.add_argument(
                "-g", "--group-by", help="Key of the job to group by: Example 'error'"
            )
            parser_pipeline_list.add_argument(
                "-m",
                "--max",
                default=-1,
                type=int,
                help="Maximum number of job to display",
            )

        parser_pipeline_restart = parser_pipeline.add_command(
            "restart",
            restart_pipeline_cmd_handler,
            help="Restart job(s) on %(prog)s pipeline",
        )
        if parser_pipeline_restart is not None:
            parser_pipeline_restart.add_argument(
                "jobs", nargs="*", help="List of jobs to restart"
            )

        parser_pipeline_start = parser_pipeline.add_command(
            "start",
            start_pipeline_cmd_handler,
            help="Start %(prog)s pipeline",
        )
        if parser_pipeline_start is not None:
            parser_pipeline_start.add_argument(
                "pipeline", help="Path to pipeline YAML configuration"
            )
