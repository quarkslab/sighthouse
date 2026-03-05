"""SightHouse command-line"""

from argparse import ArgumentParser, Namespace, _SubParsersAction
from typing import Callable, Optional, TypeGuard, Any
from traceback import format_exception
from pathlib import Path
import sys


def _get_version() -> str:
    """
    Dynamically return the version of the 'sighthouse' module.

    Returns:
        str: The version number of the 'sighthouse-core' module.
    """

    try:
        from importlib.metadata import version, PackageNotFoundError

        return version("sighthouse-core")
    except PackageNotFoundError:
        return "?.?.?"


# Make mypy happy
def _is_subparser_action(e: Any) -> TypeGuard[_SubParsersAction]:
    """
    Determine if the given argument is an instance of _SubParsersAction.

    This helper function is used to filter elements that are of
    type _SubParsersAction from a collection of actions.

    Args:
        e (Any): The object to check the type of.

    Returns:
        TypeGuard[_SubParsersAction]: True if `e` is an instance of
                                        _SubParsersAction, False otherwise.
    """
    return isinstance(e, _SubParsersAction)


class SightHouseCommandLine(ArgumentParser):
    """
    A command-line interface for parsing and managing commands.

    The CommandLine class extends the ArgumentParser from the argparse
    module to allow the addition of command groups and command handlers.
    It maintains a registry of commands and their corresponding handlers,
    facilitating modular command processing.
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize the ArgumentParser parser.

        Args:
            *args: Variable length argument list for ArgumentParser.
            **kwargs: Arbitrary keyword arguments for ArgumentParser.
        """
        super().__init__(*args, **kwargs)
        self._commands: dict = {}

    def add_command_group(
        self, name: str, dest: str, *args, **kwargs
    ) -> Optional["SightHouseCommandLine"]:
        """
        Add a new command group to the command line parser.

        Args:
            name (str): The name of the command group.
            dest (str): The destination variable to store the group choice.
            *args: Variable length argument list for the subparser.
            **kwargs: Arbitrary keyword arguments for the subparser.

        Returns:
            Optional[SightHouseCommandLine]: The command parser for the group if
                                             added successfully, otherwise None.
        """
        # Add the new command
        parser = self.add_command(name, self._run, *args, **kwargs)
        if parser is None:
            return None

        # Add a subparser that will act as a group
        parser.add_subparsers(dest=dest)
        return parser

    def add_command(
        self, name: str, handler: Callable, *args, **kwargs
    ) -> Optional["SightHouseCommandLine"]:
        """
        Add a command and its handler to the command line parser.

        This method associates a command name with a corresponding
        handler function and adds it to the current command line
        structure.

        Args:
            name (str): The name of the command to add.
            handler (Callable): The function that will handle the command.
            *args: Variable length argument list for the parser.
            **kwargs: Arbitrary keyword arguments for the parser.

        Returns:
            Optional[SightHouseCommandLine]: The parser for the new command if
                                             added successfully, otherwise None.
        """
        # ArgumentParser can have only up to one subparser
        subparser: Optional[_SubParsersAction] = next(
            filter(_is_subparser_action, self._actions), None
        )
        if subparser is not None:
            parser = subparser.add_parser(name, *args, **kwargs)
            self._commands.update({name: handler})
            return parser

        return None

    def banner(self) -> None:
        """
        Print a fancy banner on stdout
        """
        with open(Path(__file__).parent / "logo.ans", "rb") as fp:
            print(fp.read().decode(), end="")

        print(f"""
                 SightHouse v{_get_version()}
                    by: Fenrisfulsur & Madsquirrels
        """)

    def run(self) -> None:
        """
        Run the SightHouseCommandLine parser. Parse arguments provided on the command line and
        call the registered handler accordingly.
        """
        if len(sys.argv) <= 1:
            self.banner()
            self.print_help()
            sys.exit(0)

        args, remaining = self.parse_known_args()
        return self._run(self, args, remaining)

    def _run(
        self, obj: "SightHouseCommandLine", args: Namespace, remaining: list[str]
    ) -> None:
        """
        Run the SightHouseCommandLine parser and call the registered accordingly. The parser
        operate recursively until all arguments have been parsed.
        """
        # ArgumentParser can have only up to one subparser
        subparser: Optional[_SubParsersAction] = next(
            filter(_is_subparser_action, obj._actions), None
        )
        if subparser is None:
            print("Error: Internal error: Invalid subparser")
            sys.exit(1)

        command = vars(args).get(subparser.dest)
        if not command:
            obj.print_help()
            sys.exit(0)

        try:
            handler = obj._commands.get(command)
            sub_obj = subparser.choices.get(command)
            if handler and sub_obj:
                handler(sub_obj, args, remaining)
        except Exception as e:
            print(e)
            print("".join(format_exception(e)))
            sys.exit(1)
        except KeyboardInterrupt:
            print("Interrupted")
            sys.exit(0)


def main():
    """Main entrypoint of the SightHouse CLI"""
    app = SightHouseCommandLine(prog="sighthouse", description="SightHouse CLI")
    # Add default arguments
    app.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_get_version()}",
    )
    app.add_argument(
        "-d", "--debug", default=False, action="store_true", help="Enable debug"
    )
    # Add default subparser
    app.add_subparsers(title="COMMAND", dest="command")

    empty: bool = True
    try:
        from sighthouse.frontend.cli import add_to_cli  # type: ignore[import-untyped]

        add_to_cli(app)
        empty = False
    except ModuleNotFoundError:
        pass

    try:
        from sighthouse.pipeline.cli import add_to_cli  # type: ignore[import-untyped]

        add_to_cli(app)
        empty = False
    except ModuleNotFoundError:
        pass

    try:
        from sighthouse.client.cli import add_to_cli  # type: ignore[import-untyped]

        add_to_cli(app)
        empty = False
    except ModuleNotFoundError:
        pass

    if empty:
        print(
            "Error: It appear that you have install sighthouse[core] alone. This package "
            "does not offer\nany features, consider installing sighthouse[frontend], "
            "sighthouse[client] or sighthouse[pipeline]"
        )
        sys.exit(1)

    app.run()


if __name__ == "__main__":
    main()
