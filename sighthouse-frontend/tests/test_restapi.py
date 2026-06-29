import io
import logging
import secrets
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from sighthouse.frontend.database import FrontendDatabase
from sighthouse.frontend.restapi import FrontendRestAPI
from sighthouse.frontend.model import User

LANGUAGES = ["x86:LE:64:default", "ARM:LE:32:v8"]


class RestApiTestBase(unittest.TestCase):
    PASSWORD = "s3cret-pw"

    def setUp(self):
        self.tmpdir = TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.db = FrontendDatabase(
            "sqlite://:memory:", f"local://{self.tmpdir.name}/", exist_ok=True
        )
        self.user = self.db.add_user(
            User(
                User.INVALID_ID,
                f"alice_{secrets.token_hex(6)}",
                generate_password_hash(self.PASSWORD, method="pbkdf2:sha256"),
            )
        )

        # Avoid binding a real port and depending on a Ghidra install.
        lang_patcher = patch(
            "sighthouse.frontend.restapi.get_ghidra_languages",
            return_value=LANGUAGES,
        )
        lang_patcher.start()
        self.addCleanup(lang_patcher.stop)

        with patch("sighthouse.core.utils.api.make_server"):
            self.api = FrontendRestAPI(
                self.db,
                "redis://localhost:6379/0",
                Path("/nonexistent/ghidra"),
                bsims=[],
                fidbs=[],
                logger=logging.getLogger("test_restapi"),
            )
        self.client = self.api._FrontendRestAPI__app.test_client()

    def login(self):
        resp = self.client.post(
            "/api/v1/login",
            json={"user": self.user.name, "password": self.PASSWORD},
        )
        self.assertEqual(resp.status_code, 200)

    def _upload(self, name="ls.bin", content=b"\x7fELF binary"):
        return self.client.post(
            "/api/v1/uploads",
            data={"filename": (io.BytesIO(content), name)},
            content_type="multipart/form-data",
        )


class TestPublicRoutes(RestApiTestBase):
    def test_ping(self):
        resp = self.client.get("/api/v1/ping")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"success": "Pong !"})

    def test_languages_are_public(self):
        resp = self.client.get("/api/v1/languages")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["languages"], LANGUAGES)


class TestAuth(RestApiTestBase):
    def test_login_missing_fields(self):
        resp = self.client.post("/api/v1/login", json={"user": "alice"})
        self.assertEqual(resp.status_code, 400)

    def test_login_invalid_credentials(self):
        resp = self.client.post(
            "/api/v1/login", json={"user": self.user.name, "password": "wrong"}
        )
        self.assertEqual(resp.status_code, 401)

    def test_login_success(self):
        resp = self.client.post(
            "/api/v1/login",
            json={"user": self.user.name, "password": self.PASSWORD},
        )
        self.assertEqual(resp.status_code, 200)

    def test_protected_route_requires_login(self):
        resp = self.client.get("/api/v1/uploads")
        self.assertEqual(resp.status_code, 401)

    def test_logout_after_login(self):
        self.login()
        resp = self.client.post("/api/v1/logout")
        self.assertEqual(resp.status_code, 200)


class TestFileEndpoints(RestApiTestBase):
    def test_upload_list_and_delete_cycle(self):
        self.login()

        # Upload
        resp = self._upload()
        self.assertEqual(resp.status_code, 201)
        self.assertIn("file", resp.get_json())

        # List shows the uploaded file
        resp = self.client.get("/api/v1/uploads")
        self.assertEqual(resp.status_code, 200)
        files = resp.get_json()["files"]
        self.assertEqual(len(files), 1)
        file_hash = files[0]["hash"]

        # Delete by hash
        resp = self.client.delete(f"/api/v1/uploads/{file_hash}")
        self.assertEqual(resp.status_code, 200)

        # Deleting again -> not found
        resp = self.client.delete(f"/api/v1/uploads/{file_hash}")
        self.assertEqual(resp.status_code, 404)

    def test_upload_missing_field(self):
        self.login()
        resp = self.client.post(
            "/api/v1/uploads", data={}, content_type="multipart/form-data"
        )
        self.assertEqual(resp.status_code, 400)

    def test_upload_empty_filename(self):
        self.login()
        resp = self.client.post(
            "/api/v1/uploads",
            data={"filename": (io.BytesIO(b"x"), "")},
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 400)


class TestProgramEndpoints(RestApiTestBase):
    def _upload_file_id(self):
        resp = self._upload()
        return resp.get_json()["file"]

    def test_create_program_requires_programs_list(self):
        self.login()
        resp = self.client.post("/api/v1/programs", json={"nope": []})
        self.assertEqual(resp.status_code, 400)

    def test_create_program_invalid_language(self):
        self.login()
        file_id = self._upload_file_id()
        resp = self.client.post(
            "/api/v1/programs",
            json={"programs": [{"name": "p", "file": file_id, "language": "BOGUS"}]},
        )
        self.assertEqual(resp.status_code, 400)

    def test_create_program_invalid_file(self):
        self.login()
        resp = self.client.post(
            "/api/v1/programs",
            json={"programs": [{"name": "p", "file": 9999, "language": LANGUAGES[0]}]},
        )
        self.assertEqual(resp.status_code, 400)

    def test_create_list_get_and_delete_program(self):
        self.login()
        file_id = self._upload_file_id()

        # Create
        resp = self.client.post(
            "/api/v1/programs",
            json={
                "programs": [
                    {"name": "myprog", "file": file_id, "language": LANGUAGES[0]}
                ]
            },
        )
        self.assertEqual(resp.status_code, 201)

        # List
        resp = self.client.get("/api/v1/programs")
        self.assertEqual(resp.status_code, 200)
        programs = resp.get_json()["programs"]
        self.assertEqual(len(programs), 1)
        program_id = programs[0]["id"]

        # Get one
        resp = self.client.get(f"/api/v1/programs/{program_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["name"], "myprog")

        # Get unknown
        resp = self.client.get("/api/v1/programs/999999")
        self.assertEqual(resp.status_code, 404)

        # Delete
        resp = self.client.delete(f"/api/v1/programs/{program_id}")
        self.assertEqual(resp.status_code, 200)

    def test_get_analysis_not_found(self):
        self.login()
        resp = self.client.get("/api/v1/programs/12345/analyze")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
