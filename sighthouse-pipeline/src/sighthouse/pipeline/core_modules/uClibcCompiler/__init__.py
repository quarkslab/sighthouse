from typing import Dict, List, Tuple
from tempfile import TemporaryDirectory
from argparse import ArgumentParser
from pathlib import Path
import os

from sighthouse.pipeline.worker import Compiler, Job
from sighthouse.core.utils import (
    extract_tar,
    run_process,
    parse_menuconfig,
    write_menuconfig,
)


class uClibcCompiler(Compiler):

    # 3h timeout
    TIMEOUT: int = 3600 * 3

    def __init__(self, worker_url: str, repo_url: str):
        super().__init__("uClibc Compiler", worker_url, repo_url)

    def set_arch_config(self, config: Dict[str, str], options: Dict[str, str]) -> None:
        """Set arch-specific configuration options"""
        # First unset every arch specific options
        for key in list(config.keys()):
            if key.startswith("TARGET_") and key != "TARGET_LDSO_NAME":
                config[key] = None

        # Compiler will default to gcc x86
        # Useful ressource: https://wiki.osdev.org/Target_Triplet
        cc = options.get("cc", "x86_64-linux-gnu-gcc")
        if cc == "x86_64-linux-gnu-gcc" or cc == "gcc":
            config.update(
                {
                    "TARGET_x86_64": "y",
                    "TARGET_ARCH_BITS": 64,
                    "TARGET_ARCH": '"x86_64"',
                    "TARGET_SUBARCH": '""',
                }
            )
        elif cc == "arm-linux-gnueabi-gcc":
            config.update(
                {
                    "TARGET_arm": "y",
                    "TARGET_ARCH_BITS": 32,
                    "TARGET_ARCH": '"arm"',
                    "TARGET_SUBARCH": '""',
                    "CONFIG_ARM_EABI": "y",
                    "UCLIBC_BUILD_PIE": "y",
                    "ARCH_ANY_ENDIAN": "y",
                    "ARCH_LITTLE_ENDIAN": "y",
                    "ARCH_WANTS_LITTLE_ENDIAN": "y",
                    "ARCH_WANTS_BIG_ENDIAN": None,
                    "UCLIBC_USE_TIME64": None,
                }
            )
        elif cc == "mips-linux-gnu-gcc":
            config.update(
                {
                    "TARGET_mips": "y",
                    "TARGET_ARCH_BITS": 32,
                    "TARGET_ARCH": '"mips"',
                    "TARGET_SUBARCH": '""',
                    "CONFIG_MIPS_O32_ABI": "y",
                    "CONFIG_MIPS_N32_ABI": None,
                    "CONFIG_MIPS_N64_ABI": None,
                    "CONFIG_MIPS_NAN_LEGACY": "y",
                    "CONFIG_MIPS_NAN_2008": None,
                    "UCLIBC_USE_MIPS_PREFETCH": "y",
                    "UCLIBC_BUILD_PIE": None,
                    "ARCH_ANY_ENDIAN": "y",
                    "ARCH_BIG_ENDIAN": "y",
                    "ARCH_WANTS_LITTLE_ENDIAN": None,
                    "ARCH_WANTS_BIG_ENDIAN": "y",
                    "UCLIBC_USE_TIME64": None,
                }
            )
        elif cc == "mipsel-linux-gnu-gcc":
            config.update(
                {
                    "TARGET_mips": "y",
                    "TARGET_ARCH_BITS": 32,
                    "TARGET_ARCH": '"mips"',
                    "TARGET_SUBARCH": '""',
                    "CONFIG_MIPS_O32_ABI": "y",
                    "CONFIG_MIPS_N32_ABI": None,
                    "CONFIG_MIPS_N64_ABI": None,
                    "CONFIG_MIPS_NAN_LEGACY": "y",
                    "CONFIG_MIPS_NAN_2008": None,
                    "UCLIBC_USE_MIPS_PREFETCH": "y",
                    "UCLIBC_BUILD_PIE": None,
                    "ARCH_ANY_ENDIAN": "y",
                    "ARCH_LITTLE_ENDIAN": "y",
                    "ARCH_WANTS_LITTLE_ENDIAN": "y",
                    "ARCH_WANTS_BIG_ENDIAN": None,
                    "UCLIBC_USE_TIME64": None,
                }
            )
        elif cc == "aarch64-linux-gnu-gcc":
            config.update(
                {
                    "TARGET_aarch64": "y",
                    "TARGET_ARCH_BITS": 64,
                    "TARGET_ARCH": '"aarch64"',
                    "TARGET_SUBARCH": '""',
                    "CONFIG_AARCH64_PAGE_SIZE_4K": "y",
                    "CONFIG_AARCH64_PAGE_SIZE_16K": None,
                    "CONFIG_AARCH64_PAGE_SIZE_64K": None,
                    "ARCH_ANY_ENDIAN": "y",
                    "ARCH_LITTLE_ENDIAN": "y",
                    "ARCH_WANTS_LITTLE_ENDIAN": "y",
                    "ARCH_WANTS_BIG_ENDIAN": None,
                    "FORCE_SHAREABLE_TEXT_SEGMENTS": None,
                    "UCLIBC_BUILD_SSP": None,
                }
            )
            # Delete buggy options
            for opt in [
                "ARCH_HAS_UCONTEXT",
                "ARCH_HAS_DEPRECATED_SYSCALLS",
                "UCLIBC_HAS_CONTEXT_FUNCS",
                "UCLIBC_HAS_LINUXTHREADS",
                "UCLIBC_USE_TIME64",
            ]:
                if opt in config:
                    del config[opt]
        else:
            raise Exception("Unsupported compiler: '{}'".format(cc))

    def do_work(self, job: Job) -> None:
        variants: List[Tuple[str, Dict[str, str]]] = self.validate_compiler_variants(
            job.worker_args
        )
        # Get the file now before it could be modified by pack_and_send_task
        job_file = job.job_data.get("file")
        for name, options in variants:
            # Create a new temporary directory and clone the same project each time to avoid
            # conflicts between previous builds
            with TemporaryDirectory() as tmpdirname:
                tmpdir = Path(tmpdirname)
                req = self.get_file(job_file)
                if not req:
                    raise Exception(
                        "Could not download tar file: '{}'".format(job_file)
                    )

                if not extract_tar(req, tmpdir):
                    raise Exception("Could not extract tar file")

                # Build environment variables
                env_vars = os.environ.copy()
                env_vars.update(
                    {"CC": options.get("cc"), "CFLAGS": options.get("cflags")}
                )

                # 1. Generate default config using 'make defconfig'
                ret, _, _ = run_process(
                    ["make", "defconfig"],
                    cwd=tmpdir,
                    capture_output=True,
                    timeout=self.TIMEOUT,
                )
                if ret != 0:
                    raise Exception("Fail to generate default configuration")

                # 2. Edit .config
                current_cfg = parse_menuconfig(tmpdir / ".config")
                current_cfg.update(
                    parse_menuconfig(Path(__file__).parent / "uClibc-ng.config")
                )
                current_cfg.update(
                    {
                        "KERNEL_HEADERS": '"{}"'.format(
                            tmpdir / "linux-headers" / "include"
                        )
                    }
                )
                self.set_arch_config(current_cfg, options)
                write_menuconfig(tmpdir / ".config", current_cfg)

                # 3. Build with make in BUILD DIR
                cc = options.get("cc", "x86_64-linux-gnu-gcc")
                args = ["make"]
                if cc not in ["gcc", "x86_64-linux-gnu-gcc"]:
                    # Add cross compiler argument
                    args.append("CROSS={}".format(cc.rstrip("gcc")))

                ret, _, _ = run_process(
                    args,
                    cwd=tmpdir,
                    env=env_vars,
                    capture_output=True,
                    timeout=self.TIMEOUT,
                )
                if ret != 0:
                    raise Exception("Build failed")

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
    parser = ArgumentParser(description="uClibc Compiler worker")
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

    args = parser.parse_args()
    uClibcCompiler(args.worker_url, args.repo_url).run()


main()
