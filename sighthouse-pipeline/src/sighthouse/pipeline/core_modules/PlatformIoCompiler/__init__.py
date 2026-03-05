from tempfile import TemporaryDirectory
from argparse import ArgumentParser
from pathlib import Path
import sys
import tempfile
import json

from typing import List

from sighthouse.pipeline.worker import Compiler, Job
from sighthouse.core.utils import (
    extract_tar,
    run_process,
)

# from dependency_directory import get_dir_dependency


class PlatformIoCompiler(Compiler):
    """Simple builder for plateformIO jobs"""

    PLATFORMIO_FILE = "platformio.ini"
    BUILD_DIR = ".pio/build"
    # Run the command with a 4h timeout (which should be enough for the compilation to finish)
    BUILD_TIMEOUT = 4 * 3600

    def __init__(self, worker_url: str, repo_url: str, strict: bool = False):
        super().__init__("PlatformIo Compiler", worker_url, repo_url)
        self.strict = strict

    def build(self, path: Path, capture_output: bool = False) -> list[Path]:
        output_files = []
        ini_files = list(Path(path).rglob(self.PLATFORMIO_FILE))
        for ini_file in ini_files:
            process_args = [
                sys.executable,
                "-m" "platformio",
                "run",
                "-d",
                str(ini_file),
            ]
            # Run the command with a 4h timeout (which should be enough for the compilation to finish)
            _ = run_process(
                process_args, capture_output=capture_output, timeout=self.BUILD_TIMEOUT
            )
            build_dir = Path(ini_file.parent, self.BUILD_DIR)
            output_files += list(build_dir.rglob("*.o"))

        return output_files

    def upload_objects_files(self, job: Job, path: Path) -> None:
        ini_files = list(Path(path).rglob(self.PLATFORMIO_FILE))
        for ini_file in ini_files:
            # Import black magic
            with tempfile.NamedTemporaryFile(suffix=".json", delete=True) as tmpfile:
                filename = Path(tmpfile.name).resolve()

                args = [
                    sys.executable,
                    str(Path(__file__).parent / "dependency_directory.py"),
                    filename,
                    "--project-dir",
                    str(ini_file.parent),
                ]
                # Pass the strict flag to the script
                if self.strict:
                    args.append("--strict")

                ret = run_process(
                    args,
                    timeout=self.BUILD_TIMEOUT,
                    capture_output=True,
                )
                if ret[0] != 0:
                    self.log("\nSTDOUT:\n{}".format(ret[1].decode("utf-8")))
                    self.log("\nSTDERR:\n{}".format(ret[2].decode("utf-8")))
                    raise Exception(ret[2])

                self.log("\nSTDOUT:\n{}".format(ret[1].decode("utf-8")))

                # Load JSON result
                with open(filename, "r", encoding="utf-8") as f:
                    results = json.load(f)

            if self.strict and len(results) == 0:
                raise Exception(
                    "Fail to retrieve metadata for ALL the compiled files, failling"
                )

            for result in results:
                # Upload libraries if any
                lib_metadata = []
                for lib in result["libraries"]:
                    lib_metadata.append((lib["name"], lib["version"]))
                    self.pack_and_send_task(
                        job, [Path(file) for file in lib["files"]], [lib_metadata[-1]]
                    )

                # Upload framework (assume there are always one)
                example_metadata = []
                if "framework" in result:
                    framework_metadata = (
                        result["framework"]["name"],
                        result["framework"]["version"],
                    )
                    self.pack_and_send_task(
                        job,
                        [Path(file) for file in result["framework"]["files"]],
                        [framework_metadata],
                    )
                    # Upload example
                    example_metadata = [framework_metadata]
                example_metadata.extend(lib_metadata)
                # Add a reference to self metadata if not already present
                self_metadata = (job.job_data["name"], job.job_data["version"])
                if self_metadata not in example_metadata:
                    example_metadata.append(self_metadata)

                self.pack_and_send_task(
                    job,
                    [Path(file) for file in result["example"]["files"]],
                    example_metadata,
                )

    def do_work(self, job: Job) -> None:
        with TemporaryDirectory() as tmpdirname:
            tmpdir = Path(tmpdirname)
            job_file = job.job_data.get("file")
            req = self.get_file(job_file)
            if not req:
                raise Exception("Could not download tar file: '{}'".format(job_file))

            if not extract_tar(req, tmpdir):
                raise Exception("Could not extract tar file")
            # Unsure that there is at least one .ini file
            if len(list(tmpdir.rglob(self.PLATFORMIO_FILE))) == 0:
                raise Exception(
                    "PlatformIo package does not contain '{}' files".format(
                        self.PLATFORMIO_FILE
                    )
                )

            # Build platformio project
            build_files: List = self.build(tmpdir, False)
            if len(build_files) == 0:
                raise Exception("PlatformIo produce 0 file")
            # TODO check number of objects files
            self.upload_objects_files(job, tmpdir)


def main():
    parser = ArgumentParser(description="PlatformIo Compiler worker")
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
    parser.add_argument(
        "--strict", action="store_true", help="Enable strict mode checking"
    )

    args = parser.parse_args()

    PlatformIoCompiler(args.worker_url, args.repo_url, strict=args.strict).run()


main()
