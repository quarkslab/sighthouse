## ###
# IP: GHIDRA
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##
from argparse import ArgumentParser
import platform
import os
import sys
import subprocess
import sysconfig
import venv
from pathlib import Path
from xml.etree import ElementTree
from typing import List, Dict


def get_application_properties(install_dir: Path) -> Dict[str, str]:
    app_properties_path: Path = install_dir / "Ghidra" / "application.properties"
    props: Dict[str, str] = {}
    with open(app_properties_path, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("#") or line.startswith("!"):
                continue
            key, value = line.split("=", 1)
            if key:
                props[key] = value
    return props


def get_user_settings_dir(install_dir: Path) -> Path:
    props: Dict[str, str] = get_application_properties(install_dir)
    app_name: str = props["application.name"].replace(" ", "").lower()
    app_version: str = props["application.version"]
    app_release_name: str = props["application.release.name"]
    versioned_name: str = f"{app_name}_{app_version}_{app_release_name}"
    xdg_config_home: str = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home) / app_name / versioned_name
    if platform.system() == "Windows":
        return Path(os.environ["APPDATA"]) / app_name / versioned_name
    if platform.system() == "Darwin":
        return Path.home() / "Library" / app_name / versioned_name
    return Path.home() / ".config" / app_name / versioned_name


def in_venv() -> bool:
    return sys.prefix != sys.base_prefix


def is_externally_managed() -> bool:
    marker: Path = (
        Path(sysconfig.get_path("stdlib", sysconfig.get_default_scheme()))
        / "EXTERNALLY-MANAGED"
    )
    return marker.is_file()


def get_venv_exe(venv_dir: Path) -> str:
    win_python_cmd: str = str(venv_dir / "Scripts" / "python.exe")
    linux_python_cmd: str = str(venv_dir / "bin" / "python3")
    return win_python_cmd if platform.system() == "Windows" else linux_python_cmd


def get_ghidra_venv(install_dir: Path) -> Path:
    user_settings_dir: Path = get_user_settings_dir(install_dir)
    venv_dir: Path = user_settings_dir / "venv"
    return venv_dir


def create_ghidra_venv(venv_dir: Path) -> None:
    print(f"Creating Ghidra virtual environemnt at {venv_dir}...")
    venv.create(venv_dir, with_pip=True)


def version_tuple(v):
    filled = []
    for point in v.split("."):
        filled.append(point.zfill(8))
    return tuple(filled)


def get_package_version(python_cmd: str, package: str) -> str:
    version = None
    result = subprocess.Popen(
        [python_cmd, "-m", "pip", "show", package], stdout=subprocess.PIPE, text=True
    )
    for line in result.stdout.readlines():
        line = line.strip()
        print(line)
        key, value = line.split(":", 1)
        if key == "Version":
            version = value.strip()
    return version


def install(
    install_dir: Path, python_cmd: str, pip_args: List[str], offer_venv: bool
) -> bool:
    if offer_venv:
        ghidra_venv_choice: str = input(
            "Install into new Ghidra virtual environment (y/n)? "
        )
        if ghidra_venv_choice.lower() in ("y", "yes"):
            venv_dir = get_ghidra_venv(install_dir)
            create_ghidra_venv(venv_dir)
            python_cmd = get_venv_exe(venv_dir)
        elif ghidra_venv_choice.lower() in ("n", "no"):
            system_venv_choice: str = input("Install into system environment (y/n)? ")
            if system_venv_choice.lower() not in ("y", "yes"):
                print(
                    'Must answer "y" to the prior choices, or launch in an already active virtual environment.'
                )
                return None
        else:
            print("Please answer yes or no.")
            return None

    subprocess.check_call([python_cmd] + pip_args)
    return python_cmd


