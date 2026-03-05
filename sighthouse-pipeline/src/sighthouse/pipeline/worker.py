"""Worker for the SightHouse pipeline"""

from typing import Any, Dict, List, Tuple, Union, Optional, Sequence
from traceback import format_exception
from secrets import token_urlsafe
from copy import deepcopy
from pathlib import Path
import json
import os

from celery import Celery, signals
from celery.app.task import Task
from celery.worker.control import inspect_command
from celery.utils.log import get_logger

from sighthouse.core.utils.repo import Repo
from sighthouse.core.utils import (
    create_tar,
    get_minimal_paths,
    get_hash,
)


class ExecutionStep:
    """Represent a step in the execution chain of a Job"""

    def __init__(self, package: str, args: Dict[str, Any], step: str):
        """Initializes a new execution step.

        Args:
            package (str): The name of the package containing the step.
            args (Dict[str, Any]): The arguments required for executing the step.
            step (str): The name of the step.
        """
        self.package = package
        self.args = args
        self.step = step

    def to_dict(self) -> Dict[str, Any]:
        """Converts the execution step to a dictionary representation.

        Returns:
            Dict[str, Any]: A dictionary containing the step's package, arguments, and name.
        """
        return {"package": self.package, "args": self.args, "step": self.step}

    def __repr__(self) -> str:
        """Returns a string representation of the execution step.

        Returns:
            str: A string summarizing the step, including package, step name, and arguments.
        """
        return (
            f'{self.__class__.__name__}(package="{self.package}", '
            f'step="{self.step}", args={self.args})'
        )


class ExecutionChain:
    """Represents an ordered list of execution steps for a Job.

    The class manages a sequential chain of `ExecutionStep` instances that define
    the workflow of a job. It supports navigation between steps, retrieval of step
    arguments, and advancement to the next logical set of steps.
    """

    DEFAULT_STEP = "1"

    def __init__(
        self, execution_steps: List[ExecutionStep], current_step: Optional[str] = None
    ):
        """Initializes an execution chain.

        Args:
            execution_steps (List[ExecutionStep]): The sequence of steps to execute.
            current_step (Optional[str]): The label of the current step. Defaults to "1"
                if not provided.
        """
        self.execution_steps = execution_steps
        self.current_step = current_step or self.DEFAULT_STEP

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionChain":
        """Creates an ExecutionChain instance from a dictionary representation.

        Args:
            data (Dict[str, Any]): A dictionary containing step data and current step label.
                Expected format:
                {
                    "execution_steps": [
                        {"package": str, "args": Dict[str, Any], "step": str},
                        ...
                    ],
                    "current_step": str
                }

        Returns:
            ExecutionChain: A new instance built from the provided dictionary.
        """
        steps = [
            ExecutionStep(
                package=step["package"], args=step.get("args", {}), step=step["step"]
            )
            for step in data.get("execution_steps", [])
        ]
        return cls(execution_steps=steps, current_step=data.get("current_step"))

    def to_dict(self) -> Dict[str, Any]:
        """Converts the execution chain to a dictionary representation.

        Returns:
            Dict[str, Any]: A dictionary describing all steps and the current step.
        """
        return {
            "execution_steps": [step.to_dict() for step in self.execution_steps],
            "current_step": self.current_step,
        }

    def get_step(self, step: str) -> Optional[ExecutionStep]:
        """Retrieves the specified execution step.

        Args:
            step (str): The identifier of the step to retrieve.

        Returns:
            Optional[ExecutionStep]: The matching execution step, or None if not found.
        """
        for s in self.execution_steps:
            if s.step == step:
                return s
        return None

    @property
    def worker_args(self) -> Dict[str, Any]:
        """Returns the argument dictionary for the current step.

        Returns:
            Dict[str, Any]: The arguments for the current step, or an empty dict if not found.
        """
        step = self.get_step(self.current_step)
        return step.args if step else {}

    @property
    def package(self) -> Optional[str]:
        """Returns the package name associated with the current step.

        Returns:
            Optional[str]: The package name, or None if the current step does not exist.
        """
        step = self.get_step(self.current_step)
        return step.package if step else None

    def get_next_worker_args(self) -> List[Tuple[str, Dict[str, Any]]]:
        """Retrieves arguments for the next main step(s) in the sequence.

        The method identifies the next major step (based on numeric prefixes)
        and collects the arguments for all substeps within that next step.

        Returns:
            List[Tuple[str, Dict[str, Any]]]: A list of tuples where each tuple contains the
            step identifier and a copy of its argument dictionary. Returns an empty list if there
            are no subsequent steps.
        """
        args = []

        try:
            current_main = int(self.current_step.split(".", 1)[0])
        except ValueError:
            return []

        next_main = current_main + 1

        for step in self.execution_steps:
            try:
                main_index = int(step.step.split(".", 1)[0])
            except ValueError:
                continue
            if main_index == next_main:
                args.append((step.step, deepcopy(step.args or {})))

        return args

    def advance_to_next_step(self) -> Optional[List["ExecutionStep"]]:
        """
        Advance to the next major step and return ALL its substeps.

        - Moves from current position (e.g. "3.2") to next major step (e.g. "4")
        - Sets `current_step` to first substep of that major step
        - Returns all substeps for that major step as a batch

        Returns:
            List[ExecutionStep]: All substeps of next major step, or None if complete.
        """
        # Inline grouping: {main_num: [steps]}
        groups: Dict[int, List["ExecutionStep"]] = {}
        for step in self.execution_steps:
            try:
                main_num = int(step.step.split(".", 1)[0])
                groups.setdefault(main_num, []).append(step)
            except ValueError:
                continue

        current_main = int(self.current_step.split(".", 1)[0])

        # Get next major step substeps
        next_steps = next(
            (steps for n, steps in groups.items() if n > current_main), None
        )

        if next_steps is None:
            return None

        self.current_step = min(step.step for step in next_steps)
        return [deepcopy(step) for step in next_steps]


