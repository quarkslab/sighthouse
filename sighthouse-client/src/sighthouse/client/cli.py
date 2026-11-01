"""SightHouse client command-line"""

import pathlib
import os
from typing import List, Optional
from argparse import Namespace, ArgumentParser

from sighthouse.cli import SightHouseCommandLine

from sighthouse.client.install_binja import main as binja_main
from sighthouse.client.install_ida import InstallError, main as ida_main
from sighthouse.client.install_ghidra import main as ghidra_main
from sighthouse.client.SightHouseClient import AnalysisOptions
from sighthouse.client.SightHouseClientStandalone import SightHouseClientStandalone

_ENV_IDA_DIR = "IDA_DIR"
_ENV_GHIDRA_INSTALL_DIR = "GHIDRA_INSTALL_DIR"

# ---------------------------------------------------------------------------
# Per-SRE install helpers
# ---------------------------------------------------------------------------


def _install_binja() -> None:
    binja_main()


def _install_ida(
    ida_dir: Optional[str],
    python: Optional[str],
    break_system_packages: bool,
    dry_run: bool,
) -> None:
    # The IDA directory is optional: the plugin goes in the IDA user directory
    # and the Python interpreter is detected from the idapyswitch settings.
    resolved = ida_dir or os.environ.get(_ENV_IDA_DIR)
    if resolved:
        path = pathlib.Path(resolved).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"IDA directory not found: {path}")
        resolved = str(path)
    ida_main(resolved, python, break_system_packages, dry_run)


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
            print("[+] Installing SightHouse Binary Ninja client ...")
            _install_binja()

        elif sre == "ida":
            print("[+] Installing SightHouse IDA client ...")
            _install_ida(
                args.ida_dir, args.python, args.break_system_packages, args.dry_run
            )

        elif sre == "ghidra":
            print("[+] Installing SightHouse Ghidra client ...")
            _install_ghidra(args.ghidra_install_dir)

        else:
            # Should never happen because argparse enforces choices=
            print(f"[!] Unknown SRE: {sre}")
            return

        print("[+] Installation complete.")

    except (FileNotFoundError, ValueError, InstallError) as exc:
        print(f"[!] {exc}")


def analyze_cmd_handler(self, args: Namespace, remaining: List[str]) -> None:
    """Analyze a binary against the SightHouse signature server.

    Auto-detects the language + layout by default. Can be overwritten
    by setting --language/--load-addr
    """
    if args.insecure:
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    options = AnalysisOptions(bob_ross=False, auto_analysis=True)
    analyzer = SightHouseClientStandalone(
        args.url,
        args.username,
        args.password,
        verify_host=not args.insecure,
        force_submission=args.force,
        options=options,
    )
    analyzer.run(args.filename, language=args.arch, load_addr=args.load_addr)


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
        help="Path to the Ghidra installation directory (required for 'ghidra', "
        f"defaults to ${_ENV_GHIDRA_INSTALL_DIR}).",
    )

    install_parser.add_argument(
        "--ida-dir",
        dest="ida_dir",
        metavar="PATH",
        default=None,
        help="Path to the IDA Pro installation directory (optional for 'ida', "
        f"defaults to ${_ENV_IDA_DIR}).",
    )
    install_parser.add_argument(
        "--python",
        dest="python",
        metavar="PATH",
        default=None,
        help="Python interpreter used by IDA ('ida' only, default: detected from "
        "the idapyswitch settings).",
    )
    install_parser.add_argument(
        "--break-system-packages",
        dest="break_system_packages",
        default=False,
        action="store_true",
        help="Allow pip to install into an externally managed Python ('ida' only).",
    )
    install_parser.add_argument(
        "--dry-run",
        dest="dry_run",
        default=False,
        action="store_true",
        help="Print what would be done without changing anything ('ida' only).",
    )

    # -- analyze sub-command -------------------------------------------------
    analyze_parser: ArgumentParser = parser_client.add_command(
        "analyze",
        analyze_cmd_handler,
        help="Analyze a binary against the signature server",
    )
    analyze_parser.add_argument(
        "url", metavar="URL", help="SightHouse frontend server URL"
    )
    analyze_parser.add_argument(
        "username", metavar="USERNAME", help="Username to log in"
    )
    analyze_parser.add_argument(
        "password", metavar="PASSWORD", help="Password to log in"
    )
    analyze_parser.add_argument(
        "filename", metavar="FILE", help="Binary file to analyze"
    )
    analyze_parser.add_argument(
        "-a",
        "--arch",
        default=None,
        help="Ghidra language for a raw/baremetal image (e.g. ARM:LE:32:v8). When "
        "set, auto-detection is skipped and the whole file is mapped as one RWX "
        "section at --load-addr.",
    )
    analyze_parser.add_argument(
        "-l",
        "--load-addr",
        dest="load_addr",
        default=0,
        type=lambda x: int(x, 0),
        help="Base address for the raw mapping (hex or decimal). Default: 0.",
    )
    analyze_parser.add_argument(
        "-k",
        "--insecure",
        dest="insecure",
        default=False,
        action="store_true",
        help="Allow insecure server connections (skip TLS verification).",
    )
    analyze_parser.add_argument(
        "-f",
        "--force",
        dest="force",
        default=False,
        action="store_true",
        help="Replace a cached program of the same name and re-analyze.",
    )
