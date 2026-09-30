"""Tests for the frontend configuration objects and their persistence."""

from tempfile import TemporaryDirectory
import json
import unittest

from sighthouse.frontend.database import FrontendDatabase
from sighthouse.frontend.model import BSimConfig, FidbConfig, FrontendConfig


class TestBSimConfig(unittest.TestCase):
    def test_defaults(self):
        c = BSimConfig()
        self.assertEqual(c.urls, [])
        self.assertEqual(c.min_instructions, 10)
        self.assertEqual(c.max_instructions, 0)
        self.assertEqual(c.number_of_matches, 10)
        self.assertEqual(c.similarity, 0.7)
        self.assertEqual(c.confidence, 1.0)

    def test_round_trip(self):
        c = BSimConfig(
            urls=["postgres://host:5432/db"],
            min_instructions=5,
            max_instructions=100,
            number_of_matches=3,
            similarity=0.9,
            confidence=2.0,
        )
        self.assertEqual(BSimConfig.from_dict(c.to_dict()).to_dict(), c.to_dict())

    def test_validate_rejects_out_of_range(self):
        with self.assertRaises(ValueError):
            BSimConfig.from_dict({"similarity": 1.5})
        with self.assertRaises(ValueError):
            BSimConfig.from_dict({"confidence": -1.0})
        with self.assertRaises(ValueError):
            BSimConfig.from_dict({"number_of_matches": -1})
        with self.assertRaises(ValueError):
            # max_instructions (non-zero) below min_instructions
            BSimConfig.from_dict({"min_instructions": 10, "max_instructions": 5})

    def test_validate_rejects_bad_url(self):
        with self.assertRaises(ValueError):
            BSimConfig.from_dict({"urls": ["not-a-uri"]})

    def test_from_dict_type_errors(self):
        with self.assertRaises(ValueError):
            BSimConfig.from_dict({"urls": "postgres://x"})  # not a list
        with self.assertRaises(ValueError):
            BSimConfig.from_dict({"min_instructions": "10"})  # not an int


class TestFidbConfig(unittest.TestCase):
    def test_defaults(self):
        c = FidbConfig()
        self.assertEqual(c.urls, [])
        # FIDB keeps a lower default than BSIM
        self.assertEqual(c.min_instructions, 2)
        self.assertEqual(c.max_instructions, 0)

    def test_round_trip(self):
        c = FidbConfig(urls=["local://fidb"], min_instructions=7, max_instructions=50)
        self.assertEqual(FidbConfig.from_dict(c.to_dict()).to_dict(), c.to_dict())

    def test_validate_rejects_out_of_range(self):
        with self.assertRaises(ValueError):
            FidbConfig.from_dict({"min_instructions": 10, "max_instructions": 5})