def upgrade(
    python_cmd: str, pip_args: List[str], dist_dir: Path, current_pyghidra_version: str
) -> bool:
    included_pyghidra: Path = next(dist_dir.glob("pyghidra-*.whl"), None)
    if included_pyghidra is None:
        print("Warning: included pyghidra wheel was not found", file=sys.stderr)
        return
    included_version = included_pyghidra.name.split("-")[1]
    current_version = current_pyghidra_version
    if version_tuple(included_version) > version_tuple(current_version):
        choice: str = input(
            f"Do you wish to upgrade PyGhidra {current_version} to {included_version} (y/n)? "
        )
        if choice.lower() in ("y", "yes"):
            pip_args.append("-U")
            subprocess.check_call([python_cmd] + pip_args)
            return True
        else:
            print("Skipping upgrade")
            return False


class Bundle:

    def __init__(self, file: str, system: bool, enabled: bool, active: bool):
        self.file = file
        self.system = system
        self.enabled = enabled
        self.active = active


def deserialize_bundles(settings: Path) -> List[Bundle]:
    bundles: List[Bundle] = []

    element = ElementTree.parse(str(settings))
    root = element.getroot()

    script_mgr = next(
        filter(
            lambda e: e.get("CLASS")
            == "ghidra.app.plugin.core.script.GhidraScriptMgrPlugin",
            root.iter("PLUGIN_STATE"),
        ),
        None,
    )
    if script_mgr is None:
        print("Error: Fail to parse ghidra settings")
        return bundles

    bundles_enabled: List[bool] = []
    bundles_file: List[str] = []
    bundles_system: List[bool] = []
    bundles_active: List[bool] = []

    for child in script_mgr:
        name = child.get("NAME")
        if name == "BundleHost_ENABLE":
            bundles_enabled = [e.get("VALUE") == "true" for e in child]
        elif name == "BundleHost_FILE":
            bundles_file = [e.get("VALUE") for e in child]
        elif name == "BundleHost_SYSTEM":
            bundles_system = [e.get("VALUE") == "true" for e in child]
        elif name == "BundleHost_ACTIVE":
            bundles_active = [e.get("VALUE") == "true" for e in child]

    if not (
        len(bundles_system)
        == len(bundles_file)
        == len(bundles_enabled)
        == len(bundles_active)
    ):
        print("Error: Number of bundles mismatch")
        return bundles

    for f, s, en, ac in zip(
        bundles_file, bundles_system, bundles_enabled, bundles_active
    ):
        bundles.append(Bundle(file=f, system=s, enabled=en, active=ac))

    return bundles


def serialize_bundles(settings: Path, bundles: List[Bundle]) -> None:
    element = ElementTree.parse(str(settings))
    root = element.getroot()

    script_mgr = next(
        filter(
            lambda e: e.get("CLASS")
            == "ghidra.app.plugin.core.script.GhidraScriptMgrPlugin",
            root.iter("PLUGIN_STATE"),
        ),
        None,
    )
    if script_mgr is None:
        print("Error: Fail to parse ghidra settings")
        return None

    enable_node = None
    file_node = None
    system_node = None
    active_node = None

    for child in script_mgr:
        name = child.get("NAME")
        kind = child.get("TYPE")
        if name == "BundleHost_ENABLE":
            enable_node = child
            child.clear()
        elif name == "BundleHost_FILE":
            file_node = child
            child.clear()
        elif name == "BundleHost_SYSTEM":
            system_node = child
            child.clear()
        elif name == "BundleHost_ACTIVE":
            active_node = child
            child.clear()

        # Add back the attributes remove by clear
        if "BundleHost_" in name:
            child.set("NAME", name)
            child.set("TYPE", kind)

    # Create node is they dont exists (should not be the case but better be sure than sorry)
    if file_node is None:
        file_node = ElementTree.Element("ARRAY", NAME="BundleHost_FILE", TYPE="string")
        script_mgr.append(file_node)
    if system_node is None:
        system_node = ElementTree.Element(
            "ARRAY", NAME="BundleHost_SYSTEM", TYPE="boolean"
        )
        script_mgr.append(system_node)
    if enable_node is None:
        enable_node = ElementTree.Element(
            "ARRAY", NAME="BundleHost_ENABLE", TYPE="boolean"
        )
        script_mgr.append(enable_node)
    if active_node is None:
        active_node = ElementTree.Element(
            "ARRAY", NAME="BundleHost_ACTIVE", TYPE="boolean"
        )
        script_mgr.append(active_node)

    for b in bundles:
        file_node.append(ElementTree.Element("A", VALUE=b.file))
        system_node.append(
            ElementTree.Element("A", VALUE="true" if b.system else "false")
        )
        enable_node.append(
            ElementTree.Element("A", VALUE="true" if b.enabled else "false")
        )
        active_node.append(
            ElementTree.Element("A", VALUE="true" if b.active else "false")
        )

    ElementTree.indent(element)
    element.write(str(settings), encoding="utf-8", xml_declaration=True)


