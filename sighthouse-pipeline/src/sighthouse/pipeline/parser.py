"""Parser for SightHouse pipeline configuration files"""

from pathlib import Path
from typing import Set, Dict, Any, List, Optional
import yaml

from sighthouse.pipeline.worker import ExecutionStep, ExecutionChain


class WorkerConfig:
    """Represents a single worker node in the pipeline DAG."""

    MANDATORY_KEYS = {"name", "package"}
    OPTIONAL_KEYS = {"args", "target", "foreach"}

    def __init__(
        self,
        name: str,
        package: str,
        target: Optional[str] = None,
        args: Optional[Dict[str, Any]] = None,
        foreach: Optional[List[Any]] = None,
    ) -> None:
        """
        Initialize a WorkerConfig.

        Args:
            name: Unique worker name within the pipeline.
            package: WorkerConfig type/implementation identifier (e.g. 'git_scrapper').
            target: Optional name of the worker that should receive this worker's output.
            args: Arbitrary configuration arguments for this worker.
            foreach: Optional directive allowing to fanout jobs
        """
        self.name: str = name
        self.package: str = package
        self.target: Optional[str] = target
        self.args: Dict[str, Any] = args or {}
        self.foreach: Optional[List[Any]] = foreach

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkerConfig":
        """
        Create WorkerConfig from dictionary with full validation.

        Raises:
            ValueError: If keys or values are invalid.
        """
        cls._validate_keys(data)
        cls._validate_values(data)

        return cls(
            name=data["name"],
            package=data["package"],
            target=data.get("target"),
            args=data.get("args"),
            foreach=data.get("foreach"),
        )

    @classmethod
    def _validate_keys(cls, data: Dict[str, Any]) -> None:
        """Validate that all mandatory keys exist and no invalid keys are present."""
        provided_keys = set(data.keys())

        missing = cls.MANDATORY_KEYS - provided_keys
        if missing:
            raise ValueError(f"Missing mandatory keys: {', '.join(sorted(missing))}")

        invalid = provided_keys - (cls.MANDATORY_KEYS | cls.OPTIONAL_KEYS)
        if invalid:
            raise ValueError(f"Invalid keys found: {', '.join(sorted(invalid))}")

    @classmethod
    def _validate_values(cls, data: Dict[str, Any]) -> None:
        """Validate values for mandatory and optional fields."""
        # Mandatory: non-empty strings
        for key in cls.MANDATORY_KEYS:
            value = data[key]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"Field '{key}' must be a non-empty string, got: {repr(value)}"
                )

        # Optional target: if present, must be non-empty string
        if "target" in data:
            value = data["target"]
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(
                    f"Field 'target' must be a non-empty string when provided, got: {repr(value)}"
                )

        # Optional foreach: if present, must be non-empty list
        if "foreach" in data:
            value = data["foreach"]
            if value is not None and (not isinstance(value, list) or len(value) == 0):
                raise ValueError(
                    f"Field 'foreach' must be a non-empty list when provided, got: {repr(value)}"
                )

    def to_dict(self) -> Dict[str, Any]:
        """Convert this worker into a serializable dictionary."""
        result: Dict[str, Any] = {
            "name": self.name,
            "package": self.package,
            "args": self.args,
        }
        if self.target is not None:
            result["target"] = self.target
        if self.foreach is not None:
            result["foreach"] = self.foreach
        return result

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}"
            "(name='{self.name}', package='{self.package}', target='{self.target}')"
        )


