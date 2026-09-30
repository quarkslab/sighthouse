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

from sighthouse.cli import SightHouseCommandLine
from sighthouse.frontend.database import FrontendDatabase
from sighthouse.frontend.model import User
from sighthouse.frontend.restapi import FrontendRestAPI
from sighthouse.frontend.localapi import LocalRestAPI


def add_frontent_cmd_handler(self, args: Namespace, remaining: List[str]) -> None:
    """Add a user to sighthouse frontend"""
    basicConfig(level=INFO if not args.debug else DEBUG)
    logger = getLogger(__name__)

    database = FrontendDatabase(args.database, exist_ok=True, logger=logger)
    password = args.password
    if not password:
        # Auto-generate a new password
        password = token_hex(16)

    user = database.add_user(
        User.create(args.username, password, "admin" if args.admin else "user")
    )
    if not user:
        print(f"Error: Fail to add user '{args.username}'")
    else:
        print(
            f"{'Administrator' if args.admin else 'User'} '{args.username}' with password '{password}' was added"
        )


def list_frontent_cmd_handler(self, args: Namespace, remaining: List[str]) -> None:
    """List users of sighthouse frontend"""
    basicConfig(level=INFO if not args.debug else DEBUG)
    logger = getLogger(__name__)

    database = FrontendDatabase(args.database, exist_ok=True, logger=logger)
    for user in database.list_users():
        print(f"{user.name} ({user.role})")


def set_role_frontent_cmd_handler(self, args: Namespace, remaining: List[str]) -> None:
    """Set the role of a user of sighthouse frontend"""
    basicConfig(level=INFO if not args.debug else DEBUG)
    logger = getLogger(__name__)

    database = FrontendDatabase(args.database, exist_ok=True, logger=logger)
    user = database.get_user_by_name(args.username)
    if not user:
        print(f"Error: Fail to find user '{args.username}'")
        return

    user.role = args.role
    if not database.update_user(user):
        print(f"Error: Fail to update user '{args.username}'")
    else:
        print(f"User '{args.username}' role set to '{args.role}'")


def remove_frontent_cmd_handler(self, args: Namespace, remaining: List[str]) -> None:
    """Remove user from sighthouse frontend"""
    basicConfig(level=INFO if not args.debug else DEBUG)
    logger = getLogger(__name__)

    database = FrontendDatabase(args.database, exist_ok=True, logger=logger)
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

    # Own process group so SIGTERM also reaches the celery children
    process = Popen(args, start_new_session=True)

    def _stop(signum, frame) -> None:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

    signal.signal(signal.SIGTERM, _stop)
    try:
        process.wait()
    except KeyboardInterrupt:
        _stop(signal.SIGINT, None)
        process.wait()


def start_frontent_cmd_handler(self, args: Namespace, remaining: List[str]) -> None:
    """Start sighthouse frontend"""
    basicConfig(level=INFO if not args.debug else DEBUG)
    logger = getLogger(__name__)

    database = FrontendDatabase(args.database, exist_ok=True, logger=logger)

    config = database.get_config()

    # Apply CLI overrides when provided
    for obj, attr, value in (
        (config, "repo_url", args.repo_url),
        (config, "ghidra_dir", args.ghidra_dir),
        (config, "host", args.host),
        (config, "port", args.port),
        (config, "worker_url", args.worker_url),
        (config, "worker_count", args.worker),
        (config.bsim_config, "urls", args.bsim_url),
        (config.fidb_config, "urls", args.fidb_url),
    ):
        if value is not None:
            setattr(obj, attr, value)

    if config.ghidra_dir is None or not Path(config.ghidra_dir).is_dir():
        print("Error: set -g/--ghidra-dir or GHIDRA_INSTALL_DIR")
        return

    database.set_config(config)
    database.set_repo(config.repo_url, exist_ok=True)

    api = FrontendRestAPI(database, logger)
    local_api = LocalRestAPI(database)
    celery_process = Process(
        target=run_celery_worker,
        args=(config.worker_url, config.ghidra_dir, config.worker_count),
    )

    logger.info(
        f"SightHouse frontend server listening on http://{api.host}:{api.port}/"
    )
    api.start()
    local_api.start()
    celery_process.start()

    def stop_all() -> None:
        api.shutdown()
        local_api.shutdown()
        celery_process.terminate()
        for p in [api, local_api, celery_process]:
            p.join()  # type: ignore[attr-defined]

    def handle_sigint(sig, frame):
        logger.info("Stopping all processes...")
        stop_all()
        sys.exit(0)

    def handle_restart(sig, frame):
        logger.info("Restarting SightHouse frontend...")
        stop_all()
        os.execv(sys.executable, [sys.executable, *sys.argv])

    signal.signal(signal.SIGINT, handle_sigint)
    # Sent by the /api/v1/restart endpoint (POSIX only)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, handle_restart)

    api.join()
    local_api.join()
    celery_process.join()


