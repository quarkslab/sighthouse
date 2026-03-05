"""Generic helpers"""

from typing import Any, List, Dict, Tuple, Union, Optional, Sequence
from urllib.parse import urlparse, unquote, ParseResult
from subprocess import Popen, PIPE
from threading import Timer
from hashlib import sha256
from pathlib import Path
from io import BytesIO
import tarfile
import functools
import sys
import os
import zipfile

import requests


@functools.cache
def parse_uri(uri: str) -> Dict[str, Any]:
    """Parse an uri and return it's components"""
    parsed: ParseResult = urlparse(uri)
    kind: str = parsed.scheme
    path: str = ""
    data: Dict[str, Any] = {"type": kind}

    if kind == "sqlite":
        if parsed.netloc == ":memory:" or parsed.path == "/:memory:":
            data.update({"database": ":memory:"})
            return data

        # Handle relative or absolute paths
        if parsed.netloc:  # sqlite://localhost/path.db
            path = f"/{parsed.netloc}{parsed.path}"
        else:  # sqlite:///path.db
            path = parsed.path

        path = unquote(
            path[1:] if path[0] == "/" else path
        )  # remove leading slash for relative paths on Unix
        data.update({"database": Path(path).absolute()})

    elif kind in ["postgres", "postgresql"]:
        # Normalize type
        data.update(
            {
                "type": "postgresql",
                "dbname": parsed.path.lstrip("/"),
                "user": parsed.username,
                "password": parsed.password,
                "host": parsed.hostname,
                "port": parsed.port or 5432,
            }
        )

    elif kind in ["elastic"]:
        data.update(
            {
                "dbname": parsed.path.lstrip("/"),
                "user": parsed.username,
                "password": parsed.password,
                "host": parsed.hostname,
                "port": parsed.port or 5432,
            }
        )

    elif kind == "mysql":
        data.update(
            {
                "dbname": parsed.path.lstrip("/"),
                "user": parsed.username,
                "password": parsed.password,
                "host": parsed.hostname,
                "port": parsed.port or 3306,
            }
        )

    elif kind == "local":
        # Handle relative or absolute paths
        if parsed.netloc:  # local://path/to/path.db
            path = unquote(f"{parsed.netloc}{parsed.path}")
        else:  # local:///path.db
            # Remove leading slash for relative paths on Unix
            path = unquote(parsed.path)

        data.update({"database": Path(path).absolute()})

    elif kind == "s3":
        path = parsed.path.lstrip("/")
        if "/" in path:
            # There is a least one '/', safe to split
            bucket, directory = path.split("/", 1)
        else:
            # No directory, use root
            bucket, directory = path, "/"

        # Append leading '/' if needed
        if not directory.startswith("/"):
            directory = "/" + directory

        data.update(
            {
                "dbname": bucket,
                "directory": directory,
                "user": parsed.username,
                "password": parsed.password,
                "host": parsed.hostname,
                "port": parsed.port or 9000,
            }
        )

    else:
        raise ValueError(f"Unsupported URI scheme: {kind}")

    return data


def download_file(url: str, timeout: int = 3600) -> Optional[BytesIO]:
    """
    Download a file from the given URL and return a file-like object containing its content.
    Returns None if the URL is not valid or if an error occurs during the download.

    Args:
        url (str): The URL of the file to be downloaded
        timeout (int): Timeout in seconds

    Returns:
        Optional[BytesIO]: A BytesIO object containing the file's content, or None
                           if an error occurred or the input was invalid
    """
    if not isinstance(url, str):
        return None

    try:
        req = requests.get(url, timeout=timeout)
        if req.status_code == 200:
            return BytesIO(req.content)
    except requests.exceptions.ConnectionError:
        pass

    return None


