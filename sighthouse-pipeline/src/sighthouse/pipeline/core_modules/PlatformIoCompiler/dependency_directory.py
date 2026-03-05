# type: ignore
import sys
import os
from pathlib import Path

from typing import List

import json
import argparse
import requests
from urllib.parse import urlparse
import subprocess
import tempfile
import zipfile

from platformio.package.manager.core import get_core_package_dir

get_core_package_dir("tool-scons")

sys.path.insert(0, f"{Path.home()}/.platformio/packages/tool-scons/scons-local-4.8.1/")

import SCons
from SCons.Script import SConscript, Builder
from SCons.Script import DefaultEnvironment
from SCons import Defaults
from SCons.Node import FS

from platformio import fs
from platformio.project.config import ProjectConfig

from platformio.builder.tools.piolib import ProjectAsLibBuilder

from platformio.builder.tools.piobuild import generate as generate_piobuild
from platformio.builder.tools.piotarget import generate as generate_piotarget
from platformio.builder.tools.pioplatform import generate as generate_pioplatform
from platformio.builder.tools.piointegration import generate as generate_piointegration
from platformio.builder.tools.pioproject import generate as generate_pioproject
from platformio.builder.tools.piolib import generate as generate_piolib

from platformio.platform.factory import PlatformFactory
from SCons.Script import COMMAND_LINE_TARGETS

# from platformio.builder.tools.pioplatform import BoardConfig
from platformio.platform.exception import UnknownBoard

from sighthouse.core.utils import _safe_extract_zip


def VariantDir(env, directory, *args, **kwargs):
    env["VariantDir"].append(env.subst(directory))


def PioPlatform(_):
    env = DefaultEnvironment()
    return PlatformFactory.from_env(
        env["PIOENV"], targets=COMMAND_LINE_TARGETS, autoinstall=True
    )


def BoardConfig(env, board=None):
    with fs.cd(env.subst("$PROJECT_DIR")):
        try:
            p = env.PioPlatform()
            board = board or env.get("BOARD")
            assert board, "BoardConfig: Board is not defined"
            return p.board_config(board)
        except (AssertionError, UnknownBoard) as exc:
            sys.stderr.write("Error: %s\n" % str(exc))
            next(iter(p.get_boards()))
            return next(iter(p.get_boards().values()))
            # env.Exit(1)
    return None


def BuildLibrary(env, variant_dir, src_dir, src_filter=None, nodes=None):
    try:
        env.ProcessUnFlags(env.get("BUILD_UNFLAGS"))
        nodes = nodes or env.CollectBuildFiles(variant_dir, src_dir, src_filter)
        return env.StaticLibrary(env.subst(variant_dir), nodes)
    except SCons.Errors.UserError:
        return []


def fetch_fs_size(env):
    pass


