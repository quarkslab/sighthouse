"""Handle SightHouse pipeline packages"""

from importlib.util import spec_from_file_location, module_from_spec
from importlib.metadata import PackageNotFoundError
from typing import Set, Dict, Callable, List, Optional, Any
from traceback import format_exception
from logging import Logger
from pathlib import Path
import tempfile
import tarfile
import shutil
import sys

import yaml
from sighthouse.core.utils import get_appdata_dir, run_process
from sighthouse.pipeline.worker import CommonWorker, Job


class MonkeyPatchWorker:
    """Hacky patch to simulate a worker processing a single job

    note: This class is used as a context manager and is not thread safe
    """

    def __init__(self, job: Optional[Job]):
        self._job = job
        self._worker_run: Optional[Callable[[CommonWorker, int], None]] = None

    def __enter__(self):
        # @WARNING: This method will give unexpected result if used in a multithread

        if self._job:
            # Patch workers to run only a single job
            self._worker_run = CommonWorker.run
            CommonWorker.run = lambda obj: self.__run(obj, self._job)  # type: ignore
        return self

    def __run(self, obj: CommonWorker, job: Job) -> None:
        job.job_metadata.update({"id": "fakejob"})
        try:
            obj.do_work(job)
            job.job_metadata.update({"state": "success"})
        except Exception as e:
            error = "".join(format_exception(e))
            job.job_metadata.update({"state": "failed", "error": error})

        obj._on_task_success(
            sender=type("FakeSender", (object,), {"name": "FakeSender"})(),
            result=job.to_dict(),
        )

    def __exit__(self, exception_type, exception_value, exception_traceback):
        if self._job:
            CommonWorker.run = self._worker_run  # type: ignore


class PackageMetadata:
    """
    Represents package metadata loaded from package.yml.

    Attributes:
        name (str): The package's name.
        description (str): A short description of the package.
        author (str): Author of the package.
        license (str): License string.
        version (str): Version of the package.
        requirements (List[str]): List of pip requirements.
        path (Path): Filesystem path where the package is located.
    """

    def __init__(
        self,
        name: str,
        description: str = "",
        author: str = "",
        license: str = "",
        version: str = "1.0.0",
        requirements: Optional[List[str]] = None,
        path: Optional[Path] = None,
    ):
        self.name = name
        self.description = description
        self.author = author
        self.license = license
        self.version = version
        self.requirements = requirements or []
        self.path = path

    def __eq__(self, other: Any) -> bool:
        """Compare this object to something else"""
        if not isinstance(other, type(self)):
            raise NotImplementedError("Comparing to a different type is not allowed")

        return self.name == other.name and self.version == other.version

    def __repr__(self) -> str:
        """
        Return detailed representation of the package metadata.
        """
        return (
            f"{self.__class__.__name__}(name='{self.name}', version='{self.version}',"
            f" author='{self.author}', requirements={self.requirements})"
        )

    def __str__(self) -> str:
        """
        Return a human-friendly string representation.
        """
        return f"{self.name} v{self.version} by {self.author}"


