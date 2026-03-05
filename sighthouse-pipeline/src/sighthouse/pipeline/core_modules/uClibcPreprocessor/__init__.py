from typing import Dict, List, Tuple
from tempfile import TemporaryDirectory
from argparse import ArgumentParser
from pathlib import Path

from sighthouse.pipeline.worker import Preprocessor, Compiler, Job
from sighthouse.core.utils import (
    download_file,
    extract_tar,
    run_process,
)


class uClibcPreprocessor(Preprocessor):

    def __init__(self, worker_url: str, repo_url: str):
        super().__init__("uClibc Preprocessor", worker_url, repo_url)

    def get_kernel_headers(self) -> Path:
        """Retrieve kernel headers sources"""
        dir = Path(__file__).parent.absolute()
        headers = dir / "linux-4.0"
        if headers.exists() and headers.is_dir():
            return headers

        self.log("Retrieving kernel sources")
        url = "https://www.kernel.org/pub/linux/kernel/v4.x/linux-4.0.tar.xz"
        req = download_file(url)
        if not req:
            raise Exception("Could not download tar file: '{}'".format(url))

        if not extract_tar(req, dir):
            raise Exception("Could not extract tar file")

        if not headers.exists() or not headers.is_dir():
            raise Exception("Could no find linux sources inside tar file")

        return headers

    def install_kernel_headers(self, directory: Path, options: Dict[str, str]) -> None:
        """Install kernel headers sources inside the given directory"""
        headers: Path = self.get_kernel_headers()
        # Full list of available arch can be obtained by installing all headers with `make headers_install_all`
        # and then using `ls -d include/asm-* | sed 's/.*-//'` to list

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

        ret, _, _ = run_process(
            [
                "make",
                "headers_install",
                "ARCH={}".format(arch),
                "INSTALL_HDR_PATH={}".format(directory / "linux-headers"),
            ],
            cwd=headers,
            capture_output=True,
        )
        if ret != 0:
            raise Exception("Fail to install kernel headers")

    def do_work(self, job: Job) -> None:
        _: Path = self.get_kernel_headers()
        # Get the file now before it could be modified by pack_and_send_task
        job_file: str = job.job_data.get("file")
        for id, args in job.get_next_worker_args():
            variants: List[Tuple[str, Dict[str, str]]] = (
                Compiler.validate_compiler_variants(args)
            )
            for name, options in variants:
                # Create a new temporary directory and clone the same project each time to avoid
                # conflicts between previous builds
                with TemporaryDirectory() as tmpdirname:
                    tmpdir = Path(tmpdirname)
                    req = self.get_file(job_file)
                    if not req:
                        raise Exception(
                            "Could not download tar file: '{}'".format(job_file)
                        )

                    if not extract_tar(req, tmpdir):
                        raise Exception("Could not extract tar file")

                    self.install_kernel_headers(tmpdir, options)

                    # Repack things
                    self.pack_and_send_task(job, list(tmpdir.rglob("**/*")), step=id)


def main():
    parser = ArgumentParser(description="uClibc Preprocessor worker")
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
    uClibcPreprocessor(args.worker_url, args.repo_url).run()


main()
