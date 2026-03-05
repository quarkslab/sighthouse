from typing import Dict, Optional, Any
import json

from sighthouse.core.utils.database import Database


class LazyEntry(object):
    """Dedicated type to check whevether or not an entry is loaded"""


class Package(object):

    def __init__(
        self,
        name: str,
        version: str,
        hash: str,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        submitted: bool = False,
    ):
        self.name = name
        self.version = version
        self.hash = hash
        self.url = url
        self.submitted = submitted
        self.data = data or {}

    def __repr__(self) -> str:
        return '{}(name="{}", version="{}", hash="{}", "url="{}", submitted={})'.format(
            self.__class__.__name__,
            self.name,
            self.version,
            self.hash,
            self.url,
            self.submitted,
        )


class PackageDatabase(Database):

    def __init__(self, database_url: str):
        super().__init__(database_url, exist_ok=True)

        # Create tables if they do not exists
        self._init_database()

        self._packages = {}
        # Cache method
        for row in self.fetch("SELECT hash FROM package;"):
            self._packages.update({row[0]: LazyEntry()})

    def _init_database(self):
        """Initialize database (create table if they don't exists)"""

        # Create package table if it does not already exists
        self.execute(
            "CREATE TABLE IF NOT EXISTS package ("
            "  hash VARCHAR NOT NULL,"
            "  name VARCHAR,"
            "  version VARCHAR,"
            "  url VARCHAR,"
            "  submitted INTEGER,"  # SQLite does not have a separate Boolean storage class.
            "  data VARCHAR,"  # Instead, Boolean values are stored as integers
            "  PRIMARY KEY (hash)"
            ");"
        )

    def get_package_count(self):
        """Return the number of package (avoid loading all package entry)"""
        return len(self._packages)

    def add_package(self, package: Package) -> None:
        """Add a new package to the database"""
        self.execute(
            "INSERT INTO package ("
            " hash, name, version, url, submitted, data"
            ") VALUES(?, ?, ?, ?, ?, ?);",
            (
                package.hash,
                package.name,
                package.version,
                package.url,
                1 if package.submitted else 0,
                json.dumps(package.data),
            ),
        )
        self._packages.update({package.hash: package})

    def get_package(self, hash: str) -> Package:
        """Return the corresponding package if exists"""
        package = self._packages.get(hash)
        if isinstance(package, LazyEntry):
            # Retrieve back information from the database
            for row in self.fetch(
                "SELECT name, version, hash, url, submitted, data FROM package WHERE hash = ?;",
                (hash,),
            ):
                # Add package to objects
                package = Package(
                    name=row[0],
                    version=row[1],
                    hash=row[2],
                    url=row[3],
                    submitted=bool(row[4]),
                    data=json.loads(row[5]),
                )

                self._packages.update({hash: package})

        return package

    def update_package(self, package: Package) -> bool:
        """Update a package from the database"""
        self.execute(
            "UPDATE package SET name = ?, version = ?, url = ?, submitted = ?, data = ? WHERE hash = ?;",
            (
                package.name,
                package.version,
                package.url,
                int(package.submitted),
                json.dumps(package.data),
                package.hash,
            ),
        )
        self._db.commit()
        self._packages.update({package.hash: package})
        return True

    def get_packages(self) -> list[Package]:
        """Return the list of packages"""
        return [self.get_package(hash) for hash in self._packages]

    def commit(self):
        """Commit changes made to database"""
        self._db.commit()

    def close(self):
        """Close database connection"""
        self._db.close()