def extract_tar(file: str | Path | BytesIO | bytes, to: Path) -> bool:
    """
    Unpack a tar file into the given directory.

    Args:
        file (Union[str, Path, BytesIO, bytes]): The source of the tar archive.
                                                  Can be a file path as string or Path object,
                                                  a BytesIO object, or raw bytes data.
        to (Path): The destination directory where files will be extracted

    Returns:
        bool: True on success and False otherwise
    """
    try:
        if isinstance(file, BytesIO):
            tar = tarfile.open(fileobj=file)
        elif isinstance(file, str):
            tar = tarfile.open(file)
        elif isinstance(file, Path):
            tar = tarfile.open(str(file))
        elif isinstance(file, bytes):
            tar = tarfile.open(fileobj=BytesIO(file))
        else:
            return False

        _safe_extract_tar(tar, to)
        tar.close()
        return True
    except tarfile.ReadError:
        pass

    return False


def create_tar(base_name: Path, files: Sequence[Union[Path, str]]) -> BytesIO:
    """
    Create a tar.gz file containing the given files.

    Args:
        base_name (Path): The name of the resulting tar.gz file.
                          This will be used to set relative paths for each file in the archive.
        files (Sequence[Union[Path, str]]: A sequence of str or Path objects representing files to include in the tar archive

    Returns:
        BytesIO: A BytesIO object containing the tar.gz file data

    Raises:
        ValueError: If the input list is empty.
        TypeError: If the input list contain elements that are neither str or Path objects.
    """

    if len(files) == 0:
        raise ValueError("Could not get minimal paths from an empty list")

    if not all(map(lambda e: isinstance(e, Path) or isinstance(e, str), files)):
        raise TypeError("Unsupported files types")

    # Cast everything to Path
    paths: List[Path] = list(map(Path, files))

    ret = BytesIO()
    with tarfile.open(fileobj=ret, mode="w:gz") as tar:
        for file in paths:
            if base_name == file:
                # Avoid adding a file with a arcname equal to '.'
                tar.add(
                    file,
                    arcname=str(
                        file.absolute().relative_to(base_name.parent.absolute())
                    ),
                )

            else:
                tar.add(
                    file, arcname=str(file.absolute().relative_to(base_name.absolute()))
                )

    # Return at the begining of the file
    ret.seek(0)
    return ret


def run_process(
    process_args: Union[List[str], List[List[str]]],
    capture_output: bool = False,
    env: Optional[Dict[str, str]] = None,
    cwd: Optional[Union[str, Path]] = None,
    timeout: float = -1.0,
) -> Tuple[int, bytes, bytes]:
    """Run the given command(s) in new process(es).
    Supports pipes when process_args is a list of lists.

    Supports both single commands and pipes.

    Args:
        process_args: List of command argument lists. Single command: ['echo', 'aaa'].
            Pipes: [['echo', 'aaa'], ['sed', 's/a/b/g']].
        capture_output: If True, capture stdout/stderr. Otherwise print to console.
        env: Optional environment variables dictionary.
        cwd: Optional working directory.
        timeout: Timeout in seconds. -1 for no timeout.

    Returns:
        Tuple of (returncode, stdout, stderr). If capture_output is False, stdout/stderr
        are empty bytes.

    Examples:
        Single command:
            >>> run_process(['echo', 'aaa'], capture_output=True)
            (0, b'aaa\\n', b'')

        Pipeline:
            >>> run_process([['echo', 'aaa'], ['sed', 's/a/b/g']], capture_output=True)
            (0, b'bbb\\n', b'')

        With timeout:
            >>> run_process(['sleep', '10'], timeout=2, capture_output=True)
            (-9, b'', b'')
    """
    # Handle single command list as [[cmd]]
    if isinstance(process_args[0], str):
        process_args = [process_args]  # type: ignore

    procs: List[Popen] = []
    if len(process_args) == 1:
        # Single process
        kwargs: Dict[str, Any] = {"env": env, "cwd": cwd}
        if capture_output:
            kwargs.update({"stdout": PIPE, "stderr": PIPE})

        proc: Popen = Popen(process_args[0], **kwargs)
        procs.append(proc)
    else:
        # Pipes: chain with stdin=previous.stdout
        # First process
        first_kwargs: Dict[str, Any] = {"env": env, "cwd": cwd, "stdout": PIPE}
        procs.append(Popen(process_args[0], **first_kwargs))

        # Chain all subsequent processes
        for i in range(1, len(process_args)):
            kwargs = {"env": env, "cwd": cwd, "stdin": procs[i - 1].stdout}
            if i == len(process_args) - 1:
                if capture_output:
                    # Last process captures output
                    kwargs.update({"stdout": PIPE, "stderr": PIPE})
            else:
                # Middle processes continue piping
                kwargs.update({"stdout": PIPE})

            proc = Popen(process_args[i], **kwargs)
            procs.append(proc)

        # Close first process stdout to prevent deadlock
        if len(procs) > 0 and procs[0].stdout:
            procs[0].stdout.close()

    # Wait logic with timeout
    returncode: int = 0
    stdout: bytes = b""
    stderr: bytes = b""

    if timeout > 0:
        state: Dict[str, bool] = {"interrupted": False}

        # Interrupted callback
        def kill_pipeline(state) -> None:
            state["interrupted"] = True
            for proc in procs:
                proc.kill()

        timer: Timer = Timer(timeout, kill_pipeline, args=(state,))
        try:
            timer.start()
            if capture_output or len(process_args) > 1:
                stdout, stderr = procs[-1].communicate()
            returncode = procs[-1].wait()
        finally:
            timer.cancel()

        if state["interrupted"]:
            raise Exception(f"Process timeout after {timeout} seconds")
    else:
        if capture_output or len(process_args) > 1:
            stdout, stderr = procs[-1].communicate()
        returncode = procs[-1].wait()

    return (returncode, stdout or b"", stderr or b"")


