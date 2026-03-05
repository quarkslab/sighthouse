from argparse import ArgumentParser
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional
import os

from sighthouse.pipeline.worker import Scrapper, Job
from sighthouse.core.utils import (
    create_tar,
    run_process,
    get_minimal_paths,
)


class GitScrapper(Scrapper):

    def __init__(
        self,
        worker_url: str,
        repo_url: str | None,
    ):
        # Check if git is installed and available
        try:
            ret, _, _ = run_process(["git", "--version"], capture_output=True)
            if ret != 0:
                raise Exception("Error: Git is not installed or not available in PATH.")
        except (Exception, FileNotFoundError):
            raise Exception("Error: Git is not installed or not available in PATH.")

        super().__init__("Git Scrapper", worker_url, repo_url)

    def validate_repos(self, data: dict) -> list[dict]:
        """
        Validate repositories structure. Each repository must have: name (str), url (str), branches (list[str]).

        Args:
            data (dict): Dictionary of repositories to validate.

        Returns:
            list[dict]: The list of repositories objects.

        """

        # Check top-level key
        if not isinstance(data, dict) or "repositories" not in data:
            raise ValueError(
                "YAML must contain a 'repositories' list at the top level."
            )

        repositories = data["repositories"]
        if not isinstance(repositories, list):
            raise ValueError("'repositories' must be a list.")

        # Validate each repository entry
        for idx, repo in enumerate(repositories, start=1):
            if not isinstance(repo, dict):
                raise ValueError("Repository #{} is not a dictionary.".format(idx))

            required_keys = {"name", "url", "branches"}
            missing = required_keys - repo.keys()
            if missing:
                raise ValueError(
                    "Repository #{} is missing keys: {}".format(idx, ", ".join(missing))
                )

            # key type checks
            if not isinstance(repo["name"], str):
                raise TypeError(
                    "'name' in repository #{} must be a string.".format(idx)
                )
            if not isinstance(repo["url"], str):
                raise TypeError("'url' in repository #{} must be a string.".format(idx))

            if not isinstance(repo["branches"], list) or not all(
                isinstance(tag, str) for tag in repo["branches"]
            ):
                raise TypeError(
                    "'branches' in repository #{} must be a list of strings.".format(
                        idx
                    )
                )

        return repositories

    def get_commit_from_tag(self, tag: str, repo_path: Path) -> Optional[str]:
        """
        Retrieves the commit hash associated with a specific Git tag in a repository.

        Args:
            repo_path (Path): Path to the repository root directory.
            tag (str): Name of the Git tag (e.g., 'v1.0.0').

        Returns:
            Optional[str]: The full commit hash (SHA) if found, None if tag not found
                           or any error occurs.
        """
        try:
            # Ensure repository path exists
            if not repo_path.exists():
                self.log(
                    "Error: Repository path '{}' does not exist.".format(repo_path)
                )
                return False

            command = [
                "git",
                "--git-dir={}".format(repo_path / ".git"),
                "--work-tree={}".format(repo_path),
                "rev-list",
                "-n",
                "1",
                tag,
            ]

            result, stdout, stderr = run_process(command, capture_output=True)
            commit_hash = stdout.decode().strip()
            return commit_hash if commit_hash else None

        except Exception as e:
            self.log("Error: {}".format(e))
            return None

    def clone_git_repo(self, repo_url: str, directory: Path) -> bool:
        """
        Clones a git repository into the specified directory.

        Args:
            repo_url (str): The URL of the git repository to clone.
            directory (Path): The target directory

        Returns:
            bool: True if successful, False otherwise.
        """
        command = ["git", "clone", repo_url, str(directory.absolute())]

        try:
            result, _, stderr = run_process(command, capture_output=True)
            if result == 0:
                self.log("Successfully cloned {}".format(repo_url))
                return True
            else:
                self.log("Error cloning repository: {}".format(stderr))
                return False
        except Exception as e:
            self.log("Error cloning repository: {}".format(e.stderr))
            return False

    def checkout_git_repo(self, ref: str, repo_path: Path) -> bool:
        """
        Checks out a specific branch, tag, or commit in a git repository.

        Args:
            repo_path (Path): Path to the repository root.
            ref (str): Branch name, tag, or commit hash to checkout (e.g., 'main', 'v1.0', 'abc123').

        Returns:
            bool: True if successful, False otherwise.
        """
        # Ensure repository path exists
        if not repo_path.exists():
            self.log("Error: Repository path '{}' does not exist.".format(repo_path))
            return False

        command = [
            "git",
            "--git-dir={}".format(repo_path / ".git"),
            "--work-tree={}".format(repo_path),
            "checkout",
            ref,
        ]

        try:
            result, _, stderr = run_process(command, capture_output=True)
            if result == 0:
                self.log("Successfully checked out {}".format(ref))
                return True
            else:
                self.log("Error checking out '{}': {}".format(ref, stderr))
                return False
        except Exception as e:
            self.log("Error checking out '{}': {}".format(ref, e.stderr))
            return False

    def pack_repo(self, repo_path: Path, hash: str) -> str:
        """
        Packs all files from the repository into a tar.gz archive, excluding .git directory and its contents.

        Args:
            repo_path (Path): The root path of the repository to be packed.
            hash (str): Unique identifier used as the name for the resulting tar.gz file.

        Returns:
            str: The name of the created tar.gz file.
        """
        self.log("Packing files")
        files = []
        for path in repo_path.rglob("*"):
            # Skip .git directory and anything inside it
            if path.is_file() and ".git" not in path.parts:
                files.append(path)

        # Create tar archive
        common_prefix, files = get_minimal_paths(files)
        back = Path.cwd()
        os.chdir(common_prefix)
        tar = create_tar(common_prefix, files).read()
        os.chdir(back)
        name = "{}.tar.gz".format(hash)

        # Push file to repo
        if not self.push_file(name, tar):
            raise Exception("Fail to send build to compiler")

        self.log("Publish file: {}".format(hash))
        return name

    def do_work(self, job: Job) -> None:
        repos = self.validate_repos(job.worker_args)
        for repo in repos:
            with TemporaryDirectory() as tmpdirname:
                tmpdir = Path(tmpdirname)
                # Clone repo once
                self.clone_git_repo(repo["url"], tmpdir)
                for branch in repo["branches"]:
                    # Checkout the repo for the given commit/tag
                    if not self.checkout_git_repo(branch, tmpdir):
                        break

                    hash = self.get_commit_from_tag(branch, tmpdir)

                    file = self.pack_repo(tmpdir, hash)
                    job.job_data.update(
                        {
                            "origin": repo["url"],
                            "file": file,
                            "hash": hash,
                            "name": repo["name"],
                            "version": branch,
                        }
                    )
                    self.send_task(job)


def main():
    parser = ArgumentParser(description="Git Scrapper worker")
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
    GitScrapper(args.worker_url, args.repo_url).run()


main()