def reset_password_frontent_cmd_handler(
    self, args: Namespace, remaining: List[str]
) -> None:
    """Reset password of a user of sighthouse frontend"""
    basicConfig(level=INFO if not args.debug else DEBUG)
    logger = getLogger(__name__)

    database = FrontendDatabase(args.database, exist_ok=True, logger=logger)
    password = args.password
    if not password:
        # Auto-generate a new password
        password = token_hex(16)

    user = database.get_user_by_name(args.username)
    if not user:
        print(f"Error: Fail to find user '{args.username}'")
        return

    user.set_password(password)
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
        parser_frontend_add_user = parser_frontend.add_command(
            "add-user", add_frontent_cmd_handler, help="Add a user to %(prog)s frontend"
        )
        if parser_frontend_add_user is not None:
            parser_frontend_add_user.add_argument(
                "username", type=str, help="Username of the user to add"
            )
            parser_frontend_add_user.add_argument(
                "--admin", action="store_true", help="Add the user as admin"
            )
            parser_frontend_add_user.add_argument(
                "-p",
                "--password",
                type=str,
                help="Password for new user, leave empty to auto-generate one",
            )

        parser_frontend_list = parser_frontend.add_command(
            "list-user",
            list_frontent_cmd_handler,
            help="List users of %(prog)s frontend",
        )

        parser_frontend_set_role = parser_frontend.add_command(
            "set-role",
            set_role_frontent_cmd_handler,
            help="Set the role of a user of %(prog)s frontend",
        )
        if parser_frontend_set_role is not None:
            parser_frontend_set_role.add_argument(
                "username", type=str, help="Username of the user to update"
            )
            parser_frontend_set_role.add_argument(
                "role", type=str, choices=User.VALID_ROLES, help="Role to assign"
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

        # @NOTE: Adding a default=... here break the CLI overwrite mecanism
        parser_frontend_start = parser_frontend.add_command(
            "start", start_frontent_cmd_handler, help="Start %(prog)s frontend"
        )
        if parser_frontend_start is not None:
            parser_frontend_start.add_argument(
                "-r",
                "--repo-url",
                type=str,
                help="Url of the repository to upload files",
            )
            parser_frontend_start.add_argument(
                "--host",
                type=str,
                help="Host of the frontend server (default: 0.0.0.0)",
            )
            parser_frontend_start.add_argument(
                "--port",
                type=int,
                help="Port of the frontend server",
            )
            parser_frontend_start.add_argument(
                "-g",
                "--ghidra-dir",
                type=str,
                default=os.environ.get("GHIDRA_INSTALL_DIR"),
                help="Path to the ghidra root directory",
            )
            parser_frontend_start.add_argument(
                "-b", "--bsim-url", type=str, nargs="+", help="List of BSIM urls"
            )
            parser_frontend_start.add_argument(
                "-f", "--fidb-url", type=str, nargs="+", help="List of FIDB urls"
            )
            parser_frontend_start.add_argument(
                "-w", "--worker-url", type=str, help="Url of the worker server"
            )
            parser_frontend_start.add_argument(
                "--worker",
                type=int,
                help="Number of concurrent task analyzer worker can perform",
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

        # Add database arguments to all the subcommands
        for parser in (
            parser_frontend_add_user,
            parser_frontend_list,
            parser_frontend_set_role,
            parser_frontend_rm_user,
            parser_frontend_start,
            parser_frontend_reset_pwd,
        ):
            if parser is not None:
                parser.add_argument(
                    "-d", "--database", type=str, help="Database URI", required=True
                )
