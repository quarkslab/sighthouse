from typing import List, Dict
from pathlib import Path
import subprocess
import platform
import argparse
import sys
import os


def die(msg: str) -> None:
    print(f"Error: {msg}")
    exit(1)


def in_venv() -> bool:
    return sys.prefix != sys.base_prefix


def get_ida_venv(install_dir: Path) -> Path:
    venv_dir: Path = install_dir / "venv"
    return venv_dir


def get_venv_exe(venv_dir: Path) -> str:
    win_python_cmd: str = str(venv_dir / "Scripts" / "python.exe")
    linux_python_cmd: str = str(venv_dir / "bin" / "python3")
    return win_python_cmd if platform.system() == "Windows" else linux_python_cmd


def copy_client_script_to_idadir(idadir: Path) -> None:
    print(f"Installing Sighthouse client script to '{idadir}'")
    plugin_dir = idadir / "plugins"
    if not plugin_dir.exists() or not plugin_dir.is_dir():
        die(f"Cannot find plugins directory inside '{idadir}'")

    client_script = Path(__file__).parent / "SightHouseClientIDA.py"
    if not client_script.exists() or not client_script.is_file():
        die("Fail to find Sighthouse client script for IDA")

    # Copy script
    with open(str(client_script), "r") as fpin:
        with open(str(idadir / "SightHouseClientIDA.py"), "w") as fpout:
            fpout.write(fpin.read())

    print("Sighthouse client script installed!")


def main(install_dir):

    # Setup variables
    python_cmd: str = sys.executable
    install_dir: Path = Path(install_dir)
    release_venv_dir = get_ida_venv(install_dir)

    # Setup the proper execution environment:
    # 1) If we are already in a virtual environment, use that
    # 2) If the IDA user settings virtual environment exists, use that
    if in_venv():
        # If we are already in a virtual environment, assume that's where the user wants to be
        print(f"Using active virtual environment: {sys.prefix}")
    elif os.path.isdir(release_venv_dir):
        # If the IDA user settings venv exists, use that
        python_cmd = get_venv_exe(release_venv_dir)
        print(f"Using IDA virtual environment: {release_venv_dir}")
    else:
        die(
            f"Cannot find IDA virtual environment. Activate your environment before running the script"
        )

    pip_args_sighthouse: List[str] = [
        "-m",
        "pip",
        "install",
        "--force-reinstall",
        "sighthouse.client",
    ]
    subprocess.check_call([python_cmd] + pip_args_sighthouse)
    copy_client_script_to_idadir(install_dir)


if __name__ == "__main__":
    main()
