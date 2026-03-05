from typing import Dict, List, Tuple
from tempfile import TemporaryDirectory
from argparse import ArgumentParser
from pathlib import Path
import os

from sighthouse.pipeline.worker import Compiler, Job
from sighthouse.core.utils import (
    extract_tar,
    run_process,
)


class AutotoolsCompiler(Compiler):

    # 3h timeout
    TIMEOUT: int = 3600 * 3

    def __init__(self, worker_url: str, repo_url: str):
        super().__init__("Autotools Compiler", worker_url, repo_url)

    def do_work(self, job: Job) -> None:
        variants: List[Tuple[str, Dict[str, str]]] = self.validate_compiler_variants(
            job.worker_args
        )
        # Get the file now before it could be modified by pack_and_send_task
        job_file = job.job_data.get("file")
        for name, options in variants:
            # Create a new temporary directory and clone the same project each time to avoid
            # conflicts between previous builds
            with TemporaryDirectory() as tmpdirname:
                tmpdir: Path = Path(tmpdirname)
                req = self.get_file(job_file)
                if not req:
                    raise Exception(
                        "Could not download tar file: '{}'".format(job_file)
                    )

                if not extract_tar(req, tmpdir):
                    raise Exception("Could not extract tar file")

                # Create build directory inside tmpdir
                build_dir: Path = tmpdir / "build"
                build_dir.mkdir(exist_ok=True)

                # 1. Run ./autogen.sh or autoreconf if needed
                autogen: Path = tmpdir / "autogen.sh"
                if autogen.exists():
                    run_process(["sh", "autogen.sh"], cwd=tmpdir, timeout=self.TIMEOUT)

                # Many projects are already shipped with configure. Check for configure script (case insensitive)
                configure_candidates = ["configure", "Configure"]
                configure_path = None
                for candidate in configure_candidates:
                    path = tmpdir / candidate
                    if path.exists():
                        configure_path = path
                        break

                if configure_path is None:
                    run_process(
                        ["autoreconf", "--install"], cwd=tmpdir, timeout=self.TIMEOUT
                    )
                    configure_path = tmpdir / "configure"

                if not configure_path.exists():
                    raise Exception("Fail to find configure")

                # Build configure command with environment variables
                env_vars = os.environ.copy()
                env_vars.update(
                    {"CC": options.get("cc"), "CFLAGS": options.get("cflags")}
                )

                # 2. Run ../configure (or ../Configure) FROM BUILD DIR
                cmd = ["../{}".format(configure_path.name)]
                cmd.append("--prefix={}".format(build_dir.absolute()))
                extra_args = options.get("configure_extra_args")
                if extra_args:
                    cmd.append(extra_args)

                run_process(
                    cmd, cwd=build_dir, env=env_vars, timeout=self.TIMEOUT
                )  # Run from build_dir

                # 3. Build with make in BUILD DIR
                run_process(["make"], cwd=build_dir, timeout=self.TIMEOUT)
                build_files = list(tmpdir.rglob("**/*.o")) + list(
                    tmpdir.rglob("**/*.so")
                )
                if len(build_files) == 0:
                    raise Exception("Build produce 0 file")

                metadata = [
                    [job.job_data["name"], job.job_data["version"] + "-" + name]
                ]
                self.pack_and_send_task(job, build_files, metadata)


def main():
    parser = ArgumentParser(description="Autotools Compiler worker")
    parser.add_argument(
        "-w", "--worker-url", type=str, required=True, help="Url of the worker server"
    )
    parser.add_argument(
        "-r",
        "--repo-url",
        type=str,
        required=True,
        help="Url of the repository to upload files",
    )

    args = parser.parse_args()
    AutotoolsCompiler(args.worker_url, args.repo_url).run()


main()