def get_dir_dependency_current(env: DefaultEnvironment) -> dict:
    DefaultEnvironment().Replace(__PIO_LIB_BUILDERS=None)
    env["PROJECT_BUILD_DIR"] = env.subst("$PROJECT_DIR/.pio/build")
    env["BUILD_DIR"] = env.subst("$PROJECT_BUILD_DIR/$PIOENV")
    env["PROGNAME"] = "program"
    env["PROGSUFFIX"] = ""
    env["PYTHONEXE"] = sys.executable
    env["VariantDir"] = []
    env["BUILD_TYPE"] = "release"
    env["PROJECT_LIBDEPS_DIR"] = env.subst("$PROJECT_DIR/.pio/libdeps")
    env["LIBSOURCE_DIRS"] = [env.subst("$PROJECT_LIBDEPS_DIR/$PIOENV")]
    env["CPPDEFINES"] = []
    env["__fetch_fs_size"] = fetch_fs_size

    env.Append(
        BUILDERS=dict(
            ElfToBin=Builder(action=env.VerboseAction(" ", "Building"), suffix=".bin"),
            DataToBin=Builder(
                action=env.VerboseAction(" ", "Building"),
                suffix=".bin",
            ),
        )
    )

    platform_without_version = env["PIOPLATFORM"].split("@")[0].strip()

    parsed = urlparse(platform_without_version)
    base_framework_path = None
    if parsed.scheme:
        if parsed.scheme in ("http", "https") and ".git" in platform_without_version:

            base, _, fragment = platform_without_version.partition(".git#")
            if not base.endswith(".git"):
                repo_url = base + ".git"
            else:
                repo_url = base
            repo_name = repo_url.split("/")[-1].replace(".git", "")
            branch = fragment if fragment else None

            if not (Path.home() / f".platformio/platforms/{repo_name}").exists():
                # Clone into a temporary directory
                cmd = ["git", "clone", "--recurse-submodules"]
                if branch:
                    cmd += ["--branch", branch, "--single-branch", "--depth", "1"]
                cmd += [repo_url, f"{Path.home()}/.platformio/platforms/{repo_name}"]

                subprocess.check_call(cmd)
            base_framework_path = f"{Path.home()}/.platformio/platforms/{repo_name}"
        elif parsed.scheme in ("http", "https") and platform_without_version.endswith(
            ".zip"
        ):
            first_folder = None
            with tempfile.TemporaryDirectory() as tmpdir:
                zip_path = Path(tmpdir) / "archive.zip"

                # Download the zip
                r = requests.get(platform_without_version, stream=True)
                r.raise_for_status()
                with open(zip_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)

                # Extract it
                with zipfile.ZipFile(zip_path, "r") as zf:
                    for item in zf.namelist():
                        parts = item.split("/")
                        if len(parts) > 1:  # Ensure there is a parent directory
                            first_folder = parts[0]  # Get the first parent directory
                            break
                    _safe_extract_zip(zf, Path.home() / ".platformio" / "platforms")

            # Step 4: Move or copy the first folder to the desired location
            if first_folder:
                base_framework_path = (
                    f"{Path.home()}/.platformio/platforms/{first_folder}"
                )
    else:
        base_framework_path = (
            f"{Path.home()}/.platformio/platforms/{platform_without_version}"
        )

    framework_json_path = f"{base_framework_path}/platform.json"
    if Path(framework_json_path).exists():
        with open(framework_json_path) as f:
            frameworks_json = json.loads(f.read())
    else:
        raise Exception("Not handle Case for the moment")

    env.Replace(PIOPLATFORM=frameworks_json["name"])
    config = ProjectConfig.get_instance()
    config.update([(f"env:{env['PIOENV']}", [("platform", frameworks_json["name"])])])
    config.save()

    p = PioPlatform(env)
    if env.get("board") is not None:
        p.configure_default_packages(env, [])  # config.get(f"env:{env['PIOENV']}"), [])

    if "frameworks" in frameworks_json:
        framework_package = frameworks_json["frameworks"][env["PIOFRAMEWORK"]].get(
            "package", None
        )
        builder_script = frameworks_json["frameworks"][env["PIOFRAMEWORK"]]["script"]
        if Path(framework_json_path).exists():
            script_path = Path(f"{base_framework_path}/{builder_script}")
        else:
            script_path = tempfile.NamedTemporaryFile(presuffix=".json")
        env.fs = FS.FS(path=script_path.parent.as_posix())
        env.fs.set_SConstruct_dir(env.fs.Dir(script_path.parent))

        env.LoadPioPlatform()
        env.SConscript(
            script_path.absolute().as_posix(),
            exports={"env": env, "script_path": script_path},
        )

    plb = ProjectAsLibBuilder(env, env.subst("$PROJECT_DIR"))
    plb.search_deps_recursive()

    platform_version = frameworks_json["version"]
    if "frameworks" in frameworks_json and framework_package is not None:
        framework_version = frameworks_json["packages"][framework_package]["version"]
    else:
        framework_version = "0.0.0"

    # List libraries
    dir_objs = {}
    dir_objs["libraries"] = []
    for lib in plb.depbuilders:
        objfiles = list_object_files([env.subst(lib.build_dir)])
        dir_objs["libraries"].append(
            {"name": lib.name, "version": lib.version, "files": objfiles}
        )

    # List frameworks
    objfiles = list_object_files(env["VariantDir"])
    if "PIOFRAMEWORK" in env:
        dir_objs["framework"] = {
            "name": env["PIOFRAMEWORK"],
            "version": framework_version,
            "files": objfiles,
        }
    # List examples
    objfiles = list_object_files([f"{env['BUILD_DIR']}/src"])
    dir_objs["example"] = {"files": objfiles}
    return dir_objs


