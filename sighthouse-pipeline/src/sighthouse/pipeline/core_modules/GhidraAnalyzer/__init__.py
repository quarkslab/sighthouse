from typing import Any, Dict, List
from tempfile import TemporaryDirectory
from argparse import ArgumentParser
from pathlib import Path
from os import environ
import json

from sighthouse.core.utils import extract_tar, parse_uri
from sighthouse.core.utils.analyzer import run_ghidra_script
from sighthouse.pipeline.worker import Analyzer, Job


class GhidraAnalyzer(Analyzer):
    """Simple analyzer that uses Ghidra"""

    def __init__(
        self,
        ghidradir: Path,
        worker_url: str,
        repo_url: str | None = None,
    ):
        super().__init__("Ghidra Analyzer", worker_url, repo_url)
        self.ghidradir = ghidradir

    def parse_urls(self, urls: List[str]) -> List[Dict[str, str]]:
        """
        Parse a list of database URLs into dictionaries while preserving the originals.

        Args:
            urls (List[str]): A list of URL strings to parse. Each URL is expected
                              to be a valid connection string supported by `parse_uri`.

        Returns:
            List[Dict[str, str]]: A list of dictionaries where each element represents
                                  the parsed components of a URL plus the original unmodified one.
        """
        result: List[Dict[str, str]] = []
        for url in urls:
            info = parse_uri(url)
            info.update({"url": url})
            result.append(info)

        return result

    def parse_args(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse and validate the 'args' from the YAML configuration.

        Args:
            args (dict): Arguments to parse.

        Returns:
            Dict[str, Dict[str, Any]]: Parsed configuration dictionary with validated fields.
                - Each key (e.g., 'bsim', 'fidb') holds a dictionary with:
                    - 'urls': required list of non-empty string URLs
                    - 'format': only for 'bsim'; defaults to "json" if missing
                    - 'min_instructions' and 'max_instructions': optional integers if defined

        Raises:
            ValueError: If structure is invalid, required fields are missing,
                        or unknown keys are present.

        The configuration is expected to follow this structure:
            args:
              bsim:
                urls:
                  - postgresql://user@bsim_postgres:5432/bsim
                format: simple
                min_instructions: 10
              fidb:
                urls:
                  - postgresql://user@fidb_postgres:5433/fidb
                min_instructions: 2
        """
        if not isinstance(args, dict):
            raise ValueError("'args' must be a dictionary.")

        # Allowed top-level keys inside args
        allowed_top_keys = {"format", "bsim", "fidb"}
        unknown_keys = set(args.keys()) - allowed_top_keys
        if unknown_keys:
            raise ValueError(
                f"Unknown key(s) in 'args': {', '.join(sorted(unknown_keys))}. "
                f"Allowed keys are: {', '.join(sorted(allowed_top_keys))}."
            )

        # Parse format (default to "simple")
        fmt = args.get("format", "simple")
        if not isinstance(fmt, str):
            raise ValueError("'format' inside 'args' must be a string if provided.")

        parsed_args: Dict[str, Any] = {"format": fmt}

        # Iterate over sub-sections (bsim, fidb)
        for system_name in ["bsim", "fidb"]:
            if system_name not in args:
                continue

            system_cfg = args[system_name]
            if not isinstance(system_cfg, dict):
                raise ValueError(f"'{system_name}' must be a dictionary.")

            allowed_fields = {"urls", "min_instructions", "max_instructions"}
            unknown_fields = set(system_cfg.keys()) - allowed_fields
            if unknown_fields:
                raise ValueError(
                    f"Unknown key(s) for '{system_name}': {', '.join(sorted(unknown_fields))}. "
                    f"Allowed keys are: {', '.join(sorted(allowed_fields))}."
                )

            urls = system_cfg.get("urls")
            if (
                not urls
                or not isinstance(urls, list)
                or not all(isinstance(u, str) for u in urls)
            ):
                raise ValueError(
                    f"The 'urls' field for '{system_name}' must be a non-empty list of strings."
                )

            entry: Dict[str, Any] = {"urls": self.parse_urls(urls)}

            for field in ["min_instructions", "max_instructions"]:
                value = system_cfg.get(field)
                if value is not None:
                    if not isinstance(value, int):
                        raise ValueError(
                            f"The field '{field}' for '{system_name}' must be an int if provided."
                        )
                    entry[field] = value

            parsed_args[system_name] = entry

        # Must have at least one of bsim or fidb
        if not any(k in parsed_args for k in ("bsim", "fidb")):
            raise ValueError(
                "At least one of 'fidb' or 'bsim' must be defined under 'args'."
            )

        return parsed_args

    def do_work(self, job: Job) -> None:
        args: Dict[str, Any] = self.parse_args(job.worker_args)
        # Analyze files
        self.log(f"Starting analysis of {job.job_data.get("hash")}")
        # Run ghidra script
        script_path = (
            Path(__file__).parent.resolve()
            / "ghidrascripts"
            / "SightHouseAnalyzerScript.java"
        )

        job_file = job.job_data.get("file")
        with TemporaryDirectory() as tmpdirname:
            tmpdir = Path(tmpdirname)
            req = self.get_file(job_file)
            if not req:
                raise Exception(f"Could not download tar file: '{job_file}'")

            if not extract_tar(req, tmpdir):
                raise Exception("Could not extract tar file")

            # Override username java properties so bsim client
            # won't complain when connecting
            my_env = environ.copy()
            my_env["_JAVA_OPTIONS"] = ""
            for url in args.get("bsim", {}).get("urls", []):
                if url["type"] in ["postgres", "postgresql"] and isinstance(
                    url.get("user"), str
                ):
                    my_env["_JAVA_OPTIONS"] = f'-Duser.name="{url["user"]}" '
                    break

            my_env[
                "_JAVA_OPTIONS"
            ] += f'-Dghidra.user.scripts.dir="{script_path.parent}"'

            # Create our configuration file
            config = {
                "directory": str(tmpdir.absolute()),
                # metadata is an optional argument to retrieve more information about the functions identifies
                "metadata": json.dumps(job.job_data),
                "format": args["format"],
            }
            # Add BSIM/FIDB configuration if defined
            for backend in ["fidb", "bsim"]:
                backend_config = args.get(backend)
                if backend_config is not None:
                    backend_config.update(
                        {
                            "databases": [
                                {
                                    "url": e["url"],
                                    "username": e.get("user", ""),
                                    "password": e.get("password", ""),
                                }
                                for e in backend_config["urls"]
                            ]
                        }
                    )
                    del backend_config["urls"]
                    config.update({backend: backend_config})

            config_file = tmpdir / "config.json"
            with open(config_file, "w") as fp:
                json.dump(config, fp)

            logfile = tmpdir / "ghidra.log"
            returncode, stdout, stderr = run_ghidra_script(
                self.ghidradir,
                script_path,
                [str(config_file.absolute())],
                env=my_env,
                capture_output=True,
                logfile=logfile,
            )
            if returncode != 0:
                traceback = ""
                try:
                    with open(logfile) as fp:
                        traceback = fp.read()
                except Exception:
                    traceback = f"Fail to read ghidra logs. STDERR:\n{stderr.decode()}"

                raise Exception(
                    f"Fail to analyze project: process returned a non zero exit code:\n{traceback}"
                )


def main():
    parser = ArgumentParser(description="Ghidra Analyzer worker")
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
        "-g",
        "--ghidra-dir",
        type=str,
        required=True,
        help="Path to the ghidra root directory",
    )

    args = parser.parse_args()

    GhidraAnalyzer(
        Path(args.ghidra_dir),
        args.worker_url,
        args.repo_url,
    ).run()


main()
