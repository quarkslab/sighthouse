import unittest
import sqlite3
from sighthouse.core.utils.database import Database


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.logger = None

    def create_database(self):
        # Helper method to create a new Database instance
        database_uri = "sqlite://:memory:"  # In-memory SQLite database
        db = Database(database_uri, self.logger)  # type: ignore[arg-type]
        return db

    def test_connect_create_new_db(self):
        # Test connection for creating a new database
        db = self.create_database()
        db.connect(exist_ok=True)
        self.assertIsNotNone(db)

        # Clean up
        db.close()

    def test_connect_existing_db(self):
        # Test connecting to an existing database
        db = self.create_database()
        db.connect(exist_ok=False)
        self.assertIsNotNone(db)

        # Clean up
        db.close()

    def test_execute(self):
        # Create a table and insert sample data
        db = self.create_database()
        db.connect()
        create_table_query = "CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)"
        db.execute(create_table_query)

        insert_query = "INSERT INTO test (name) VALUES (?)"
        db.execute(insert_query, ("Alice",))

        # Retrieve data to check insertion
        result = db.fetch("SELECT * FROM test")
        self.assertEqual(result, [(1, "Alice")])

        # Clean up
        db.close()

    def test_fetch_all(self):
        # Create a table and add multiple entries
        db = self.create_database()
        db.connect()
        create_table_query = "CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)"
        db.execute(create_table_query)

        insert_query = "INSERT INTO test (name) VALUES (?)"
        db.execute(insert_query, ("Alice",))
        db.execute(insert_query, ("Bob",))

        result = db.fetch("SELECT * FROM test")
        self.assertEqual(result, [(1, "Alice"), (2, "Bob")])

        # Clean up
        db.close()

    def test_fetch_one(self):
        # Create a table and add sample entry
        db = self.create_database()
        db.connect()
        create_table_query = "CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)"
        db.execute(create_table_query)

        insert_query = "INSERT INTO test (name) VALUES (?)"
        db.execute(insert_query, ("Alice",))

        result = db.fetch("SELECT * FROM test", mode="one")
        self.assertEqual(result, (1, "Alice"))

        # Clean up
        db.close()

    def test_close_connection(self):
        db = self.create_database()
        db.connect()
        db.close()
        # Attempting to fetch data after closing the database should raise an error
        with self.assertRaises(sqlite3.ProgrammingError):
            db.fetch("SELECT * FROM test")


if __name__ == "__main__":
    unittest.main()
