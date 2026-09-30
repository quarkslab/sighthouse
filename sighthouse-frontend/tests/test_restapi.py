import io
import logging
import secrets
import signal
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from werkzeug.security import generate_password_hash, check_password_hash

from sighthouse.frontend.database import FrontendDatabase
from sighthouse.frontend.restapi import FrontendRestAPI
from sighthouse.frontend.model import User, FrontendConfig

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

        config = FrontendConfig("sqlite://:memory:")
        config.worker_url = "redis://localhost:6379/0"
        config.ghidra_dir = "/nonexistent/ghidra"
        self.db.set_config(config)

        with patch("sighthouse.core.utils.api.make_server"):
            self.api = FrontendRestAPI(
                self.db,
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

    def add_db_user(self, name, password="pw", role="user"):
        """Insert a user straight into the DB (bypassing the API)."""
        return self.db.add_user(
            User(
                User.INVALID_ID,
                name,
                generate_password_hash(password, method="pbkdf2:sha256"),
                role=role,
            )
        )

    def as_admin(self):
        """Promote the default user to admin and open an authenticated session."""
        self.user.role = "admin"
        self.db.update_user(self.user)
        self.login()


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


# Admin-only endpoints. Each is protected by @admin_required, which must
# reject anonymous callers (401) and authenticated non-admins (403) *before* doing
# any work, so the method/path is enough to exercise the access wall.
ADMIN_ENDPOINTS = [
    ("GET", "/api/v1/users"),
    ("POST", "/api/v1/users"),
    ("PUT", "/api/v1/users"),
    ("DELETE", "/api/v1/users"),
    ("GET", "/api/v1/config"),
    ("PUT", "/api/v1/config"),
    ("POST", "/api/v1/restart"),
]


class TestAccessControl(RestApiTestBase):
    """The admin surface must be gated by authentication *and* role."""

    def test_admin_endpoints_reject_anonymous(self):
        for method, path in ADMIN_ENDPOINTS:
            with self.subTest(method=method, path=path):
                resp = self.client.open(path, method=method)
                self.assertEqual(resp.status_code, 401)

    def test_admin_endpoints_reject_authenticated_non_admin(self):
        self.login()  # self.user is a plain 'user'
        for method, path in ADMIN_ENDPOINTS:
            with self.subTest(method=method, path=path):
                resp = self.client.open(path, method=method)
                self.assertEqual(resp.status_code, 403)

    def test_admin_endpoints_allow_admin(self):
        self.as_admin()
        for method, path in ADMIN_ENDPOINTS:
            with self.subTest(method=method, path=path):
                resp = self.client.open(path, method=method)
                # A real admin is never blocked by the auth wall (a bare request
                # may still be a 400 for a missing body, but never 401/403).
                self.assertNotIn(resp.status_code, (401, 403))

    def test_me_requires_login(self):
        resp = self.client.get("/api/v1/me")
        self.assertEqual(resp.status_code, 401)

    def test_me_returns_current_user(self):
        self.login()
        resp = self.client.get("/api/v1/me")
        self.assertEqual(resp.status_code, 200)
        user = resp.get_json()["user"]
        self.assertEqual(user["name"], self.user.name)
        self.assertEqual(user["role"], "user")


class TestNoSensitiveLeak(RestApiTestBase):
    """Responses must never expose password hashes or server secrets."""

    def test_users_list_excludes_hash(self):
        self.as_admin()
        resp = self.client.get("/api/v1/users")
        self.assertEqual(resp.status_code, 200)
        for item in resp.get_json()["users"]:
            self.assertEqual(set(item.keys()), {"id", "name", "role"})
            self.assertNotIn("hash", item)
        # The raw hash string must not appear anywhere in the payload.
        self.assertNotIn(self.user.hash, resp.get_data(as_text=True))

    def test_me_excludes_hash(self):
        self.login()
        resp = self.client.get("/api/v1/me")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(set(resp.get_json()["user"].keys()), {"id", "name", "role"})
        self.assertNotIn(self.user.hash, resp.get_data(as_text=True))


class TestSetupWizard(RestApiTestBase):
    """The setup endpoint bootstraps the first admin, but only on an empty DB."""

    def _fresh_api(self, subdir):
        db = FrontendDatabase(
            "sqlite://:memory:", f"local://{self.tmpdir.name}/{subdir}/", exist_ok=True
        )
        with patch("sighthouse.core.utils.api.make_server"):
            config = FrontendConfig("sqlite://:memory:")
            config.worker_url = "redis://localhost:6379/0"
            config.ghidra_dir = "/nonexistent/ghidra"
            db.set_config(config)
            api = FrontendRestAPI(
                db,
                logger=logging.getLogger("test_setup"),
            )
        return db, api._FrontendRestAPI__app.test_client()

    def test_need_setup_false_when_a_user_exists(self):
        resp = self.client.get("/api/v1/setup")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.get_json()["need_setup"])

    def test_setup_rejected_when_already_configured(self):
        resp = self.client.post("/api/v1/setup", json={"user": "x", "password": "y"})
        self.assertEqual(resp.status_code, 400)

    def test_setup_flow_on_empty_db_creates_admin(self):
        db, client = self._fresh_api("fresh")
        self.assertTrue(client.get("/api/v1/setup").get_json()["need_setup"])

        resp = client.post("/api/v1/setup", json={"user": "root", "password": "pw"})
        self.assertEqual(resp.status_code, 200)

        created = db.get_user_by_name("root")
        self.assertIsNotNone(created)
        self.assertEqual(created.role, "admin")

        # Now configured: the flag flips and a second setup is refused.
        self.assertFalse(client.get("/api/v1/setup").get_json()["need_setup"])
        resp = client.post("/api/v1/setup", json={"user": "other", "password": "pw"})
        self.assertEqual(resp.status_code, 400)

    def test_setup_missing_fields(self):
        _db, client = self._fresh_api("fresh2")
        resp = client.post("/api/v1/setup", json={"user": "root"})
        self.assertEqual(resp.status_code, 400)


