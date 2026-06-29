import secrets
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sighthouse.frontend.database import FrontendDatabase
from sighthouse.frontend.localapi import LocalRestAPI
from sighthouse.frontend.model import (
    User,
    File,
    Program,
    Section,
    Function,
    Analysis,
)


class LocalApiTestBase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.db = FrontendDatabase(
            "sqlite://:memory:", f"local://{self.tmpdir.name}/", exist_ok=True
        )

        # Constructing ServerThread normally binds a socket; avoid that.
        with patch("sighthouse.core.utils.api.make_server"):
            self.api = LocalRestAPI(self.db)
        self.client = self.api._LocalRestAPI__app.test_client()

        # Build the object graph the routes need: user -> file -> program -> section.
        self.user = self.db.add_user(
            User(User.INVALID_ID, f"u_{secrets.token_hex(8)}", "h")
        )
        self.file = self.db.add_file_user(
            File(File.INVALID_ID, "f.bin", self.user.id, content=b"data")
        )
        self.program = self.db.add_program(
            Program(Program.INVALID_ID, "prog", self.user.id, "c", self.file.id)
        )
        self.section = self.db.add_section(
            Section(
                Section.INVALID_ID,
                ".text",
                self.program.id,
                0,
                100,
                200,
                "r-x",
                "code",
            )
        )

    def tearDown(self):
        self.db.close()


class TestPing(LocalApiTestBase):
    def test_ping_returns_pong(self):
        resp = self.client.get("/api/v1/ping")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"ping": "pong"})


class TestCreateFunctions(LocalApiTestBase):
    def _url(self, section_id=None):
        sid = self.section.id if section_id is None else section_id
        return f"/api/v1/programs/{self.program.id}/sections/{sid}/functions"

    def test_create_functions_persists_them(self):
        resp = self.client.post(
            self._url(),
            json={"functions": [{"name": "main", "offset": 100}]},
        )
        self.assertEqual(resp.status_code, 201)
        returned = resp.get_json()["functions"]
        self.assertEqual(len(returned), 1)
        self.assertEqual(returned[0]["name"], "main")
        # The function is now retrievable from the section.
        self.assertEqual(len(self.db.list_section_functions(self.section.id)), 1)

    def test_unknown_section_returns_404(self):
        resp = self.client.post(
            self._url(section_id=9999),
            json={"functions": [{"name": "main", "offset": 100}]},
        )
        self.assertEqual(resp.status_code, 404)

    def test_missing_functions_list_returns_400(self):
        resp = self.client.post(self._url(), json={"nope": []})
        self.assertEqual(resp.status_code, 400)

    def test_invalid_function_entry_returns_400(self):
        # offset must be an int -> Function.from_dict raises -> 400
        resp = self.client.post(
            self._url(),
            json={"functions": [{"name": "main", "offset": "not-an-int"}]},
        )
        self.assertEqual(resp.status_code, 400)


class TestDeleteFunctions(LocalApiTestBase):
    def test_delete_section_functions(self):
        self.db.add_function(
            Function(Function.INVALID_ID, "f", 100, self.section.id, {})
        )
        url = f"/api/v1/programs/{self.program.id}/sections/{self.section.id}/functions"
        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.db.list_section_functions(self.section.id), [])


class TestCreateMatches(LocalApiTestBase):
    def setUp(self):
        super().setUp()
        self.function = self.db.add_function(
            Function(Function.INVALID_ID, "f", 100, self.section.id, {})
        )

    def _url(self, function_id=None):
        fid = self.function.id if function_id is None else function_id
        return (
            f"/api/v1/programs/{self.program.id}/sections/{self.section.id}"
            f"/functions/{fid}/matches"
        )

    def test_create_matches_persists_them(self):
        resp = self.client.post(
            self._url(),
            json={"matches": [{"name": "memcpy", "metadata": {"lib": "libc"}}]},
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.get_json()["matches"][0]["name"], "memcpy")

    def test_unknown_function_returns_404(self):
        resp = self.client.post(
            self._url(function_id=9999),
            json={"matches": [{"name": "memcpy", "metadata": {}}]},
        )
        self.assertEqual(resp.status_code, 404)

    def test_missing_matches_list_returns_400(self):
        resp = self.client.post(self._url(), json={"oops": 1})
        self.assertEqual(resp.status_code, 400)


class TestUpdateAnalysis(LocalApiTestBase):
    def _url(self, program_id=None):
        pid = self.program.id if program_id is None else program_id
        return f"/api/v1/programs/{pid}/analyze"

    def test_update_existing_analysis(self):
        self.db.add_analysis(
            Analysis(self.program.id, self.user.id, {"status": "pending"})
        )
        resp = self.client.put(
            self._url(), json={"status": "running", "progress": "50%"}
        )
        self.assertEqual(resp.status_code, 200)

    def test_update_missing_analysis_returns_404(self):
        resp = self.client.put(self._url(), json={"status": "running", "progress": "x"})
        self.assertEqual(resp.status_code, 404)

    def test_finished_status_cleans_up_and_succeeds(self):
        self.db.add_analysis(
            Analysis(self.program.id, self.user.id, {"status": "running"})
        )
        # Deleting a non-existent config file is tolerated; the call still succeeds.
        resp = self.client.put(
            self._url(), json={"status": "finished", "progress": "100%"}
        )
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