def get_enable_bundles(settings: Path) -> List[Path]:
    bundles = deserialize_bundles(settings)
    result: List[Path] = []
    for b in bundles:
        if b.enabled and not b.system:
            bundle_path = Path(b.file.replace("$USER_HOME", str(Path.home())))
            if bundle_path.exists() and bundle_path.is_dir():
                result.append(bundle_path)
    return result


def get_suitable_bundles(settings: Path) -> List[Path]:
    bundles = deserialize_bundles(settings)
    result: List[Path] = []
    for b in bundles:
        if not b.enabled and not b.system:
            bundle_path = Path(b.file.replace("$USER_HOME", str(Path.home())))
            if bundle_path.exists() and bundle_path.is_dir():
                result.append(bundle_path)
    return result


def add_new_bundle(settings: Path, bundle: Path) -> None:
    bundles = deserialize_bundles(settings)
    bundle.mkdir(exist_ok=True)
    for b in bundles:
        bundle_path = Path(b.file.replace("$USER_HOME", str(Path.home())))
        if not b.enabled and not b.system and bundle == bundle_path:
            print(f"Enabling disabled bundle '{bundle}'")
            b.enabled = True
            # Keep active in sync with enabled (assumption)
            b.active = True
            serialize_bundles(settings, bundles)
            return

    print(f"Creating a new bundle in '{bundle}'")
    new_b = Bundle(
        file=str(bundle).replace(str(Path.home()), "$USER_HOME"),
        system=False,
        enabled=True,
        active=True,
    )
    bundles.append(new_b)
    serialize_bundles(settings, bundles)


def copy_client_script_to_bundle(bundle: Path) -> None:
    print(f"Installing Sighthouse client script to '{bundle}'")
    client_script = Path(__file__).parent / "SightHouseClientGhidra.py"
    if not client_script.exists() or not client_script.is_file():
        print("Error: Fail to find Sighthouse client script for Ghidra")
        return

    # Copy script
    with open(str(client_script), "r") as fpin:
        with open(str(bundle / "SightHouseClientGhidra.py"), "w") as fpout:
            fpout.write(fpin.read())

    print("Sighthouse client script installed!")