class TestFrontendConfig(unittest.TestCase):
    def test_defaults(self):
        c = FrontendConfig("sqlite://frontend.db")
        self.assertEqual(c.database_uri, "sqlite://frontend.db")
        self.assertEqual(c.repo_url, "local://data")
        self.assertEqual(c.worker_url, "redis://localhost:6379/0")
        self.assertEqual(c.host, "0.0.0.0")
        self.assertEqual(c.port, 6671)
        self.assertEqual(c.worker_count, 1)
        self.assertIsNone(c.ghidra_dir)
        self.assertIsInstance(c.bsim_config, BSimConfig)
        self.assertIsInstance(c.fidb_config, FidbConfig)
        # The default config must be valid.
        c.validate()

    def test_round_trip_with_none_ghidra_dir(self):
        # ghidra_dir stays None in the dict; from_dict must tolerate the explicit
        # null instead of rejecting it.
        c = FrontendConfig("sqlite://frontend.db")
        data = c.to_dict()
        self.assertIsNone(data["ghidra_dir"])
        self.assertEqual(FrontendConfig.from_dict(data).to_dict(), data)

    def test_round_trip_full(self):
        c = FrontendConfig(
            database_uri="sqlite://frontend.db",
            repo_url="local://uploads",
            host="127.0.0.1",
            port=7000,
            worker_url="redis://localhost:6379/1",
            worker_count=4,
            bsim_config=BSimConfig(urls=["postgres://h:5432/b"], similarity=0.9),
            fidb_config=FidbConfig(urls=["local://fidb"], min_instructions=7),
        )
        self.assertEqual(FrontendConfig.from_dict(c.to_dict()).to_dict(), c.to_dict())

    def test_from_dict_tolerates_missing_and_null_optionals(self):
        c = FrontendConfig.from_dict(
            {"database_uri": "sqlite://frontend.db", "repo_url": None}
        )
        # None / missing optionals fall back to the built-in defaults.
        self.assertEqual(c.repo_url, "local://data")
        self.assertEqual(c.worker_url, "redis://localhost:6379/0")

    def test_from_dict_requires_database_uri(self):
        with self.assertRaises(ValueError):
            FrontendConfig.from_dict({})

    def test_from_dict_type_errors(self):
        with self.assertRaises(ValueError):
            FrontendConfig.from_dict({"database_uri": "sqlite://x", "port": "7000"})
        with self.assertRaises(ValueError):
            FrontendConfig.from_dict({"database_uri": "sqlite://x", "repo_url": 123})

    def test_validate_rejects_out_of_range(self):
        with self.assertRaises(ValueError):
            FrontendConfig.from_dict({"database_uri": "sqlite://x", "port": 80})
        with self.assertRaises(ValueError):
            FrontendConfig.from_dict({"database_uri": "sqlite://x", "worker_count": -1})

    def test_validate_rejects_bad_database_uri(self):
        with self.assertRaises(ValueError):
            FrontendConfig("not-a-uri").validate()

    def test_restart_required_detects_startup_field_changes(self):
        base = FrontendConfig("sqlite://frontend.db", port=6671)
        # A startup-tier change is reported.
        changed = FrontendConfig("sqlite://frontend.db", port=7000)
        self.assertEqual(changed.restart_required(base), ["port"])
        # A runtime-only change (BSIM similarity) needs no restart.
        runtime = FrontendConfig("sqlite://frontend.db")
        runtime.bsim_config.similarity = 0.1
        self.assertEqual(
            runtime.restart_required(FrontendConfig("sqlite://frontend.db")), []
        )


class TestFrontendDatabaseConfig(unittest.TestCase):
    def setUp(self):
        self.tmpdir = TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.db = FrontendDatabase(
            "sqlite://:memory:", f"local://{self.tmpdir.name}/", exist_ok=True
        )

    def test_get_config_returns_default_when_empty(self):
        c = self.db.get_config()
        self.assertIsInstance(c, FrontendConfig)
        # database_uri reflects the live connection.
        self.assertEqual(c.database_uri, "sqlite://:memory:")
        self.assertEqual(c.repo_url, "local://data")

    def test_set_then_get_round_trip(self):
        stored = FrontendConfig(
            database_uri="sqlite://:memory:",
            host="127.0.0.1",
            port=7000,
            worker_count=2,
            bsim_config=BSimConfig(similarity=0.9, number_of_matches=5),
            fidb_config=FidbConfig(min_instructions=7),
        )
        self.db.set_config(stored)
        loaded = self.db.get_config()
        self.assertEqual(loaded.to_dict(), stored.to_dict())

    def test_database_uri_is_not_persisted(self):
        self.db.set_config(FrontendConfig("sqlite://:memory:", port=7000))
        raw = self.db._get_config_item("frontend.config")
        self.assertIsNotNone(raw)
        self.assertNotIn("database_uri", json.loads(raw))
        # ...but it is re-injected from the live connection on read.
        self.assertEqual(self.db.get_config().database_uri, "sqlite://:memory:")


if __name__ == "__main__":
    unittest.main()
