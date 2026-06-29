from typing import Dict, List, Tuple, Optional
from tempfile import TemporaryDirectory
from argparse import ArgumentParser
from pathlib import Path
import os

from sighthouse.pipeline.worker import Compiler, Job
from sighthouse.core.utils import (
    extract_tar,
    run_process,
)


class CmakeCompiler(Compiler):
    """Generic CMake based compiler worker.

    Recognised per-variant options (`compiler_variants`):
        cc (str):               C compiler (required, e.g. "gcc").
        cflags (str):           C flags (required, e.g. "-O0").
        cxx (str):              Optional C++ compiler (e.g. "g++").
        cxxflags (str):         Optional C++ flags.
        cmake_extra_args (str | list[str]):
                                Optional extra arguments forwarded to the CMake
                                configure step (e.g. "-DBUILD_SHARED_LIBS=ON").
    """

    # 3h timeout
    TIMEOUT: int = 3600 * 3

    def __init__(self, worker_url: str, repo_url: str, strict: bool = False):
        super().__init__("Cmake Compiler", worker_url, repo_url)
        self.strict = strict

    @staticmethod
    def _find_source_dir(tmpdir: Path) -> Optional[Path]:
        """Locate the directory holding the top-level CMakeLists.txt."""
        if (tmpdir / "CMakeLists.txt").exists():
            return tmpdir

        candidates = sorted(
            tmpdir.rglob("CMakeLists.txt"),
            key=lambda p: len(p.relative_to(tmpdir).parts),
        )
        return candidates[0].parent if candidates else None

    def do_work(self, job: Job) -> None:
        variants: List[Tuple[str, Dict[str, str]]] = self.validate_compiler_variants(
            job.worker_args
        )
        # Get the file now before it could be modified by pack_and_send_task
        job_file = job.job_data.get("file")
        for name, options in variants:
            # Create a new temporary directory and extract the same project each time
            # to avoid conflicts between previous builds
            with TemporaryDirectory() as tmpdirname:
                tmpdir: Path = Path(tmpdirname)
                req = self.get_file(job_file)
                if not req:
                    raise Exception(
                        "Could not download tar file: '{}'".format(job_file)
                    )

                if not extract_tar(req, tmpdir):
                    raise Exception("Could not extract tar file")

                source_dir = self._find_source_dir(tmpdir)
                if source_dir is None:
                    raise Exception("Could not find a CMakeLists.txt in the project")

                # Create a dedicated out-of-source build directory
                build_dir: Path = tmpdir / "build"
                build_dir.mkdir(exist_ok=True)

                cc = options.get("cc")
                cxx = options.get("cxx")
                cflags = options.get("cflags")
                cxxflags = options.get("cxxflags")

                # Build environment variables. CMake reads CC/CXX on first configure.
                env_vars = os.environ.copy()
                env_vars.update({"CC": cc, "CFLAGS": cflags})
                if cxx:
                    env_vars["CXX"] = cxx
                if cxxflags:
                    env_vars["CXXFLAGS"] = cxxflags

                # 1. Configure: generate the native build system (Makefiles/Ninja)
                #    into build_dir from the source tree.
                cmd = ["cmake", str(source_dir.absolute())]
                cmd.append("-DCMAKE_C_COMPILER={}".format(cc))
                cmd.append("-DCMAKE_C_FLAGS={}".format(cflags))
                if cxx:
                    cmd.append("-DCMAKE_CXX_COMPILER={}".format(cxx))
                if cxxflags:
                    cmd.append("-DCMAKE_CXX_FLAGS={}".format(cxxflags))

                extra_args = options.get("cmake_extra_args")
                if extra_args:
                    # Support both a single string and a list of arguments
                    if isinstance(extra_args, list) and all(
                        map(lambda e: isinstance(e, str), extra_args)
                    ):
                        cmd.extend(extra_args)
                    elif isinstance(extra_args, str):
                        cmd.append(extra_args)
                    else:
                        raise ValueError(
                            f'Invalid "cmake_extra_args". Expecting either a list[str]/str but got "{type(extra_args)}"'
                        )

                run_process(cmd, cwd=build_dir, env=env_vars, timeout=self.TIMEOUT)

                # 2. Build: compile via the generated build system
                ret, stdout, err = run_process(
                    ["cmake", "--build", "."],
                    cwd=build_dir,
                    env=env_vars,
                    timeout=self.TIMEOUT,
                    capture_output=True,
                )
                if ret != 0 and self.strict:
                    raise Exception(
                        "Build failed: stdout:\n{}\nstderr:\n{}".format(
                            stdout.decode("utf-8"), err.decode("utf-8")
                        )
                    )

                build_files = list(tmpdir.rglob("**/*.o")) + list(
                    tmpdir.rglob("**/*.so")
                )
                if len(build_files) == 0:
                    raise Exception("Build produce 0 file")

                metadata = [
                    [job.job_data["name"], job.job_data["version"] + "-" + name]
                ]
                self.pack_and_send_task(job, build_files, metadata)


def main():
    parser = ArgumentParser(description="Cmake Compiler worker")
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
        "--strict", action="store_true", help="Enable strict mode checking"
    )

    args = parser.parse_args()
    CmakeCompiler(args.worker_url, args.repo_url, strict=args.strict).run()


main()
