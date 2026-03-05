from tempfile import TemporaryDirectory
from argparse import ArgumentParser
from pathlib import Path

from sighthouse.pipeline.worker import Preprocessor, Job
from sighthouse.core.utils import download_file, extract_tar


class PlatformIoPreprocessor(Preprocessor):

    def __init__(self, worker_url: str, repo_url: str):
        super().__init__("PlatformIo Preprocessor", worker_url, repo_url)

    def do_work(self, job: Job) -> None:
        with TemporaryDirectory() as tmpdirname:
            tmpdir = Path(tmpdirname)
            url = job.job_data.get("url")
            req = download_file(url)
            if not req:
                raise Exception("Could not download tar file: '{}'".format(url))
            if not extract_tar(req, tmpdir):
                raise Exception("Could not extract tar file")
            self.pack_and_send_task(job, list(tmpdir.iterdir()))


def main():
    parser = ArgumentParser(description="PlatformIo Preprocessor worker")
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
    PlatformIoPreprocessor(args.worker_url, args.repo_url).run()


main()
