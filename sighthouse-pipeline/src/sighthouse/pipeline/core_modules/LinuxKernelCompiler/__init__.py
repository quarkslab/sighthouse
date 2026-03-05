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


class LinuxKernelCompiler(Compiler):

    # 4h timeout
    TIMEOUT: int = 3600 * 4

    def __init__(self, worker_url: str, repo_url: str):
        super().__init__("Linux Kernel Compiler", worker_url, repo_url)

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
                # Build configure command with environment variables
                env_vars = os.environ.copy()
                env_vars.update(
                    {"CC": options.get("cc"), "CFLAGS": options.get("cflags")}
                )

                # Compiler will default to gcc x86
                # Useful ressource: https://wiki.osdev.org/Target_Triplet
                cc = options.get("cc", "x86_64-linux-gnu-gcc")
                if cc == "x86_64-linux-gnu-gcc" or cc == "gcc":
                    arch = "x86"
                elif cc == "arm-linux-gnueabi-gcc":
                    arch = "arm"
                elif cc == "mips-linux-gnu-gcc" or cc == "mipsel-linux-gnu-gcc":
                    arch = "mips"
                elif cc == "aarch64-linux-gnu-gcc":
                    arch = "arm64"
                else:
                    raise Exception("Unsupported compiler: '{}'".format(cc))

                # 1. Configure for architecture
                args = ["make"]
                if arch != "x86":
                    args += [
                        "ARCH={}".format(arch),
                        "CROSS_COMPILE={}".format(cc.rstrip("gcc")),
                    ]

                ret, out, err = run_process(
                    [["yes", '"'], args + ["defconfig"]],
                    cwd=tmpdir,
                    env=env_vars,
                    timeout=self.TIMEOUT,
                )
                if ret != 0:
                    raise Exception("Fail to configure kernel build")

                # 2. Build with make
                run_process(
                    [["yes", '"'], args + ["all"]],
                    cwd=tmpdir,
                    env=env_vars,
                    timeout=self.TIMEOUT,
                )
                build_files = list(tmpdir.rglob("**/*.o")) + list(
                    tmpdir.rglob("**/vmlinux")
                )
                if len(build_files) == 0:
                    raise Exception("Build produce 0 file")

                metadata = [
                    [job.job_data["name"], job.job_data["version"] + "-" + name]
                ]
                self.pack_and_send_task(job, build_files, metadata)


def main():
    parser = ArgumentParser(description="Linux Kernel Compiler worker")
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
    LinuxKernelCompiler(args.worker_url, args.repo_url).run()


main()
