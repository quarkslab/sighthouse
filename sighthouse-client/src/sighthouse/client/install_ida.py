"""Install the SightHouse client plugin for IDA Pro.

IDA does not ship (or use) a virtual environment. IDAPython embeds whatever
Python shared library was selected with ``idapyswitch`` (stored as
``Python3TargetDLL`` in the IDA registry) and adds that interpreter's
site-packages to ``sys.path``. This installer therefore:

1. finds the Python interpreter IDA is configured to use,
2. pip-installs ``sighthouse.client`` into it, and
3. copies the plugin script into the IDA *user* plugins directory.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
from argparse import ArgumentParser
from pathlib import Path

PLUGIN_SCRIPT = "SightHouseClientIDA.py"
PACKAGE = "sighthouse.client"
REGISTRY_KEY = "Python3TargetDLL"


class InstallError(Exception):
    pass


# ---------------------------------------------------------------------------
# IDA user directory
# ---------------------------------------------------------------------------


def get_ida_user_dir() -> Path:
    """Return the IDA user directory (where ida.reg, plugins/, ... live)."""
    if idausr := os.environ.get("IDAUSR"):
        # IDAUSR may hold several directories; IDA writes to the first one
        return Path(idausr.split(os.pathsep)[0]).expanduser()
    if platform.system() == "Windows":
        return Path(os.environ["APPDATA"]) / "Hex-Rays" / "IDA Pro"
    return Path.home() / ".idapro"


# ---------------------------------------------------------------------------
# Locate the Python library selected with idapyswitch
# ---------------------------------------------------------------------------


def _read_ida_reg(reg_file: Path) -> str | None:
    """Read Python3TargetDLL from IDA's ida.reg file (macOS / Linux).

    Entry layout: ``<name>\\0 <u32 LE size> <u8 type> <value[size]>``.
    """
    try:
        data = reg_file.read_bytes()
    except OSError:
        return None
    marker = REGISTRY_KEY.encode() + b"\x00"
    if (idx := data.find(marker)) == -1:
        return None
    idx += len(marker)
    if idx + 5 > len(data):
        return None
    (size,) = struct.unpack_from("<I", data, idx)
    value = data[idx + 5 : idx + 5 + size]
    return value.rstrip(b"\x00").decode("utf-8", errors="replace") or None


def _read_windows_registry() -> str | None:
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Hex-Rays\IDA") as key:
            value, _ = winreg.QueryValueEx(key, REGISTRY_KEY)
            return str(value) or None
    except OSError:
        return None


def _find_key(obj: object, key: str) -> str | None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key and isinstance(v, str):
                return v
            if (found := _find_key(v, key)) is not None:
                return found
    return None


def _read_ida_config_json(user_dir: Path) -> str | None:
    """Fallback: idapyswitch also records the library in ida-config.json (idalib)."""
    try:
        config = json.loads((user_dir / "ida-config.json").read_text())
    except (OSError, ValueError):
        return None
    return _find_key(config, REGISTRY_KEY)


def get_ida_python_library(user_dir: Path) -> Path | None:
    """Return the Python shared library IDA is configured to load, if known."""
    value = (
        _read_windows_registry()
        if platform.system() == "Windows"
        else _read_ida_reg(user_dir / "ida.reg")
    ) or _read_ida_config_json(user_dir)
    return Path(value) if value else None


# ---------------------------------------------------------------------------
# Map that library to an interpreter
# ---------------------------------------------------------------------------


def _library_version(lib: Path) -> str | None:
    """Extract 'X.Y' from a Python library path."""
    # macOS framework: .../Python.framework/Versions/3.14/Python
    if lib.name == "Python" and lib.parent.parent.name == "Versions":
        return lib.parent.name
    # libpython3.12.so.1.0 / libpython3.12.dylib / python312.dll
    if m := re.search(r"python(\d)\.?(\d+)", lib.name, re.IGNORECASE):
        return f"{m[1]}.{m[2]}"
    return None


def candidate_interpreters(lib: Path) -> list[Path]:
    """Guess interpreter paths that belong to the given Python library."""
    version = _library_version(lib)
    if platform.system() == "Windows":
        return [lib.parent / "python.exe"]

    names = [f"python{version}", "python3"] if version else ["python3"]
    candidates: list[Path] = []
    # Walk up from the library: <prefix>/lib[/<multiarch>]/libpython... or
    # <framework>/Versions/X.Y/Python -> look for <dir>/bin/pythonX.Y
    for parent in lib.parents:
        candidates.extend(parent / "bin" / name for name in names)
    return candidates


def _interpreter_version(python: Path) -> str | None:
    try:
        out = subprocess.run(
            [str(python), "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip()


def resolve_ida_python(user_dir: Path) -> Path:
    lib = get_ida_python_library(user_dir)
    if lib is None:
        raise InstallError(
            "Cannot find which Python IDA uses (no Python3TargetDLL in the IDA registry). "
            "Run IDA's 'idapyswitch' once, or pass --python /path/to/python."
        )
    print(f"IDA is configured to load Python library: {lib}")
    expected = _library_version(lib)
    for candidate in candidate_interpreters(lib):
        if not candidate.is_file():
            continue
        version = _interpreter_version(candidate)
        if version and (expected is None or version == expected):
            return candidate
    raise InstallError(
        f"Cannot find a Python {expected or ''} interpreter matching '{lib}'. "
        "Pass --python /path/to/python explicitly."
    )


# ---------------------------------------------------------------------------
# Install steps
# ---------------------------------------------------------------------------


def _is_externally_managed(python: Path) -> bool:
    code = (
        "import sysconfig, pathlib; "
        "print((pathlib.Path(sysconfig.get_path('stdlib')) / 'EXTERNALLY-MANAGED').is_file())"
    )
    try:
        out = subprocess.run(
            [str(python), "-c", code], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    return out.stdout.strip() == "True"


def install_package(python: Path, break_system_packages: bool, dry_run: bool) -> None:
    cmd = [str(python), "-m", "pip", "install", "--upgrade", PACKAGE]
    if _is_externally_managed(python):
        if not break_system_packages:
            raise InstallError(
                f"'{python}' is an externally managed environment (PEP 668), so pip refuses "
                "to install into it. Either point IDA at another Python with 'idapyswitch', "
                "or re-run with --break-system-packages."
            )
        cmd.append("--break-system-packages")
    print(f"Installing {PACKAGE} into IDA's Python: {python}")
    print("  $ " + " ".join(cmd))
    if not dry_run:
        subprocess.check_call(cmd)


def copy_client_script(plugins_dir: Path, dry_run: bool) -> None:
    client_script = Path(__file__).parent / PLUGIN_SCRIPT
    if not client_script.is_file():
        raise InstallError(
            f"Cannot find the SightHouse IDA plugin script ({client_script})"
        )
    print(f"Installing SightHouse plugin to '{plugins_dir / PLUGIN_SCRIPT}'")
    if not dry_run:
        plugins_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(client_script, plugins_dir / PLUGIN_SCRIPT)


def main(
    ida_dir: str | None = None,
    python: str | None = None,
    break_system_packages: bool = False,
    dry_run: bool = False,
) -> None:
    """Install the SightHouse IDA plugin.

    ``ida_dir`` is optional and only used as a sanity check: the plugin goes in
    the IDA user directory ($IDAUSR, ~/.idapro or %APPDATA%\\Hex-Rays\\IDA Pro),
    which survives IDA upgrades and does not need admin rights.
    """
    if ida_dir is not None and not Path(ida_dir).expanduser().exists():
        raise InstallError(f"IDA directory not found: {ida_dir}")

    user_dir = get_ida_user_dir()
    python_path = Path(python).expanduser() if python else resolve_ida_python(user_dir)
    if not python_path.is_file():
        raise InstallError(f"Python interpreter not found: {python_path}")

    install_package(python_path, break_system_packages, dry_run)
    copy_client_script(user_dir / "plugins", dry_run)
    print("SightHouse IDA plugin installed! Restart IDA to load it.")


def add_arguments(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--ida-dir",
        default=os.environ.get("IDA_DIR"),
        help="IDA installation directory (optional, defaults to $IDA_DIR)",
    )
    parser.add_argument(
        "--python",
        default=None,
        help="Python interpreter IDA uses (default: detected from idapyswitch settings)",
    )
    parser.add_argument(
        "--break-system-packages",
        action="store_true",
        help="Allow pip to install into an externally managed Python (PEP 668)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without doing it",
    )


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__.splitlines()[0])
    add_arguments(parser)
    args = parser.parse_args()
    try:
        main(args.ida_dir, args.python, args.break_system_packages, args.dry_run)
    except InstallError as exc:
        sys.exit(f"Error: {exc}")
    except KeyboardInterrupt:
        sys.exit("\nInterrupted")
