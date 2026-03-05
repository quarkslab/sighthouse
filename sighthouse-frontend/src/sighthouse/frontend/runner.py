"""Celery runner that process analysis request"""

from secrets import token_urlsafe
from pathlib import Path
import argparse
import tempfile
import json
import os

from celery import Celery
from celery.utils.log import get_logger

from sighthouse.core.utils.repo import Repo
from sighthouse.core.utils.analyzer import run_ghidra_script
from sighthouse.frontend.bobross import Match, Function, converge_metadata_selection
from typing import List, Dict, Any
from logging import Logger
import requests


class LocalApiClient:
    """Local API client that update the matches on the database"""

    BATCH_SIZE: int = 200

    def __init__(self, logger: Logger, base_url: str = "http://localhost:6670/api/v1"):
        """
        Initializes the LocalApiClient with the base API URL.

        Args:
            logger (Logger): The logger to use to display progress.
            base_url (str): The base URL for the API.
        """
        self.logger = logger
        self.base_url = base_url

    def delete_all_functions(self, program_id: int, section_id: int) -> None:
        """
        Deletes all functions under a specified program and section.

        Param:
            program_id (int): The ID of the program.
            section_id (int): The ID of the section.
        """
        url = f"{self.base_url}/programs/{program_id}/sections/{section_id}/functions"
        response = requests.delete(url, headers={"Content-Type": "application/json"})
        self.logger.info(f"Delete Function Response Code :: {response.status_code}")
        if response.status_code == 200:
            self.logger.info("Function deleted successfully.")
        else:
            self.logger.warning(
                f"Failed to delete function. Response Code: {response.status_code}"
            )

    def create_functions(
        self, program_id: int, section_id: int, functions: List[Dict[str, Any]]
    ) -> None:
        """
        Creates functions in batches under a specified program and section.

        Args:
            program_id (int): The ID of the program.
            section_id (int): The ID of the section.
            functions (List[Dict[str, Any]]): A list of functions to be created.
        """
        url = f"{self.base_url}/programs/{program_id}/sections/{section_id}/functions"

        for i in range(0, len(functions), self.BATCH_SIZE):
            batch = functions[i : i + self.BATCH_SIZE]
            response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json={"functions": batch},
            )

            self.logger.info(
                f"Batch Update Functions Response Code :: {response.status_code}"
            )
            if response.status_code == 201:  # 201 Created
                self.logger.info("Functions updated successfully for this batch.")
                json_response = response.json()
                functions_array = json_response.get("functions", [])

                for i, function_response in enumerate(functions_array):
                    function_id = function_response.get("id")
                    if i < len(batch):
                        # Update the corresponding function in the batch
                        batch[i]["id"] = function_id
            else:
                self.logger.warning("Failed to update functions for this batch.")

    def create_matches(
        self,
        program_id: int,
        section_id: int,
        function_id: int,
        matches: List[Dict[str, Any]],
    ) -> None:
        """
        Creates matches in batches for a specific function.

        Args:
            program_id (int): The ID of the program.
            section_id (int): The ID of the section.
            function_id (int): The ID of the function.
            matches (List[Dict[str, Any]]): A list of matches to be created.
        """
        url = f"{self.base_url}/programs/{program_id}/sections/{section_id}/functions/{function_id}/matches"

        for i in range(0, len(matches), self.BATCH_SIZE):
            batch = matches[i : i + self.BATCH_SIZE]
            response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json={"matches": batch},
            )
            self.logger.info(
                f"Batch Update Matches Response Code :: {response.status_code}"
            )
            if response.status_code == 201:  # 201 Created
                self.logger.info("Matches updated successfully for this batch.")
            else:
                self.logger.warning("Failed to update matches for this batch.")

    def update_status(self, program_id: int, status: str, progress: str) -> None:
        """
        Updates the status and progress of a specific program.

        Args:
            program_id (int): The ID of the program.
            status (str): The new status to set.
            progress (str): The progress description to set.
        """
        url = f"{self.base_url}/programs/{program_id}/analyze"
        response = requests.put(
            url,
            headers={"Content-Type": "application/json"},
            json={"status": status, "progress": progress},
        )

        self.logger.info(f"Update status Response Code :: {response.status_code}")
        if response.status_code == 200:
            self.logger.info("Status update successfully.")
        else:
            self.logger.warning(
                f"Failed to update status. Response Code: {response.status_code}"
            )


