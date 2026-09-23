from argparse import ArgumentParser
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional
import os

from sighthouse.pipeline.worker import Scrapper, Job


class UploadScrapper(Scrapper):
    """Upload scrapper worker.

    Accept a list of `files`:
    files (list[dict]): List of files to process.
        name (str):             Name of the project (required, e.g. "linux").
        version (str):          Version of the project (required, e.g. "1.2.3").
        origin (str):           URL where the project was found (required,
                                e.g. "https://github.com/torvalds/linux/").
        path (str):             Path to the file or directory to analyze. Can be absolute
                                or relative to (required).
    """

    def __init__(
        self,
        worker_url: str,
        repo_url: str | None,
    ):
        super().__init__("Upload Scrapper", worker_url, repo_url)

    def validate_files(self, data: dict) -> list[dict]:
        """
        Validate files structure. Each file must have: name (str), path (str), version (str)
        and an origin (str).

        Args:
            data (dict): Dictionary of files to validate.

        Returns:
            list[dict]: The list of files objects.
        """

        # Check top-level key
        if not isinstance(data, dict) or "files" not in data:
            raise ValueError("YAML must contain a 'files' list at the top level.")

        files = data["files"]
        if not isinstance(files, list):
            raise ValueError("'files' must be a list.")

        # Validate each entry
        for idx, file in enumerate(files, start=1):
            if not isinstance(file, dict):
                raise ValueError(f"File #{idx} is not a dictionary.")

            required_keys = {"name", "path", "version", "origin"}
            missing = required_keys - file.keys()
            if missing:
                raise ValueError(f"File #{idx} is missing keys: {', '.join(missing)}")

            # key type checks, all assumed to be strings
            for key in required_keys:
                if not isinstance(file[key], str):
                    raise TypeError(f"'{key}' in file #{idx} must be a string.")

            # Unsure path exists on disk
            path = Path(file["path"])
            if not path or not (path.is_file() or path.is_dir()) or not path.exists():
                raise FileNotFoundError(
                    f"Invalid file or directory for file #{idx}: '{path}'"
                )

        return files

    def do_work(self, job: Job) -> None:
        files = self.validate_files(job.worker_args)
        for file in files:
            job.job_data.update(
                {
                    "origin": file["origin"],
                    "name": file["name"],
                    "version": file["version"],
                    # @NOTE: Metadata must be added by this scrapper as it is normally
                    #        done by the compiler worker.
                    "metadata": [[file["name"], file["version"]]],
                }
            )
            packed = self.pack_and_send_task(job, [Path(file["path"])])


def main():
    parser = ArgumentParser(description="Upload Scrapper worker")
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
    UploadScrapper(args.worker_url, args.repo_url).run()


main()
