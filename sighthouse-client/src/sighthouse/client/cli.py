"""SightHouse client command-line"""

import pathlib
import os
from typing import List, Optional
from argparse import Namespace, ArgumentParser

from sighthouse.cli import SightHouseCommandLine

from sighthouse.client.install_binja import main as binja_main
from sighthouse.client.install_ida import main as ida_main
from sighthouse.client.install_ghidra import main as ghidra_main

_ENV_IDA_DIR = "IDA_DIR"
_ENV_GHIDRA_INSTALL_DIR = "GHIDRA_INSTALL_DIR"

# ---------------------------------------------------------------------------
# Per-SRE install helpers
# ---------------------------------------------------------------------------


def _install_binja() -> None:
    binja_main()


def _install_ida(ida_dir: Optional[str]) -> None:
    resolved = ida_dir or os.environ.get(_ENV_IDA_DIR)
    if not resolved:
        raise ValueError(
            f"IDA directory is required. Pass --ida-dir or set ${_ENV_IDA_DIR}."
        )
    path = pathlib.Path(resolved).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"IDA directory not found: {path}")
    ida_main(str(path))


def _install_ghidra(ghidra_install_dir: Optional[str]) -> None:
    resolved = ghidra_install_dir or os.environ.get(_ENV_GHIDRA_INSTALL_DIR)
    if not resolved:
        raise ValueError(
            f"Ghidra install directory is required. Pass --ghidra-install-dir or set ${_ENV_GHIDRA_INSTALL_DIR}."
        )
    path = pathlib.Path(resolved).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Ghidra install directory not found: {path}")
    ghidra_main(str(path))


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def install_sre_cmd_handler(self, args: Namespace, remaining: List[str]) -> None:
    """Install sighthouse in your SRE"""
    sre: str = args.sre.lower()

    try:
        if sre == "binja":
            print("[+] Installing SightHouse Binary Ninja client …")
            _install_binja()

        elif sre == "ida":
            if not args.ida_dir:
                print("[!] --ida-dir is required for IDA installation.")
                return
            print(f"[+] Installing SightHouse IDA client into {args.ida_dir} …")
            _install_ida(args.ida_dir)

        elif sre == "ghidra":
            if not args.ghidra_install_dir:
                print("[!] --ghidra-install-dir is required for Ghidra installation.")
                return
            print(
                f"[+] Installing SightHouse Ghidra client into {args.ghidra_install_dir} …"
            )
            _install_ghidra(args.ghidra_install_dir)

        else:
            # Should never happen because argparse enforces choices=
            print(f"[!] Unknown SRE: {sre}")
            return

        print("[+] Installation complete.")

    except FileNotFoundError as exc:
        print(f"[!] {exc}")


# ---------------------------------------------------------------------------
# CLI registration
# ---------------------------------------------------------------------------


def add_to_cli(app: SightHouseCommandLine) -> None:
    """Add client argument parser to main command-line app."""

    parser_client = app.add_command_group(
        "client", "client_command", help="Handle %(prog)s client"
    )

    if parser_client is None:
        return

    # -- install sub-command -------------------------------------------------
    install_parser: ArgumentParser = parser_client.add_command(
        "install",
        install_sre_cmd_handler,
        help="Install on your SRE %(prog)s client",
    )

    # Positional: which SRE to target
    install_parser.add_argument(
        "sre",
        choices=["binja", "ghidra", "ida"],
        metavar="SRE",
        help="Target SRE to install the client on. Choices: binja, ghidra, ida.",
    )

    # Optional path arguments (only required for the relevant SRE)
    install_parser.add_argument(
        "--ghidra-install-dir",
        dest="ghidra_install_dir",
        metavar="PATH",
        default=None,
        help="Path to the Ghidra installation directory (required for 'ghidra').",
    )

    install_parser.add_argument(
        "--ida-dir",
        dest="ida_dir",
        metavar="PATH",
        default=None,
        help="Path to the IDA Pro installation directory (required for 'ida').",
    )