class TestUserManagement(RestApiTestBase):
    """CRUD behind the admin wall, including the last-admin safety guards."""

    def test_create_user_success(self):
        self.as_admin()
        resp = self.client.post(
            "/api/v1/users", json={"user": "bob", "password": "pw", "role": "user"}
        )
        self.assertEqual(resp.status_code, 201)
        self.assertIsNotNone(self.db.get_user_by_name("bob"))

    def test_create_user_invalid_role(self):
        self.as_admin()
        resp = self.client.post(
            "/api/v1/users",
            json={"user": "bob", "password": "pw", "role": "superuser"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_create_user_missing_password(self):
        self.as_admin()
        resp = self.client.post("/api/v1/users", json={"user": "bob", "role": "user"})
        self.assertEqual(resp.status_code, 400)

    def test_create_duplicate_user(self):
        self.as_admin()
        resp = self.client.post(
            "/api/v1/users",
            json={"user": self.user.name, "password": "pw", "role": "user"},
        )
        self.assertEqual(resp.status_code, 500)

    def test_delete_last_admin_is_blocked(self):
        self.as_admin()  # self.user is the only admin
        resp = self.client.delete("/api/v1/users", json={"user": self.user.name})
        self.assertEqual(resp.status_code, 400)
        self.assertIsNotNone(self.db.get_user_by_name(self.user.name))

    def test_delete_unknown_user_is_idempotent(self):
        self.as_admin()
        resp = self.client.delete("/api/v1/users", json={"user": "ghost"})
        self.assertEqual(resp.status_code, 200)

    def test_delete_ordinary_user(self):
        self.as_admin()
        self.add_db_user("bob", role="user")
        resp = self.client.delete("/api/v1/users", json={"user": "bob"})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(self.db.get_user_by_name("bob"))

    def test_update_resets_password(self):
        self.as_admin()
        self.add_db_user("bob", password="old", role="user")
        old_hash = self.db.get_user_by_name("bob").hash
        resp = self.client.put("/api/v1/users", json={"user": "bob", "password": "new"})
        self.assertEqual(resp.status_code, 200)
        updated = self.db.get_user_by_name("bob")
        self.assertNotEqual(updated.hash, old_hash)
        self.assertTrue(check_password_hash(updated.hash, "new"))

    def test_update_changes_role(self):
        self.as_admin()
        self.add_db_user("bob", role="user")
        resp = self.client.put("/api/v1/users", json={"user": "bob", "role": "admin"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.db.get_user_by_name("bob").role, "admin")

    def test_update_demote_last_admin_is_blocked(self):
        self.as_admin()  # self.user is the only admin
        resp = self.client.put(
            "/api/v1/users", json={"user": self.user.name, "role": "user"}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self.db.get_user_by_name(self.user.name).role, "admin")


class TestConfigEndpoint(RestApiTestBase):
    """GET/PUT /api/v1/config: read the running config and edit it (admin-only)."""

    def test_get_returns_config_and_version(self):
        self.as_admin()
        resp = self.client.get("/api/v1/config")
        self.assertEqual(resp.status_code, 200)
        cfg = resp.get_json()["configuration"]
        # Flattened FrontendConfig fields plus the server version.
        self.assertEqual(cfg["database_uri"], "sqlite://:memory:")
        self.assertIn("version", cfg)
        self.assertIn("bsim_config", cfg)
        self.assertIn("fidb_config", cfg)

    def test_put_runtime_field_persists_without_restart(self):
        self.as_admin()
        resp = self.client.put(
            "/api/v1/config", json={"bsim_config": {"similarity": 0.5}}
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        # A runtime-only change never asks for a restart.
        self.assertEqual(body["restart_required"], [])
        self.assertEqual(body["configuration"]["bsim_config"]["similarity"], 0.5)
        # Persisted to the DB, and other BSIM fields are preserved (partial merge).
        stored = self.db.get_config()
        self.assertEqual(stored.bsim_config.similarity, 0.5)
        self.assertEqual(stored.bsim_config.min_instructions, 10)

    def test_put_startup_field_flags_restart(self):
        self.as_admin()
        resp = self.client.put("/api/v1/config", json={"port": 7000})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["restart_required"], ["port"])
        self.assertEqual(self.db.get_config().port, 7000)

    def test_put_database_uri_is_not_client_settable(self):
        self.as_admin()
        resp = self.client.put(
            "/api/v1/config", json={"database_uri": "sqlite://evil.db"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.get_json()["configuration"]["database_uri"], "sqlite://:memory:"
        )
        self.assertEqual(self.db.get_config().database_uri, "sqlite://:memory:")

    def test_put_rejects_invalid_value(self):
        self.as_admin()
        resp = self.client.put(
            "/api/v1/config", json={"bsim_config": {"similarity": 2.0}}
        )
        self.assertEqual(resp.status_code, 400)
        # Nothing was persisted.
        self.assertEqual(self.db.get_config().bsim_config.similarity, 0.7)


class TestRestartEndpoint(RestApiTestBase):
    """POST /api/v1/restart: guarded self-restart (admin-only)."""

    def test_restart_unsupported_without_sighup_handler(self):
        self.as_admin()
        # No launcher installed a SIGHUP handler in the test process.
        with patch(
            "sighthouse.frontend.restapi.signal.getsignal",
            return_value=signal.SIG_DFL,
        ):
            resp = self.client.post("/api/v1/restart", json={"force": "true"})
        self.assertEqual(resp.status_code, 501)

    def test_restart_triggers_when_supported(self):
        self.as_admin()
        # Pretend a restart-capable launcher is present, and stop the trigger
        # thread from ever signalling the real test process.
        with (
            patch(
                "sighthouse.frontend.restapi.signal.getsignal",
                return_value=lambda *a: None,
            ),
            patch("sighthouse.frontend.restapi.threading.Thread") as Thread,
        ):
            resp = self.client.post("/api/v1/restart", json={"force": "true"})
        self.assertEqual(resp.status_code, 200)
        Thread.assert_called_once()


if __name__ == "__main__":
    unittest.main()