def list_object_files(directories: List[str]) -> List[Path]:
    object_files = []
    for directory in directories:
        path = Path(directory)
        if not path.is_dir():
            continue
        object_files.extend(list(path.rglob("*.o")))
    return object_files


def get_dir_dependency(
    project_dir: str, environment: str | None = None, strict: bool = False
):
    result = []
    from SCons.Environment import Environment

    Defaults._default_env = Environment()
    Defaults._default_env.Decider("content")
    env = DefaultEnvironment()
    generate_piobuild(env)
    generate_piotarget(env)
    generate_pioplatform(env)
    generate_piointegration(env)
    generate_pioproject(env)
    generate_piolib(env)
    env.AddMethod(VariantDir)
    env.AddMethod(PioPlatform)
    env.AddMethod(BuildLibrary)
    env.AddMethod(BoardConfig)
    env["PROJECT_DIR"] = Path(project_dir).resolve().absolute().as_posix()
    env["PROJECT_CONFIG"] = env.subst("$PROJECT_DIR/platformio.ini")

    from platformio import app

    app.set_session_var("custom_project_conf", env.subst(env["PROJECT_CONFIG"]))
    with fs.cd(env.subst(env["PROJECT_DIR"])):
        config = ProjectConfig.get_instance()
        if environment is None:
            for env1 in config.envs():
                try:
                    env["PIOENV"] = env1
                    env["PIOPLATFORM"] = config.get(f"env:{env1}", "platform")
                    frameworks = config.get(f"env:{env1}", "framework")
                    if len(frameworks) != 0:
                        env["PIOFRAMEWORK"] = frameworks[0]
                    env["BOARD"] = config.get(f"env:{env1}", "board")
                    result.append(get_dir_dependency_current(env))
                except Exception as e:
                    print(e)
                    if strict:
                        raise e
        else:
            try:
                env["PIOENV"] = environment
                env["PIOPLATFORM"] = config.get(f"env:{environment}", "platform")
                env["PIOFRAMEWORK"] = config.get(f"env:{environment}", "framework")
                env["BOARD"] = config.get(f"env:{environment}", "board")
                result.append(get_dir_dependency_current(env))
            except Exception as e:
                print(e)
                if strict:
                    raise e

    Defaults._default_env = None
    return result


def main():
    parser = argparse.ArgumentParser(description="Export project dependencies to JSON")

    parser.add_argument("filename", help="Output JSON filename")
    parser.add_argument(
        "--project-dir",
        default=".",
        help="Path to the project directory (default: current dir)",
    )
    parser.add_argument("--environment", help="Optional environment name", default=None)
    parser.add_argument(
        "--strict", action="store_true", help="Enable strict mode checking"
    )

    args = parser.parse_args()

    # Call your dependency function
    deps = get_dir_dependency(args.project_dir, args.environment, args.strict)

    # Ensure parent dir exists
    Path(args.filename).parent.mkdir(parents=True, exist_ok=True)

    # Write as JSON
    with open(args.filename, "w", encoding="utf-8") as f:
        json.dump(deps, f, default=str)


if __name__ == "__main__":
    main()
    sys.exit(0)


"""
Example on how to use:

    get_dir_dependency("../arduino-external-libs")
    get_dir_dependency("./")
    print(get_dir_dependency(f"{Path.home()}/Documents/project/platformio_work_bck/work/deni/examples/mbed-rtos-ethernet"))
    get_dir_dependency(f"{Path.home()}/Downloads/tota")
    print(get_dir_dependency(f"{Path.home()}/Downloads/tota/examples/Blink/"))
    print(get_dir_dependency(f"{Path.home()}/Downloads/justwifi/examples/advanced"))
    print(get_dir_dependency(f"{Path.home()}/Downloads/ds1302/examples/01"))
    print(get_dir_dependency(f"{Path.home()}/Downloads/ds1302/examples/02"))

"""
