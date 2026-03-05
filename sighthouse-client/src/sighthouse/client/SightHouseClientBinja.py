from argparse import ArgumentParser
from pathlib import Path
import binaryninja
import json

try:
    # Try to import using published package
    from sighthouse.client.SightHouseClient import (
        SightHouseAnalysis,
        debug_requests_on,
        LoggingSighthouse,
        Section,
        Function,
        get_hash,
    )
except ModuleNotFoundError:
    # Install in dev mode
    try:
        from .SightHouseClient import (
            SightHouseAnalysis,
            debug_requests_on,
            LoggingSighthouse,
            Section,
            Function,
            get_hash,
        )
    except:
        print("Fail to install sighthouse")
        exit(1)

from typing import List, Tuple


class LoggingBinjaSighthouse(LoggingSighthouse):

    def __init__(self) -> None:
        """Initialize logging class"""
        self.binjaLogger = binaryninja.log.Logger(0, "Sighthouse")

    def error(self, message: str):
        """Show an error message

        Args:
            message (str): The message to show
        """
        self.binjaLogger.log_error(message)

    def warning(self, message: str):
        """Show an warning message

        Args:
            message (str): The message to show
        """
        self.binjaLogger.log_warn(message)

    def info(self, message: str):
        """Show an info message

        Args:
            message (str): The message to show
        """
        self.binjaLogger.log_info(message)


class SightHouseBinjaAnalysis(SightHouseAnalysis, binaryninja.BackgroundTaskThread):

    BINJA2GHIDRAARCH = {
        "8051": "8051:BE:16:default",
        "aarch64": "AARCH64:BE:64:v8A",
        "armv7": "ARM:LE:32:v7",
        "armv7eb": "ARM:BE:32:v7",
        "thumb2": "ARM:LE:32:v8T",
        "mipsel32": "MIPS:LE:32:default",
        "mips32": "MIPS:BE:32:default",
        "mips64": "MIPS:BE:64:default",
        "ppc": "PowerPC:BE:32:default",
        "ppc64": "PowerPC:BE:64:default",
        "ppc_le": "PowerPC:LE:32:default",
        "ppc64_le": "PowerPC:LE:64:default",
        "rv32gc": "RISCV:LE:32:RV32GC",
        "rv64gc": "RISCV:LE:64:RV64GC",
        "x86": "x86:LE:32:default",
        "x86_16": "x86:LE:16:Real Mode",
        "x86_64": "x86:LE:64:default",
    }

    def __init__(
        self,
        bv: binaryninja.BinaryView,
        url: str,
        username: str,
        password: str,
        verify_host: bool = True,
        force_submission: bool = False,
        options: dict = None,
    ):
        """Initialize SightHouseAnalysis

        Args:
            bv(binaryninja.BinaryView): Binary nija view
            username (str): username to connect to server
            password (str): password to connect to server
            client (SightHouseClient): A Sighthouse client link to the SRE
        """
        # This need to be done before calling super().__init__ as it calls get_current_arch
        self.bv = bv
        self.warn_function_details = False
        binaryninja.BackgroundTaskThread.__init__(self, "SightHouse client", True)
        super().__init__(
            username,
            password,
            url,
            LoggingBinjaSighthouse(),
            verify_host=verify_host,
            force_submission=force_submission,
            options=options,
        )
        if bv.get_tag_type("SightHouse matches") is None:
            bv.create_tag_type("SightHouse matches", "🔎")

    def get_current_arch(self) -> None:
        """get current architecture and translate to ghidra one"""
        arch = self.BINJA2GHIDRAARCH.get(self.bv.arch.name, None)
        if arch is None:
            self._logger.error(
                f"Architecture {self.bv.arch.name} is currently not supported by SightHouse"
            )
        return arch

    def update_progress(self, message: str) -> None:
        """show an update progress

        Args:
            message (str): message to show
        """
        self.progress = "SightHouse: " + message

    def get_current_binary(self) -> bytes:
        """Retrieve the current binaries in bytes

        Returns:
            bytes: the content in bytes of the current binaries
        """
        return self.bv.file.raw.read(0, self.bv.file.raw.length)

    def get_program_name(self) -> str:
        """Get program name

        Returns:
            str: the program name
        """
        return Path(self.bv.file.filename).name

    def get_sections(self) -> List[Section]:
        """Get sections

        Returns:
            List[Section]: list sections
        """
        res = []
        i = 0
        for segment in self.bv.segments:
            i += 1
            perms = "R" if segment.readable else " "
            perms += "W" if segment.writable else " "
            perms += "X" if segment.executable else " "
            res.append(
                Section(
                    "Section#{}".format(i),
                    segment.start,
                    segment.start + segment.length,
                    segment.data_offset,
                    perms,
                    "",
                )
            )
        return res

    def get_functions(self, section: Section) -> List[Function]:
        """get functions

        Args:
            section (Section): section

        Returns:
            List[Function]: list of function inside the section
        """
        if not self.warn_function_details:
            self._logger.warning(
                "Architecture details such as Thumb are not implemented"
            )
            self.warn_function_details = True

        ret_funcs = []
        for func in self.bv.functions:
            if section.start <= func.start <= section.end:
                ret_funcs.append(Function(func.name, func.start))

        return ret_funcs

    def get_hash_program(self) -> str:
        """get hash of program

        Returns:
            str: sha256 string
        """
        return get_hash(self.get_current_binary())

    def add_tag(self, address: int, tag: str, message: str) -> None:
        """Add a tag on the SRE

        Args:
            address (int): address where put the tag
            tag (str): tag of message
            message (str): message to show
        """
        self.bv.add_tag(address, tag, message)