class Job:
    """Represents a job in an execution chain.

    This class wraps the job's execution logic, data, and metadata.
    It supports serialization to and from a dictionary for persistence.
    """

    def __init__(
        self,
        execution_chain: ExecutionChain,
        job_metadata: Dict[str, Any],
        job_data: Dict[str, Any] | None = None,
    ) -> None:
        """Initializes a Job instance.

        Args:
            execution_chain (ExecutionChain): The job's execution steps or dependencies.
            job_metadata (Dict[str, Any]): Metadata about the job such as id,
                                           predecessor, and state.
            job_data (Dict[str, Any] | None): The data associated with the job.
        """
        self.execution_chain = execution_chain
        self.job_data = job_data or {}
        self.job_metadata = job_metadata
        # Internal, not serialized
        self._next_from: str | None = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Job":
        """Creates a Job instance from a dictionary.

        Args:
            data (Dict[str, Any]): The dictionary containing job data, structured as:
                {
                    "execution_chain": {...},
                    "job_data": {...},
                    "job_metadata": {...}
                }

        Returns:
            Job: A new Job instance created from the given dictionary.
        """
        execution_chain = ExecutionChain.from_dict(data.get("execution_chain", {}))
        job_data = data.get("job_data", {})
        job_metadata = data["job_metadata"]
        return cls(execution_chain, job_metadata, job_data)

    def to_dict(self) -> Dict[str, Any]:
        """Converts the Job instance into a dictionary.

        Returns:
            Dict[str, Any]: The dictionary representation of the Job.
        """
        return {
            "execution_chain": self.execution_chain.to_dict(),
            "job_data": self.job_data,
            "job_metadata": self.job_metadata,
        }

    @property
    def worker_args(self) -> Dict[str, Any]:
        """Retrieves the argument dictionary for the current step.

        Returns:
            Dict[str, Any]: The arguments associated with the current step in the execution chain.
        """
        return self.execution_chain.worker_args

    @property
    def package(self) -> Optional[str]:
        """Retrieves the package name for the current step.

        Returns:
            Optional[str]: The package name of the module responsible for the current step,
            or None if unavailable.
        """
        return self.execution_chain.package

    def get_next_worker_args(self) -> List[Tuple[str, Dict[str, Any]]]:
        """Gets the argument dictionaries for the next step(s) in sequence.

        Returns:
            List[Tuple[str, Dict[str, Any]]]: A list of tuples containing each next step label
            and its corresponding argument dictionary.
        """
        return self.execution_chain.get_next_worker_args()

    def __repr__(self) -> str:
        """Returns a formatted string representation of the Job instance.

        Returns:
            str: A formatted summary of the job.
        """
        return (
            f"{self.__class__.__name__}(id={self.job_metadata.get('id')}, "
            f"state={self.job_metadata.get('state')}, from={self.job_metadata.get('from')})"
        )


