import io
import unittest
from pathlib import Path
from argparse import Namespace
from contextlib import redirect_stdout
from tempfile import TemporaryDirectory
from unittest.mock import patch

from werkzeug.security import check_password_hash

from sighthouse.frontend.cli import (
    add_frontent_cmd_handler,
    list_frontent_cmd_handler,
    remove_frontent_cmd_handler,
    reset_password_frontent_cmd_handler,
    add_to_cli,
)
from sighthouse.frontend.database import FrontendDatabase


class FrontendCliTestBase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.db_uri = f"sqlite://{self.tmpdir.name}/frontend.db"
        self.repo_url = f"local://{self.tmpdir.name}/repo/"
        # Create the database file once up front.
        self.db = FrontendDatabase(self.db_uri, self.repo_url, exist_ok=True)

    def _args(self, **overrides):
        args = Namespace(
            debug=False,
            database=self.db_uri,
            repo_url=self.repo_url,
            username="alice",
            password=None,
        )
        for k, v in overrides.items():
            setattr(args, k, v)
        return args

    def tearDown(self):
        self.db.close()

    def test_add_user_persists_and_reports_password(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            add_frontent_cmd_handler(
                None, self._args(username="alice", password="s3cret"), []
            )
        out = buf.getvalue()
        self.assertIn("alice", out)
        self.assertIn("s3cret", out)

        user = self.db.get_user_by_name("alice")
        self.assertIsNotNone(user)
        # The stored hash verifies against the supplied password.
        self.assertTrue(check_password_hash(user.hash, "s3cret"))

    def test_add_user_autogenerates_password_when_absent(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            add_frontent_cmd_handler(
                None, self._args(username="bob", password=None), []
            )
        # A password was generated and printed.
        self.assertIn("password", buf.getvalue())
        self.assertIsNotNone(self.db.get_user_by_name("bob"))

    def test_list_prints_usernames(self):
        add_frontent_cmd_handler(None, self._args(username="alice", password="p"), [])
        add_frontent_cmd_handler(None, self._args(username="bob", password="p"), [])

        buf = io.StringIO()
        with redirect_stdout(buf):
            list_frontent_cmd_handler(None, self._args(), [])
        out = buf.getvalue()
        self.assertIn("alice", out)
        self.assertIn("bob", out)

    def test_remove_existing_user(self):
        add_frontent_cmd_handler(None, self._args(username="alice", password="p"), [])

        buf = io.StringIO()
        with redirect_stdout(buf):
            remove_frontent_cmd_handler(None, self._args(username="alice"), [])
        self.assertIn("deleted", buf.getvalue())
        self.assertIsNone(self.db.get_user_by_name("alice"))

    def test_remove_unknown_user_reports_error(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            remove_frontent_cmd_handler(None, self._args(username="ghost"), [])
        self.assertIn("Fail to find user", buf.getvalue())

    def test_reset_changes_stored_hash(self):
        add_frontent_cmd_handler(None, self._args(username="alice", password="old"), [])
        old_hash = self.db.get_user_by_name("alice").hash

        buf = io.StringIO()
        with redirect_stdout(buf):
            reset_password_frontent_cmd_handler(
                None, self._args(username="alice", password="new"), []
            )
        out = buf.getvalue()
        self.assertIn("reset", out)

        new_user = self.db.get_user_by_name("alice")
        self.assertNotEqual(new_user.hash, old_hash)
        self.assertTrue(check_password_hash(new_user.hash, "new"))

    def test_reset_unknown_user_reports_error(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            reset_password_frontent_cmd_handler(
                None, self._args(username="ghost", password="x"), []
            )
        self.assertIn("Fail to find user", buf.getvalue())

    def test_registers_frontend_commands(self):
        import argparse
        from sighthouse.cli import SightHouseCommandLine

        app = SightHouseCommandLine(prog="sighthouse")
        app.add_subparsers(dest="command")

        add_to_cli(app)

        self.assertIn("frontend", app._commands)
        sub = next(a for a in app._actions if isinstance(a, argparse._SubParsersAction))
        frontend_parser = sub.choices["frontend"]
        for cmd in ("add-user", "list-user", "rm-user", "start", "reset-pwd"):
            self.assertIn(cmd, frontend_parser._commands)


if __name__ == "__main__":
    unittest.main()