class PipelineConfig:
    """Pipeline configuration representing a DAG of workers."""

    def __init__(
        self, name: str, description: str, workers: List[WorkerConfig]
    ) -> None:
        """
        Initialize a PipelineConfig.

        Args:
            name: Name of the pipeline.
            description: Human-readable description of the pipeline.
            workers: List of WorkerConfig objects that form the DAG.

        Raises:
            ValueError: If the graph is invalid (e.g., missing targets).
        """
        self.name: str = name
        self.description: str = description
        self.workers: List[WorkerConfig] = workers
        self._validate_graph()

    @classmethod
    def load(cls, path: Path | str) -> "PipelineConfig":
        """
        Load and parse pipeline configuration from a YAML file.

        Args:
            path: Path to the pipeline YAML file, as a Path or str.

        Returns:
            A validated PipelineConfig instance.

        Raises:
            FileNotFoundError: If the file does not exist.
            yaml.YAMLError: If YAML parsing fails.
            ValueError: If the structure or DAG is invalid.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Pipeline file not found: {path}")

        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError("Root of YAML document must be a mapping (dictionary).")

        cls._validate_top_level(data)

        name = data.get("name", "unnamed")
        description = data.get("description", "")
        workers_data = data.get("workers", [])

        if not workers_data:
            raise ValueError("No workers defined in pipeline configuration.")

        workers = [WorkerConfig.from_dict(w) for w in workers_data]

        names = [w.name for w in workers]
        duplicates = [n for n in set(names) if names.count(n) > 1]
        if duplicates:
            raise ValueError(
                f"Duplicate worker names found: {', '.join(sorted(duplicates))}"
            )

        return cls(name=name, description=description, workers=workers)

    @classmethod
    def _validate_top_level(cls, data: Dict[str, Any]) -> None:
        """Validate top-level YAML structure."""
        allowed_keys = {"name", "description", "workers"}
        invalid_keys = set(data.keys()) - allowed_keys
        if invalid_keys:
            raise ValueError(
                f"Invalid top-level keys: {', '.join(sorted(invalid_keys))}"
            )

    def _validate_graph(self) -> None:
        """
        Validate the worker graph structure.

        Checks:
            - All non-null 'target' values refer to an existing worker name.
            - No self-references (worker targeting itself).
        """
        worker_names = {w.name for w in self.workers}
        targets = {w.target for w in self.workers if w.target is not None}

        missing = targets - worker_names
        if missing:
            raise ValueError(
                f"Targets not found in workers: {', '.join(sorted(missing))}"
            )

        for worker in self.workers:
            if worker.target is not None and worker.target == worker.name:
                raise ValueError(
                    f"Self-reference detected: {worker.name} targets itself"
                )

    @property
    def roots(self) -> List[WorkerConfig]:
        """
        Return the root workers in the DAG.

        Roots are workers that have no incoming edge (no other worker targets them).
        """
        incoming = {w.target for w in self.workers if w.target is not None}
        return [w for w in self.workers if w.name not in incoming]

    def to_dict(self) -> Dict[str, Any]:
        """Convert the entire pipeline configuration to a serializable dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "workers": [w.to_dict() for w in self.workers],
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}', workers={len(self.workers)})"

    def create_execution_chain(self, name: str) -> "ExecutionChain":
        """
        Create a flattened ExecutionChain object for a root worker
        with a numbered execution sequence.

        Args:
            name: Name of the root worker.

        Returns:
            ExecutionChain: The generated execution chain for the given root.

        Raises:
            ValueError: If the root worker cannot be found,
                        or if cycles / invalid targets exist.
        """
        # Find the root worker
        root = next((w for w in self.roots if w.name == name), None)
        if root is None:
            raise ValueError(f"Cannot find '{name}' worker")

        def build_execution_chain(
            current: WorkerConfig, chain: List[WorkerConfig], visited: Set[str]
        ):
            """Recursively build flat chain by following 'target' links."""
            if current.name in visited:
                raise ValueError(f"Cycle detected at worker '{current.name}'")

            visited.add(current.name)
            chain.append(current)

            if current.target:
                next_worker = next(
                    (w for w in self.workers if w.name == current.target), None
                )
                if next_worker is None:
                    raise ValueError(f"Target '{current.target}' not found")

                build_execution_chain(next_worker, chain, visited)

        # Step 1: Build the flattened list of workers in order
        execution_order: List[WorkerConfig] = []
        build_execution_chain(root, execution_order, set())

        steps: List[ExecutionStep] = []
        for i, worker in enumerate(execution_order, start=1):
            base_step = str(i)
            if worker.foreach:
                for j, foreach_args in enumerate(worker.foreach, start=1):
                    step_number = f"{base_step}.{j}"
                    steps.append(
                        ExecutionStep(
                            package=worker.package, args=foreach_args, step=step_number
                        )
                    )
            else:
                steps.append(
                    ExecutionStep(
                        package=worker.package, args=worker.args, step=base_step
                    )
                )

        # Step 2: Return ExecutionChain object
        return ExecutionChain(execution_steps=steps, current_step="1")
