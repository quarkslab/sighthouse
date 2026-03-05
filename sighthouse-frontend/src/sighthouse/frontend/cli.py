"""SightHouse frontend command-line"""

from logging import getLogger, basicConfig, INFO, DEBUG
from typing import Optional, List
from multiprocessing import Process
from argparse import Namespace
from secrets import token_hex
from subprocess import Popen
from pathlib import Path
import signal
import sys
import os

from werkzeug.security import generate_password_hash

from sighthouse.cli import SightHouseCommandLine
from sighthouse.frontend.database import FrontendDatabase
from sighthouse.frontend.model import User
from sighthouse.frontend.restapi import FrontendRestAPI
from sighthouse.frontend.localapi import LocalRestAPI


def add_frontent_cmd_handler(self, args: Namespace, remaining: List[str]) -> None:
    """Add a user to sighthouse frontend"""

    database = FrontendDatabase(args.database, args.repo_url, exist_ok=True)
    password = args.password
    if not password:
        # Auto-generate a new password
        password = token_hex(16)

    user = database.add_user(
        User(
            id=User.INVALID_ID,
            name=args.username,
            hash=generate_password_hash(password, method="pbkdf2:sha256"),
        )
    )
    if not user:
        print(f"Error: Fail to add user '{args.username}'")
    else:
        print(f"User '{args.username}' with password '{password}' was added")


def list_frontent_cmd_handler(self, args: Namespace, remaining: List[str]) -> None:
    """List users of sighthouse frontend"""
    database = FrontendDatabase(args.database, args.repo_url, exist_ok=True)
    for user in database.list_users():
        print(user.name)


def remove_frontent_cmd_handler(self, args: Namespace, remaining: List[str]) -> None:
    """Remove user from sighthouse frontend"""
    database = FrontendDatabase(args.database, args.repo_url, exist_ok=True)
    user = database.get_user_by_name(args.username)
    if not user:
        print(f"Error: Fail to find user '{args.username}'")
        return

    if not database.delete_user(user):
        print(f"Error: Fail to delete user '{args.username}'")
    else:
        print(f"User '{args.username}' deleted")


def run_celery_worker(url: str, ghidradir: str, worker: Optional[int] = None) -> None:
    """Start the celery worker that handle analysis"""
    script_path = Path(__file__).resolve().parent / "runner.py"
    args = [sys.executable, str(script_path), url, ghidradir]
    if worker is not None:
        args += ["--worker", str(worker)]

    process = Popen(args)
    process.wait()


def start_frontent_cmd_handler(self, args: Namespace, remaining: List[str]) -> None:
    """Start sighthouse frontend"""
    basicConfig(level=INFO if not args.debug else DEBUG)
    logger = getLogger(__name__)

    database = FrontendDatabase(args.database, args.repo_url, exist_ok=True)
    if args.ghidra_dir is None:
        print("Error: GHIDRA_INSTALL_DIR or ghidra-dir not set")
        return

    api = FrontendRestAPI(
        database,
        args.worker_url,
        Path(args.ghidra_dir),
        args.bsim_url,
        args.fidb_url,
        logger,
    )

    api2 = LocalRestAPI(database)
    t3 = Process(
        target=run_celery_worker, args=(args.worker_url, args.ghidra_dir, args.worker)
    )

    api.start()
    api2.start()
    t3.start()

    def handle_sigint(sig, frame):
        print("\nStopping all processes...")
        api.shutdown()
        api2.shutdown()
        t3.terminate()

        for p in [api, api2, t3]:
            p.join()  # type: ignore[attr-defined]

        sys.exit(0)

    # Handle Ctrl-C
    signal.signal(signal.SIGINT, handle_sigint)

    api.join()
    api2.join()
    t3.join()