def copy_client_script(install_dir: Path) -> None:
    # Get the user Ghidra configuration directory
    user_dir = get_user_settings_dir(install_dir)
    settings = user_dir / "tools" / "_code_browser.tcd"
    if not settings.exists() or not settings.is_file():
        print(f"Error: Fail to find {settings.name}")
        return

    bundles = get_enable_bundles(settings)
    if len(bundles) == 0:
        print("Error: No existing bundles found")
        suitable = get_suitable_bundles(settings)
        default = Path.home() / "ghidra_scripts"
        for e in [
            user_dir / "ghidra_scripts",
            Path.home() / "ghidra_scripts",
            default,
        ]:  # Default directories
            if e not in suitable:
                suitable.append(e)

        print("Found the following suitable bundles:")
        for i, bundle in enumerate(suitable):
            print(f" {i}: {bundle}")
        print("")

        choice = input(
            f"Enter the number corresponding to the bundle to install (default: {default}): "
        )
        try:
            if choice.lower() in ["y", "yes"]:
                choice = suitable.index(default)
            else:
                choice = int(choice)
            if choice < 0 or choice >= len(suitable):
                raise ValueError("Invalid range")
            add_new_bundle(settings, suitable[choice])
            copy_client_script_to_bundle(suitable[choice])
        except ValueError:
            print(f"Error: Invalid choice '{choice}', skipping")

    elif len(bundles) == 1:
        choice = input(
            f"Found only one bundle directory, do you want to copy script to '{bundles[0]}' (y/n)? "
        )
        if choice.lower() in ("y", "yes"):
            copy_client_script_to_bundle(bundles[0])
        else:
            print("Error: Skipping install script")
    else:
        print("Multiples bundles detected:")
        for i, bundle in enumerate(bundles):
            print(f" {i}: {bundle}")
        print("")

        choice = input("Enter the number corresponding to the bundle to install: ")
        try:
            choice = int(choice)
            if choice < 0 or choice >= len(bundles):
                raise ValueError("Invalid range")
            copy_client_script_to_bundle(bundles[choice])
        except ValueError:
            print(f"Error: Invalid choice '{choice}', skipping")


def main(install_dir: str) -> None:
    # Parse command line arguments

    # Setup variables
    install_dir = Path(install_dir)
    python_cmd: str = sys.executable
    pyghidra_dir: Path = install_dir / "Ghidra" / "Features" / "PyGhidra"
    dist_dir: Path = pyghidra_dir / "pypkg" / "dist"

    # Unsure install_dir exists
    if not install_dir.exists() or not install_dir.is_dir():
        print(f"Ghidra installation does not exists: '{install_dir}'")
        sys.exit(1)

    release_venv_dir = get_ghidra_venv(install_dir)

    # If in release mode, offer to install or upgrade PyGhidra before launching from user-controlled environment
    pip_args_poetry: List[str] = [
        "-m",
        "pip",
        "install",
        "--force-reinstall",
        "poetry",
    ]
    poetry_args_build: List[str] = ["-m", "poetry", "build"]
    pip_args_pyghidra: List[str] = [
        "-m",
        "pip",
        "install",
        "--no-index",
        "-f",
        str(dist_dir),
        "pyghidra",
    ]

    # Setup the proper execution environment:
    # 1) If we are already in a virtual environment, use that
    # 2) If the Ghidra user settings virtual environment exists, use that
    # 3) If we are "externally managed", automatically create/use the Ghidra user settings virtual environment
    offer_venv: bool = False
    if in_venv():
        # If we are already in a virtual environment, assume that's where the user wants to be
        print(f"Using active virtual environment: {sys.prefix}")
    elif os.path.isdir(release_venv_dir):
        # If the Ghidra user settings venv exists, use that
        python_cmd = get_venv_exe(release_venv_dir)
        print(f"Using Ghidra virtual environment: {release_venv_dir}")
    elif is_externally_managed():
        print("Externally managed environment detected!")
        create_ghidra_venv(release_venv_dir)
        python_cmd = get_venv_exe(release_venv_dir)
    else:
        offer_venv = True

    # If PyGhidra is not installed in the execution environment, offer to install it
    # If it's already installed, offer to upgrade (if applicable)
    for pip_args in [pip_args_poetry, poetry_args_build, pip_args_pyghidra]:
        python_cmd = install(install_dir, python_cmd, pip_args, offer_venv)
        if not python_cmd:
            sys.exit(1)

    # Now that poetry has build our package, install sighthouse
    pip_args_sighthouse: List[str] = [
        "-m",
        "pip",
        "install",
        "--force-reinstall",
        str(list((Path.cwd() / "dist/").glob("*.whl"))[-1]),
    ]
    if not install(install_dir, python_cmd, pip_args_sighthouse, offer_venv):
        sys.exit(1)

    # Copy client script
    copy_client_script(install_dir)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("ghidra_dir", help="Path to your installation of Ghidra")

    args = parser.parse_args()
    main(args.ghidra_dir)