class Worker:
    """Simple worker that process analysis request by using Ghidra analyzer"""

    def __init__(self, args: argparse.Namespace):
        self.celery_app = Celery("", broker=args.url, backend=args.url)  # Useless
        self.ghidradir = Path(args.ghidradir)

        self.logger = get_logger("celery.task")

    def run(self, concurrent_task: int = 1) -> None:
        """Runs the Celery worker performing the analysis.

        Args:
            concurrent_task (int): Number of concurrent tasks to process.
        """

        @self.celery_app.task(name="frontendanalyzer.do_work", queue="frontendanalyzer")
        def frontend_task(job_data: dict) -> str:
            self.logger.info(job_data)
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                binary_path = temp_path / "binary.bin"
                config_path = temp_path / "config.json"
                output_path = temp_path / "output.json"
                error_path = temp_path / "error.log"
                options = job_data["options"]

                binary_data = Repo.download_sharefile(job_data["binary"])
                config_data = Repo.download_sharefile(job_data["config"])
                if not isinstance(binary_data, bytes) or not isinstance(
                    config_data, bytes
                ):
                    return "Failure"

                config = json.loads(config_data)
                config.update(
                    {
                        "file": str(binary_path),
                        "output": str(output_path),
                        "error": str(error_path),
                    }
                )

                with open(binary_path, "wb") as fp:
                    fp.write(binary_data)

                with open(config_path, "w", encoding="utf-8") as fp:
                    json.dump(config, fp)

                client = LocalApiClient(self.logger)
                if self.__work(config, temp_path) != 0:
                    # Analysis failed
                    with open(error_path, "r", encoding="utf-8") as fp:
                        error = fp.read()
                        client.update_status(config["program"]["id"], "finished", error)
                        return "Failure"

                # Analysis succeed, load program
                with open(output_path, "r", encoding="utf-8") as fp:
                    program = json.load(fp)

                # Delete all functions from all sections
                for section in program["sections"]:
                    client.delete_all_functions(program["id"], section["id"])
                    # Recreate all the functions using client API so they get an ID if hey
                    # didn't existed before (was discovered by ghidra)
                    client.create_functions(
                        program["id"], section["id"], section["functions"]
                    )

                    # @TODO: Should we run the Algorithm per section or for whole program?
                    if options.get("BobRoss"):
                        functions: List[Function] = [
                            Function.from_dict(f) for f in section["functions"]
                        ]
                        for function in functions:
                            function.sort_matches_deterministic()

                        result = converge_metadata_selection(
                            functions,
                            distance=64,
                            bonus_malus=0.0935,
                            max_iterations=1,
                            influence_sim=0.85,
                        )
                        section["functions"] = [f.to_dict() for f in result]

                    # Step 4: Upload matches using client API
                    for function in section["functions"]:
                        if len(function["matches"]) > 0:
                            client.create_matches(
                                program["id"],
                                section["id"],
                                function["id"],
                                self.__enhance_matching_result(function["matches"]),
                            )

                client.update_status(
                    config["program"]["id"], "finished", "Analysis successfully ended"
                )

            return "Success"

        self.celery_app.worker_main(
            [
                "--quiet",
                "worker",
                "-n",
                token_urlsafe(12),
                "-c",
                str(concurrent_task),
                "--loglevel=info",
                "-Q",
                "frontendanalyzer",
            ]
        )

    def __enhance_matching_result(self, matches: List[Dict]) -> List[Dict]:
        """Algorithm that aim to increase the relevance of the raw matches return
        by analyzers
        """
        results = {}
        if not matches:
            return []

        matches.sort(key=lambda data: data["metadata"]["significance"])
        for match in matches:
            name = match["name"]
            if name not in results:
                metadata = match["metadata"]
                metadata["nb_match"] = 1
                metadata["score"] = metadata["significance"]
                results[name] = match
            else:
                prev_match = results[name]
                metadata = prev_match["metadata"]
                metadata["nb_match"] += 1
                metadata["score"] += match["metadata"]["significance"]

        for match in results.values():
            metadata = match["metadata"]
            metadata["score"] = metadata["score"] / metadata["nb_match"]

        return list(results.values())

    def __work(self, config: dict, temp_path: Path) -> int:
        # Environnement should not change, so create it once
        env = self.__get_worker_env(config)
        script_path = (
            Path(__file__).parent.resolve()
            / "ghidrascripts"
            / "SightHouseFrontendScript.java"
        )
        logfile = temp_path / "application.log"

        self.logger.debug("Started process frontendAnalyzer for analysis")
        return run_ghidra_script(
            self.ghidradir,
            script_path,
            [str((temp_path / "config.json").absolute())],
            env=env,
            logfile=logfile.absolute(),
        )[0]

    def __get_worker_env(self, config: dict) -> dict[str, str]:
        # Override username java properties so bsim client
        # won't complain when connecting
        my_env = os.environ.copy()
        my_env["_JAVA_OPTIONS"] = ""
        for bsim_config in config["bsim"]["databases"]:
            if bsim_config["url"].startswith("postgresql://"):
                my_env["_JAVA_OPTIONS"] = f"-Duser.name={bsim_config['user']} "
                break

        # Add user.scripts.dir property in case there other scripts with the same name
        script_path = Path(__file__).parent.resolve() / "ghidrascripts"
        my_env["_JAVA_OPTIONS"] += f"-Dghidra.user.scripts.dir={script_path}"
        return my_env


def main():
    """Entrypoint of the celery runner"""
    parser = argparse.ArgumentParser(
        prog="CeleryFrontend", description="CeleryFrontend", epilog="CeleryFrontend"
    )
    parser.add_argument("url")
    parser.add_argument("ghidradir")
    parser.add_argument(
        "-w",
        "--worker",
        type=int,
        default=1,
        help="Number of concurrent task this worker can perform",
    )
    args = parser.parse_args()
    worker = Worker(args)
    worker.run(concurrent_task=args.worker)


if __name__ == "__main__":
    main()