def run_plugin(bv: binaryninja.BinaryView) -> None:
    settings = binaryninja.Settings()
    url = settings.get_string("sighthouse.serverURL")
    username = settings.get_string("sighthouse.username")
    password = settings.get_string("sighthouse.password")
    verify_host = settings.get_bool("sighthouse.verify_host")
    bob_ross = settings.get_bool("sighthouse.bob_ross")
    force_submission = settings.get_bool("sighthouse.force_submission")
    analyzer = SightHouseBinjaAnalysis(
        bv,
        url,
        username,
        password,
        verify_host=verify_host,
        force_submission=force_submission,
        options={
            "BobRoss": bob_ross,
        },
    )
    analyzer.start()


def main(path: str, url: str, username: str, password: str):
    bv = binaryninja.load(path)
    analyzer = SightHouseBinjaAnalysis(
        bv,
        url,
        username,
        password,
        verify_host=False,
        force_submission=True,
        options={
            "BobRoss": False,
        },
    )
    analyzer.start()


if __name__ == "__main__":
    parser = ArgumentParser("SightHouse")
    parser.add_argument("db", help="Path to the target binja db")
    parser.add_argument("url", help="SightHouse server URL")
    parser.add_argument("username", help="SightHouse server password")
    parser.add_argument("password", help="SightHouse server username")
    parser.add_argument("--debug", action="store_true", help="Activate debug mode")

    args = parser.parse_args()

    if args.debug:
        debug_requests_on()

    main(args.db, args.url, args.username, args.password)
else:
    from binaryninja import PluginCommand

    settings = binaryninja.Settings()
    properties = {
        "title": "SightHouse",
        "description": "Query signatures from SightHouse signature server",
    }
    settings.register_group("sighthouse", "SightHouse client")
    settings.register_setting(
        "sighthouse.serverURL",
        json.dumps(
            {
                "title": "Server URL",
                "description": "Set the SightHouse signature server URL",
                "type": "string",
                "optional": False,
            }
        ),
    )
    settings.register_setting(
        "sighthouse.username",
        json.dumps(
            {
                "title": "Server username",
                "description": "Set the username to be used for connecting to the SightHouse server",
                "type": "string",
                "optional": False,
            }
        ),
    )
    settings.register_setting(
        "sighthouse.password",
        json.dumps(
            {
                "title": "Server password",
                "description": "Set the password to be used for connecting to the SightHouse server",
                "type": "string",
                "optional": False,
            }
        ),
    )
    settings.register_setting(
        "sighthouse.verify_host",
        json.dumps(
            {
                "title": "Verify server certificate",
                "description": "Verify the server certificate when connecting to the SightHouse server",
                "type": "boolean",
                "default": True,
                "optional": False,
            }
        ),
    )

    settings.register_setting(
        "sighthouse.bob_ross",
        json.dumps(
            {
                "title": "Experimental Algorithme to enhance matches",
                "description": "Experimental Algorithme to enhance matches",
                "type": "boolean",
                "default": False,
                "optional": True,
            }
        ),
    )

    settings.register_setting(
        "sighthouse.force_submission",
        json.dumps(
            {
                "title": "Force submission",
                "description": "Remove previous information stored on the server before each analysis",
                "type": "boolean",
                "default": True,
                "optional": False,
            }
        ),
    )

    PluginCommand.register(
        "SightHouse Binary Ninja Plugin",
        "Query signatures from SightHouse signature server",
        run_plugin,
    )