def get_minimal_paths(paths: Sequence[Union[Path, str]]) -> Tuple[Path, List[Path]]:
    """Calculate the minimal common prefix path from a list of paths and return it
    along with the relative paths.

    This function finds the shortest common prefix that all provided paths share,
    then returns this common prefix as well as a list of paths made relative to this
    common prefix. This is useful for normalizing file structures or comparing paths.

    Args:
        paths Sequence[Union[Path, str]]: A sequence of string/Path objects representing path.

    Returns:
        Tuple[Path, List[Path]]: A tuple where the first element is the minimal common
                                 prefix as a Path object and the second element is a list
                                 of paths relative to this common prefix.

    Raises:
        ValueError: If the input list is empty or if there's an error in finding a valid
                    common prefix (should not occur under normal circumstances).
        TypeError: If the input list contain elements that are neither str or Path objects.
    """

    if len(paths) == 0:
        raise ValueError("Could not get minimal paths from an empty list")

    if not all(map(lambda e: isinstance(e, Path) or isinstance(e, str), paths)):
        raise TypeError("Unsupported path types")

    # Cast everything to Path
    files: List[Path] = list(map(Path, paths))

    if len(paths) == 1:
        common_prefix = Path(files[0].parent)
        return common_prefix, [files[0].relative_to(common_prefix)]

    reference = files[0]
    for i, element in enumerate(reference.parts):
        for lst in files[1:]:
            if i >= len(lst.parts) or lst.parts[i] != element:
                common_prefix = Path(*reference.parts[:i])
                return common_prefix, [p.relative_to(common_prefix) for p in files]

    raise ValueError("Could not get minimal paths from list")


def get_hash(data: bytes) -> str:
    """Compute the SHA256 of the given data"""
    return sha256(data).hexdigest()


def is_stdin_piped() -> bool:
    """Return True if stdin is piped, False otherwise"""
    return not sys.stdin.isatty()


def is_stdout_piped() -> bool:
    """Return True if stdout is piped, False otherwise"""
    return not sys.stdout.isatty()