class PackageLoader:
    """
    Package loader that can load, install, uninstall, and list user packages.
    """

    DEFAULT_PACKAGE_PATH = get_appdata_dir() / "packages"

    def __init__(self, logger: Logger, paths: Optional[List[Path | str]] = None):
        """
        Initialize the package loader.

        Args:
            logger (Logger): Logger for debug/info messages.
            paths (list[Path|str], optional): Additional directories to search for packages.

        Raises:
            TypeError: If provided paths is not a list.
            ValueError: If any given path is invalid.
        """
        if paths is not None and not isinstance(paths, list):
            raise TypeError("Invalid path list for module loader")

        paths_: List[Path] = []
        for path in paths or []:
            if isinstance(path, str):
                path = Path(path)
            if not isinstance(path, Path) or not path.exists() or not path.is_dir():
                raise ValueError("Invalid directory for module loader")

            paths_.append(path)

        self._paths: List[Path] = paths_
        # Allow to nop the default package path
        if self.DEFAULT_PACKAGE_PATH is not None:
            self._paths.insert(0, self.DEFAULT_PACKAGE_PATH)
            self.DEFAULT_PACKAGE_PATH.mkdir(exist_ok=True, parents=True)

        self._logger = logger
        self._metadata: dict[str, PackageMetadata] = {}

    def __pip_supports_break_system_packages(self) -> bool:
        _, stdout, _ = run_process(
            [sys.executable, "-m", "pip", "install", "--help"], capture_output=True
        )
        return b"--break-system-packages" in stdout

    def _install_package_requirement(self, name: str) -> bool:
        """
        Install a Python package requirement via pip.

        Args:
            name (str): Name of the pip package.

        Returns:
            bool: True if installation succeeded, False otherwise.
        """
        cmd = [sys.executable, "-m", "pip", "--no-input", "install", name]
        if self.__pip_supports_break_system_packages():
            cmd.insert(-1, "--break-system-packages")

        returncode, stdout, stderr = run_process(cmd, capture_output=True)
        if returncode != 0:
            self._logger.warning(f"Fail to install packages ({returncode})")
            self._logger.warning(
                "Here is the backlog:\n" + stdout.decode() + stderr.decode()
            )
            return False

        return True

    def load_metadata(self, path: Path) -> Optional[PackageMetadata]:
        """
        Load package.yml metadata if present.
        Always return a PackageMetadata object if possible.

        Args:
            path (Path): Directory containing the package.

        Returns:
            PackageMetadata | None: The parsed metadata, or None if not found or invalid.
        """
        metadata_path = path / "package.yml"
        data: Dict[str, Any] = {}
        if metadata_path.exists() and metadata_path.is_file():
            try:
                with open(metadata_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                self._logger.debug(f"Loaded metadata for module in '{path}'")
            except Exception as e:
                self._logger.warning(f"Failed to parse metadata for '{path}': {e}")
                return None
        else:
            self._logger.error(f"No metadata file found for in '{path}'")
            return None

        pkg_meta = PackageMetadata(
            name=data.get("name", path.name),
            description=data.get("description", ""),
            author=data.get("author", ""),
            license=data.get("license", ""),
            version=data.get("version", "1.0.0"),
            requirements=data.get("requirements", []),
            path=path,
        )

        return pkg_meta

    def get_metadata(self, name: str) -> Optional[PackageMetadata]:
        """
        Get previously loaded/scanned PackageMetadata for a module.

        Args:
            name (str): Name of the module.

        Returns:
            PackageMetadata | None
        """
        if name in self._metadata:
            self._logger.debug(f"Using cached element for '{name}'")
            return self._metadata[name]

        paths_seen = {e.path for e in self._metadata.values()}
        for p in self._paths:
            for path in p.iterdir():
                if path.is_dir() and path not in paths_seen:
                    # Parsing metadata automatically add them in the list
                    meta = self.load_metadata(path)
                    if meta and meta.name == name:
                        self._logger.debug(f"Found package {name}")
                        return meta

        self._logger.debug(f"Package '{name}' not found")
        return None

    def _load_module(
        self, path: Path, args: List[str], job: Optional[Job] = None
    ) -> bool:
        """
        Load a Python module from disk.

        Args:
            path (Path): Path to the Python file to load.
            args (list[str]): The argument for the package
            job: (Optional[Job]): Optional job data to process

        Returns:
            bool: True if loaded successfully, False otherwise.
        """
        if str(path.parent) not in sys.path:
            sys.path.append(str(path.parent.absolute()))
            self._logger.debug(
                f"Adding '{path.parent.absolute()}' to sys.path to fix relative import"
            )
        spec = spec_from_file_location(path.stem, path)
        if spec is None or spec.loader is None:
            self._logger.warning(
                f"Fail to load module specification from path: '{path}'"
            )
            return False

        module = module_from_spec(spec)
        # Save argv
        saved_argv = list(sys.argv)
        try:
            # Modify sys.argv to make ArgumentParser behave as if the module
            # was simply run using `python3 __init__.py ...`
            sys.argv = [str(path)] + args
            with MonkeyPatchWorker(job) as _:
                spec.loader.exec_module(module)
            # Restore argv
            sys.argv = saved_argv
            return True
        except PackageNotFoundError as e:
            self._logger.warning(
                f"Package {e.name} is missing, please install it if "
                f"you plan to use the package '{path.parent.stem}'"
            )
        except Exception as e:
            self._logger.warning(
                f"Exception occurred while loading the package {path.parent.stem}"
            )
            self._logger.warning("".join(format_exception(e)))
        # Restore argv
        sys.argv = saved_argv
        return False

    def _check(
        self,
        path: Path,
        args: Optional[List[str]] = None,
        quick: bool = False,
        job: Optional[Job] = None,
    ) -> bool:
        """
        Validate the given package path.

        Args:
            path (Path): Package directory.
            args (Optional[List[str]]): The argument for the package
            quick (bool): Whether to check only metadata and init.py presence.
            job: (Optional[Job]): Optional job data to process

        Returns:
            bool: True if valid, False otherwise.
        """
        meta = self.load_metadata(path)
        if not meta:
            self._logger.debug(f"Failed to load {path}")
            return False

        entry = path / "__init__.py"
        if not entry.exists() or not entry.is_file():
            self._logger.debug(f"No __init__.py in '{path.name}'")
            return False

        if quick:
            return True

        if meta.requirements:
            self._logger.debug(
                f"Installing requirements from package.yml for '{meta.name}'"
            )
            for req in meta.requirements:
                if not self._install_package_requirement(req):
                    self._logger.warning(f"Failed to install '{req}' for '{meta.name}'")
                    return False

        self._logger.debug(f"Attempting to load module '{meta.name}'")
        if not self._load_module(entry, args or [], job=job):
            return False

        self._logger.debug(f"Package '{meta.name}' loaded successfully")
        return True

    def install(
        self, source: Path | str, overwrite: bool = False, quick_check: bool = True
    ) -> bool:
        """
        Install a module from a directory or a .tar.gz archive.

        Args:
            source (Path | str): Path to the source directory or .tar.gz file
                                 containing the package.
            overwrite (bool): Whether to overwrite existing installation.
            quick_check (bool): Perform quick validation (metadata only) if True.
        """
        if isinstance(source, str):
            source = Path(source)

        temp_dir = None

        # If it's a tar.gz file, extract it
        if (
            source.exists()
            and source.is_file()
            and source.suffixes[-2:] == [".tar", ".gz"]
        ):
            try:
                temp_dir = Path(tempfile.mkdtemp(prefix="pkg_install_"))
                with tarfile.open(source, "r:gz") as tar:
                    tar.extractall(temp_dir)
                # Assume archive has a single top-level folder (the package folder)
                extracted_items = list(temp_dir.iterdir())
                if len(extracted_items) != 1 or not extracted_items[0].is_dir():
                    self._logger.error(f"Invalid archive structure for '{source}'")
                    shutil.rmtree(temp_dir)
                    return False
                source = Path(extracted_items[0])
                self._logger.debug(f"Extracted archive '{source.name}' to '{temp_dir}'")
            except Exception as e:
                self._logger.error(f"Failed to extract archive '{source}': {e}")
                if temp_dir and temp_dir.exists():
                    shutil.rmtree(temp_dir)
                return False

        # Validate source path
        if not source.exists() or not source.is_dir():
            self._logger.error(
                f"Install failed: source path '{source}' is not a valid directory."
            )
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir)
            return False

        # Run validation
        self._logger.debug(f"Validating module '{source.name}' before install.")
        if not self._check(source, quick=quick_check):
            self._logger.error(
                f"Module '{source.name}' failed validation. Installation aborted."
            )
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir)
            return False

        # Metadata is not None at this point
        metadata = self.load_metadata(source)
        assert metadata is not None

        # Determine destination in main path
        module_name = metadata.name
        dest_dir = self._paths[0] / module_name

        # Handle overwrite
        if dest_dir.exists():
            if not overwrite:
                self._logger.error(
                    f"Install failed: '{module_name}' already exists at {dest_dir}"
                )
                if temp_dir and temp_dir.exists():
                    shutil.rmtree(temp_dir)
                return False

            self._logger.warning(
                f"Overwriting existing module '{module_name}' at {dest_dir}"
            )
            shutil.rmtree(dest_dir)

        try:
            shutil.copytree(source, dest_dir)
            self._logger.info(
                f"Module '{module_name}' installed successfully into {dest_dir}"
            )
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir)

            # Update package location now that it is installed
            metadata.path = dest_dir
            self._metadata[metadata.name] = metadata
            return True
        except Exception as e:
            self._logger.error(f"Error while installing module '{module_name}': {e}")
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir)
            return False

    def export_package(self, name: str, destination: Path | str) -> bool:
        """
        Export a package directory as a .tar.gz file.

        Args:
            name (str): Name of the package to export.
            destination (Path | str): Path to save the exported archive (should end with .tar.gz).

        Returns:
            bool: True if exported successfully, False otherwise.
        """
        if isinstance(destination, str):
            destination = Path(destination)

        meta = self.get_metadata(name)
        if meta is None or meta.path is None:
            return False

        if destination.suffixes[-2:] != [".tar", ".gz"]:
            self._logger.warning(
                "Destination does not end with .tar.gz, adding extension automatically."
            )
            destination = destination.with_suffix(".tar.gz")

        try:
            with tarfile.open(destination, "w:gz") as tar:
                tar.add(meta.path, arcname=meta.path.name)

            self._logger.info(
                f"Package '{name}' exported successfully to '{destination}'"
            )
            return True
        except Exception as e:
            self._logger.error(f"Failed to export package '{name}': {e}")
            return False

    def run(
        self, name: str, args: Optional[List[str]] = None, job: Optional[Job] = None
    ) -> bool:
        """
        Attempt to run (load) a given package by name.

        Args:
            name (str): Package name.
            args (Optional[List[str]]): The argument for the package
            job: (Optional[Job]): Optional job data to process
        """
        meta = self.get_metadata(name)
        if meta is not None and meta.path is not None:
            return self._check(meta.path, args=args, job=job)

        self._logger.debug("Couldn't found metadata")
        return False

    def uninstall(self, name: str) -> bool:
        """
        Uninstall the given package if it exists.
        """
        meta = self.get_metadata(name)
        if meta and meta.path:
            shutil.rmtree(meta.path)
            return True

        return False

    def list_modules(self) -> List[PackageMetadata]:
        """
        Return list of PackageMetadata objects without fully loading modules.
        """
        results: List[PackageMetadata] = []
        for p in self._paths:
            for path in p.iterdir():
                if path.is_dir():
                    meta = self.load_metadata(path)
                    if meta:
                        results.append(meta)
        return results