class CeleryWorker(Celery):
    """Celery worker with added metadata"""

    def __init__(self, worker_id: str, worker_url: str):
        super().__init__(broker=worker_url, backend=worker_url)
        # Metadata we store
        self.worker_metadata = {"id": worker_id}


@inspect_command(name="worker_metadata", visible=True)
def inspect_worker_metadata(state):
    """Celery Inspection command used to verify the ability to push a job into the pipeline"""
    return state.app.worker_metadata


class CommonWorker:
    """Common class for all the SightHouse pipeline workers"""

    def __init__(
        self,
        worker_id: str,
        worker_url: str,
        repo_url: str | None = None,
    ):
        """Initialize the worker and its Celery app.

        Args:
            worker_id (str): Unique identifier for the worker.
            worker_url (str): Celery broker/backend URL.
            repo_url (str): Optional url for the repo.
        """
        self.__repo = Repo(repo_url, secure=False) if repo_url else None
        self._celery_app = CeleryWorker(
            worker_id,
            worker_url,
        )
        self._logger = get_logger("celery.task")

        # Register signal handlers
        signals.task_success.connect(self._on_task_success, weak=False)
        signals.task_failure.connect(self._on_task_failure, weak=False)

    def _on_task_success(
        self, sender=None, result: Optional[Dict[str, Any]] = None, kwargs=None, **rest
    ):
        """Called whenever a task succeeds"""
        job = Job.from_dict(result or {})
        state = job.job_metadata.get("state", "failed")
        job_id = job.job_metadata.get("id", "unknown")
        module = self._celery_app.worker_metadata.get("id", "unknown")

        msg = (
            f"[SUCCESS] Task {sender.name} | state={state} | "
            f"id={job_id} | result={result}"
        )
        self._logger.debug(msg)
        if self.__repo and not self.__repo.push_file(
            f"{state}/{module}/{job_id}.json",
            json.dumps(result).encode("utf-8"),
        ):
            self._logger.error("result Task couldn't be uploaded")

    def _on_task_failure(
        self,
        sender=None,
        task_id=None,
        exception=None,
        args=None,
        kwargs=None,
        einfo=None,
        **rest,
    ):
        """Called whenever a task fails"""
        if args is None:
            # Minimal information
            msg = f"[FAILURE] Task {sender.name} | state=failed | error={exception}"
            self._logger.error("%s\nTraceback: %s", msg, einfo)
            return

        job = Job.from_dict(args[0])
        job_id = job.job_metadata.get("id")
        module = self._celery_app.worker_metadata.get("id", "unknown")

        msg = (
            f"[FAILURE] Task {sender.name} | state=failed | id={job_id} "
            f"| args={job} | error={exception}"
        )
        self._logger.error("%s\nTraceback: %s", msg, einfo)
        if self.__repo and not self.__repo.push_file(
            f"failed/{module}/{job_id}.json", json.dumps(job).encode("utf-8")
        ):
            self._logger.error("result Task couldn't be uploaded")

    def log(self, message: str, *args, **kwargs) -> None:
        """Log a message using worker's logger

        Args:
            message (str): The message to log
        """
        self._logger.info(message)

    # Repo wrapper
    def push_file(self, upload_path: str, content: bytes) -> bool:
        """
        Pushes or uploads a file to the specified path in either local filesystem or S3.

        Args:
            upload_path (str): The path where the file should be uploaded.
            content (bytes): The content of the file to be uploaded.

        Returns:
            bool: True if successful, False otherwise.

        Raises:
            ValueError: If URI scheme is unsupported.
        """
        if self.__repo:
            return self.__repo.push_file(f"artifacts/{upload_path}", content)
        return False

    def delete_file(self, upload_path: str) -> None:
        """
        Deletes the specified file from either local filesystem or S3.

        Args:
            upload_path (str): The path of the file to be deleted.

        Raises:
            ValueError: If URI scheme is unsupported.
        """
        if self.__repo:
            self.__repo.delete_file(f"artifacts/{upload_path}")

    def get_file(self, upload_path: str) -> Optional[bytes]:
        """
        Retrieves the content of the specified file from either local filesystem or S3.

        Args:
            upload_path (str): The path of the file to be retrieved.

        Returns:
            bytes | None: The content of the file if found, otherwise None.

        Raises:
            ValueError: If URI scheme is unsupported.
        """
        if self.__repo:
            return self.__repo.get_file(f"artifacts/{upload_path}")

        return b""

    def get_sharefile(self, upload_path: str) -> Path | str:
        """
        Returns the path or URL for sharing the file.

        Args:
            upload_path (str): The path of the file to be shared.

        Returns:
            Path | str: A POSIX absolute path if local, a pre-signed URL if S3.

        Raises:
            ValueError: If URI scheme is unsupported.
        """
        if self.__repo:
            return self.__repo.get_sharefile(f"artifacts/{upload_path}")

        return ""

    def send_task(self, job: Job, step: Optional[str] = None) -> None:
        """Sends the job to the next worker in the chain.

        Args:
            job (Job): The Job instance to forward.
            step (str): Optional step to target a specific worker.
        """
        # Copy job to avoid inconsistency if send_task is called more than once inside do_work
        dup = deepcopy(job)
        # Store the future "from" value for the next hop
        if dup._next_from is not None:
            dup.job_metadata["from"] = dup._next_from
            dup._next_from = None

        if step:
            substep = dup.execution_chain.get_step(step)
            if not substep:
                raise ValueError(f"Invalid step '{step}'")

            substeps = [substep]
        else:
            substeps = dup.execution_chain.advance_to_next_step() or []

        for s in substeps:
            dup.execution_chain.current_step = s.step
            self._logger.debug(
                "Sending task %s: %s", s, json.dumps(dup.to_dict(), indent=2)
            )
            self._celery_app.send_task(
                "do_work",
                queue=s.package,
                kwargs={"job_dict": dup.to_dict()},
            )

    def pack_and_send_task(
        self,
        job: Job,
        files: Sequence[Union[Path, str]],
        name: Optional[str] = None,
        step: Optional[str] = None,
    ) -> None:
        """
        Wrapper method that will pack the given files into an archive, upload it onto the
        worker repository and send the given Job to the next worker in the execution chain.

        Params:
            job: (Job): The job to update and send
            files (Sequence[Union[Path, str]]): List of path like to upload
            name (Optional[str]): Optional name for the packed files
            step (Optional[str]): Optional substep to target a specific step
        """
        if files == []:
            return

        self.log("Packing files")
        common_prefix, files = get_minimal_paths(files)
        back = Path.cwd()
        os.chdir(common_prefix)
        tar = create_tar(common_prefix, files).read()
        os.chdir(back)
        name = f"{name if name else get_hash(tar)}.tar.gz"

        if self.push_file(name, tar):
            self.log(f"Publish file: {name}")
            job.job_data.update({"file": name})
            if step:
                self.send_task(job, step=step)
            else:
                self.send_task(job)
        else:
            raise Exception("Fail to publish builder results")

    def run(self, concurrent_task: int = 1) -> None:
        """Runs the Celery worker and registers the processing task.

        Args:
            concurrent_task (int): Number of concurrent tasks to process.
        """

        @self._celery_app.task(
            name="do_work",
            queue=self._celery_app.worker_metadata["id"],
            bind=True,
        )
        def __do_work(task: Task, job_dict: Dict[str, Any]) -> Dict[str, Any]:
            job = Job.from_dict(job_dict)
            job.job_metadata["id"] = str(task.request.id)
            dup = deepcopy(job.to_dict())

            try:
                # Store the future "from" value for the next hop
                job._next_from = str(task.request.id)

                self.do_work(job)

                dup["job_metadata"]["state"] = "success"
            except Exception as e:
                error = "".join(format_exception(e))
                self._logger.error(error)
                dup["job_metadata"].update({"state": "failed", "error": error})

            return dup

        self._celery_app.worker_main(
            [
                "--quiet",
                "worker",
                "-n",
                token_urlsafe(12),
                "-c",
                str(concurrent_task),
                "--loglevel=info",
                "-Q",
                self._celery_app.worker_metadata["id"],
            ]
        )

    def do_work(self, job: Job) -> None:
        """Defines the actual processing behavior for a Job instance.

        Args:
            job (Job): The Job instance to process.

        Raises:
            NotImplementedError: If not overridden in subclasses.
        """
        raise NotImplementedError("Subclasses must implement do_work()")