def get_appdata_dir() -> Path:
    """Returns an OS-dependent application data directory.

    Creates the directory *and its parents* if it doesn't exist.

    Returns:
        Path: The Path to the application data directory.
    """
    # Taken from crypto-condor, thanks @jlm for the code :D
    home: Path = Path.home()

    match sys.platform:
        case "linux":
            appdata = (
                Path(os.getenv("XDG_DATA_HOME", home / ".local" / "share"))
                / "sighthouse"
            )
        case "win32" | "cygwin":
            appdata = (
                Path(os.getenv("LOCALAPPDATA", home / "AppData" / "Local"))
                / "sighthouse"
            )
        case "darwin":
            appdata = home / "Library" / "Caches" / "sighthouse"
        case _:
            raise ValueError(
                f"Unsupported platform {sys.platform}, can't get appdata directory"
            )

    if not appdata.is_dir():
        appdata.mkdir(parents=True)

    return appdata


def parse_menuconfig(path: str | Path) -> Dict[str, Optional[str]]:
    """Parse menuconfig file and return a dict containing the configuration

    Args:
        path (str, Path): The path to the configuration file.

    Returns:
        dict: A dictionary containing the options
    """
    with open(path, "r", encoding="utf-8") as fp:
        lines = [e.strip() for e in fp.readlines()]

    cfg: Dict[str, Optional[str]] = {}
    # Parse config into a dictionary
    for line in lines:
        if line.startswith("# ") and line.endswith(" is not set"):
            # Special option that we need to keep because this language is f#cking dumb
            # https://github.com/wbx-github/uclibc-ng/blob/v1.0.47/extra/config/confdata.c#L316
            name = line[2:-11].strip()
            cfg.update({name: None})  # Special value
        elif not line.startswith("#") and len(line) > 0:
            # Regular line
            key, value = line.split("=", 1)
            cfg.update({key: value})

    return cfg


def write_menuconfig(path: str | Path, options: dict) -> None:
    """Write menuconfig options into the given path in menuconfig format

    Args:
        path (str, Path): The path to the configuration file.
        options (dict): A dictionary containing the options
    """
    with open(path, "w", encoding="utf-8") as fp:
        for key, value in options.items():
            if value:
                fp.write(f"{key}={value}\n")
            else:
                # Undefined -> value is not set
                fp.write(f"# {key} is not set\n")


def _is_within_directory(base: Path, target: Path) -> bool:
    base = base.resolve()
    target = target.resolve()
    return base == target or base in target.parents


def safe_extract(archive_filename: str, extract_path: Path | str):
    extract_path = Path(extract_path)
    extract_path.mkdir(parents=True, exist_ok=True)
    resolved_base = extract_path.resolve()

    archive_path = Path(archive_filename)

    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path, "r") as zip_file:
            _safe_extract_zip(zip_file, resolved_base)

    elif tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path, "r:*") as tar:
            _safe_extract_tar(tar, resolved_base)

    else:
        raise ValueError("Unsupported archive format")


def _safe_extract_zip(zip_file: "ZipFile", extract_path: Path):  # type: ignore[name-defined]
    for info in zip_file.infolist():
        target_path = extract_path / info.filename
        resolved_target = target_path.resolve()

        if not _is_within_directory(extract_path, resolved_target):
            continue

        if info.is_dir():
            resolved_target.mkdir(parents=True, exist_ok=True)
        else:
            resolved_target.parent.mkdir(parents=True, exist_ok=True)
            with zip_file.open(info) as src, open(resolved_target, "wb") as dst:
                dst.write(src.read())


def _safe_extract_tar(tar: "Tarfile", extract_path: Path):  # type: ignore[name-defined]
    for member in tar.getmembers():
        target_path = extract_path / member.name
        resolved_target = target_path.resolve()

        if not _is_within_directory(extract_path, resolved_target):
            continue

        if member.isdir():
            resolved_target.mkdir(parents=True, exist_ok=True)

        elif member.isfile():
            resolved_target.parent.mkdir(parents=True, exist_ok=True)

            src = tar.extractfile(member)
            if src is None:
                continue

            with src, open(resolved_target, "wb") as dst:
                dst.write(src.read())