def reset_password_frontent_cmd_handler(
    self, args: Namespace, remaining: List[str]
) -> None:
    """Reset password of a user of  sighthouse frontend"""

    database = FrontendDatabase(args.database, args.repo_url, exist_ok=True)
    password = args.password
    if not password:
        # Auto-generate a new password
        password = token_hex(16)

    user = database.get_user_by_name(args.username)
    if not user:
        print(f"Error: Fail to find user '{args.username}'")
        return

    user.hash = generate_password_hash(password, method="pbkdf2:sha256")
    if not database.update_user(user):
        print(f"Error: Fail to reset password of user '{args.username}'")
    else:
        print(f"Password of user '{args.username}' reset. New password: '{password}'")


def add_to_cli(app: SightHouseCommandLine) -> None:
    """Add frontend argument parser to main command-line app"""
    # Setup frontend argument parser
    parser_frontend = app.add_command_group(
        "frontend", "frontend_command", help="Handle %(prog)s frontend"
    )
    if parser_frontend is not None:
        parser_frontend.add_argument(
            "-r",
            "--repo-url",
            type=str,
            required=False,
            help="Url of the repository to upload files",
            default="local://data",
        )
        parser_frontend.add_argument(
            "-g",
            "--ghidra-dir",
            type=str,
            required=False,
            default=(
                os.environ["GHIDRA_INSTALL_DIR"]
                if "GHIDRA_INSTALL_DIR" in os.environ
                else None
            ),
            help="Path to the ghidra root directory",
        )
        parser_frontend.add_argument(
            "-d",
            "--database",
            type=str,
            help="Database URI",
            default="sqlite://frontend.db",
        )

        parser_frontend_add_user = parser_frontend.add_command(
            "add-user", add_frontent_cmd_handler, help="Add a user to %(prog)s frontend"
        )
        if parser_frontend_add_user is not None:
            parser_frontend_add_user.add_argument(
                "username", type=str, help="Username of the user to add"
            )
            parser_frontend_add_user.add_argument(
                "-p",
                "--password",
                type=str,
                help="Password for new user, leave empty to auto-generate one",
            )

        parser_frontend.add_command(
            "list-user",
            list_frontent_cmd_handler,
            help="List users of %(prog)s frontend",
        )
        parser_frontend_rm_user = parser_frontend.add_command(
            "rm-user",
            remove_frontent_cmd_handler,
            help="Remove a user from %(prog)s frontend",
        )
        if parser_frontend_rm_user is not None:
            parser_frontend_rm_user.add_argument(
                "username", type=str, help="Username of the user to remove"
            )

        parser_frontend_start = parser_frontend.add_command(
            "start", start_frontent_cmd_handler, help="Start %(prog)s frontend"
        )
        if parser_frontend_start is not None:
            parser_frontend_start.add_argument(
                "-b",
                "--bsim-url",
                type=str,
                nargs="+",
                help="List of BSIM urls",
                # default=["postgresql://bsim_user:password@localhost:5432/bsim"],
            )
            parser_frontend_start.add_argument(
                "-f",
                "--fidb-url",
                type=str,
                nargs="+",
                help="List of FIDB urls",
                # default=["local://fidb.sig"],
            )
            parser_frontend_start.add_argument(
                "-w",
                "--worker-url",
                type=str,
                required=False,
                help="Url of the worker server",
                default="redis://localhost:6379/0",
            )
            parser_frontend_start.add_argument(
                "--worker",
                type=int,
                required=False,
                help="Number of concurrent task analyzer worker can perform",
                default=1,
            )

        parser_frontend_reset_pwd = parser_frontend.add_command(
            "reset-pwd",
            reset_password_frontent_cmd_handler,
            help="Reset password of a user of %(prog)s frontend",
        )
        if parser_frontend_reset_pwd is not None:
            parser_frontend_reset_pwd.add_argument(
                "username",
                type=str,
                help="Username of the user which have it's password reset",
            )
            parser_frontend_reset_pwd.add_argument(
                "-p",
                "--password",
                type=str,
                help="Password for user, leave empty to auto-generate one",
            )