class Scrapper(CommonWorker):
    """SightHouse scrapper worker"""


class Preprocessor(CommonWorker):
    """SightHouse preprocessor worker"""


class Compiler(CommonWorker):
    """SightHouse compiler worker"""

    @staticmethod
    def validate_compiler_variants(
        data: Dict[str, Dict[str, Any]],
    ) -> List[Tuple[str, Dict[str, str]]]:
        """
        Validate compiler_variants structure.

        Args:
            data (dict): Dictionary of compiler_variants to validate.

        Returns:
            list[tuple[str, str]]: The list of compiler_variants.

        """
        # Check top-level key
        if not isinstance(data, dict) or "compiler_variants" not in data:
            raise ValueError(
                "YAML must contain a 'compiler_variants' list at the top level."
            )

        compiler_variants = data["compiler_variants"]
        if not isinstance(compiler_variants, dict):
            raise ValueError("'compiler_variants' must be a dict.")

        result: List[Tuple[str, Dict[str, str]]] = []
        # Validate each entry
        for idx, name in enumerate(compiler_variants, start=1):
            variant = compiler_variants[name]
            if not isinstance(variant, dict):
                raise ValueError(f"Variant #{idx} is not a dictionary.")

            required_fields = {"cc", "cflags"}
            missing = required_fields - set(variant.keys())
            if missing:
                raise ValueError(
                    f"Variant #{idx} is Missing required fields: {missing}."
                )

            for key in required_fields:
                if not isinstance(variant[key], str):
                    raise ValueError(f"Variant #{idx} must contain a key/value string")

            result.append((name, variant))

        return result

    def pack_and_send_task(  # type: ignore[override]
        self,
        job: Job,
        files: Sequence[Union[Path, str]],
        metadata: List[Tuple[str, str]],
        name: Optional[str] = None,
        step: Optional[str] = None,
    ) -> None:
        """
        Wrapper method that will pack the given files into an archive, upload it onto the
        worker repository and send the given Job to the next worker in the execution chain.

        Params:
            job: (Job): The job to update and send
            files (Sequence[Union[Path, str]]): List of path like to upload
            metadata (List[Tuple[str, str]]): List of metadata to send to the analyzer
            name (Optional[str]): Optional name for the packed files
            step (Optional[str]): Optional substep to target a specific step
        """
        job.job_data.update({"metadata": metadata})
        super().pack_and_send_task(job, files, name=name, step=step)


class Analyzer(CommonWorker):
    """SightHouse analyzer worker"""
