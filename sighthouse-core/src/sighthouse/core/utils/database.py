"""Generic abstraction layer for databases"""

from typing import Any, Optional, Dict, Tuple, List
from contextlib import contextmanager
from logging import Logger
from threading import Lock
from pathlib import Path

from sighthouse.core.utils import parse_uri  # type: ignore[import-untyped]


class Database:
    """
    A class to manage connections and operations for various database types,
    including SQLite, PostgreSQL, and MySQL.
    """

    def __init__(self, uri: str, exist_ok: bool = False):
        """
        Initialize a Database object with URI and Logger, optionally creating new DB.

        Args:
            uri (str): The URI string used to parse connection parameters.
            exist_ok (bool): If True, allows the creation of new databases.
                             Defaults to False.
        """
        self._lock: Lock = Lock()

        self._uri: str = uri
        self._type: Optional[str] = None
        self._db: Any = None
        self.connect(exist_ok)

    @contextmanager
    def __get_cursor(self):
        """
        A context manager that returns a cursor for database operations.

        Yields:
            Cursor object for executing SQL commands.
        """
        cur = self._db.cursor()
        try:
            yield cur
        finally:
            cur.close()

    def connect(self, exist_ok: bool = True) -> None:
        """
        Establish a connection to the database using parameters parsed from the URI.

        Args:
            exist_ok (bool): If True, allows the creation of new databases.
                             Defaults to True.
        """
        params: Dict[str, Any] = parse_uri(self._uri)
        self._type = params["type"]

        if self._type == "sqlite":
            import sqlite3

            if params["database"] != ":memory:":
                database = Path(params["database"])
                # Refuse to open a non existing database
                if not exist_ok and not database.exists():
                    raise FileNotFoundError(
                        f"Invalid database path: '{params.get('database')}'. Database should exists"
                    )

                # Create parent directory if needed
                database.parent.mkdir(parents=True, exist_ok=True)

            self._db = sqlite3.connect(params["database"], check_same_thread=False)
        elif self._type in ["postgres", "postgresql"]:
            import psycopg

            conn_details = dict(params)
            del conn_details["type"]
            self._db = psycopg.connect(**conn_details)
        elif self._type == "mysql":
            import mysql.connector  # type: ignore[import-not-found]

            self._db = mysql.connector.connect(**params)
        else:
            raise ValueError(f"Unsupported URI scheme: {self._type}")

    def _adapt_query(self, query: str) -> str:
        """
        Convert '?' placeholders in queries to '%s' for PostgreSQL databases.

        Args:
            query (str): The SQL query with potential '?' placeholders.

        Returns:
            str: Modified query string.
        """
        if self._type in ["postgres", "postgresql"]:
            return query.replace("?", "%s")
        return query  # SQLite uses ? natively

    def execute(self, query: str, params: Optional[Tuple] = None) -> Optional[int]:
        """
        Execute an SQL query with optional parameters. This method is Thread safe.

        Args:
            query: The SQL command to execute.
            params: Optional parameters for the query execution.

        Returns:
            Optional[int]: An optional integer corresponding to the ID of the inserted row.
        """
        if self._type == "sqlite":
            with self._lock:
                return self.__unsafe_execute(query, params=params)
        else:
            return self.__unsafe_execute(query, params=params)

    def __unsafe_execute(
        self, query: str, params: Optional[Tuple] = None
    ) -> Optional[int]:
        """
        Execute the given query and commit changes. Used internally without locking.

        Args:
            query: The SQL command to execute.
            params: Optional parameters for the query execution.

        Returns:
            Optional[int]: An optional integer corresponding to the ID of the inserted row.
        """
        adapted_query = self._adapt_query(query)
        with self.__get_cursor() as cursor:
            try:
                if self._type in ["postgres", "postgresql"]:
                    # Use RETURNING for PostgreSQL to get inserted ID
                    if adapted_query.strip().upper().startswith("INSERT"):
                        adapted_query = adapted_query.rstrip(";") + " RETURNING id;"
                    cursor.execute(adapted_query, params)
                    self._db.commit()
                    try:
                        return cursor.fetchone()[0] if cursor.rowcount > 0 else None
                    except Exception:
                        return None
                else:
                    if params:
                        cursor.execute(adapted_query, params)
                    else:
                        cursor.execute(adapted_query)
                    self._db.commit()
                    return (
                        cursor.lastrowid
                        if hasattr(cursor, "lastrowid") and cursor.rowcount > 0
                        else None
                    )
            except Exception as e:
                self._db.rollback()
                raise e

    def fetch(
        self, request: str, parameters: Tuple = (), mode: str = "all"
    ) -> List[Tuple]:
        """
        Fetch results from a query, with support for fetching all, one, or many rows.
        This method is Thread safe.

        Args:
            request (str): The SQL query to execute.
            parameters (tuple): Optional parameters for the query execution.
                                Defaults to an empty tuple.
            mode (str): Mode of fetching: 'all', 'one', or 'many'. Defaults to 'all'.

        Returns:
            list[tuple]: Result set from the executed query.
        """
        if self._type == "sqlite":
            with self._lock:
                return self.__unsafe_fetch(request, parameters=parameters, mode=mode)

        return self.__unsafe_fetch(request, parameters=parameters, mode=mode)

    def __unsafe_fetch(
        self, request: str, parameters: Tuple = (), mode: str = "all"
    ) -> List[Tuple]:
        """
        Fetch results without locking. Used internally for all databases.

        Args:
            request (str): The SQL query to execute.
            parameters (tuple): Optional parameters for the query execution.
                                Defaults to an empty tuple.
            mode (str): Mode of fetching: 'all', 'one', or 'many'. Defaults to 'all'.

        Returns:
            list[tuple]: Result set from the executed query.
        """
        with self.__get_cursor() as cursor:
            cursor.execute(self._adapt_query(request), parameters)
            match mode:
                case "all":
                    return cursor.fetchall()
                case "one":
                    return cursor.fetchone()
                case "many":
                    return cursor.fetchmany()
                case _:
                    raise ValueError("fetch mode must be 'all', 'one', or 'many'")

    def __repr__(self) -> str:
        """
        Return a string representation of the Database object.

        Returns:
            str: Representation of the instance.
        """
        return f'<{self.__class__.__name__}(uri="{self._uri}", connected={self._db is not None})>'

    def close(self) -> None:
        """
        Close the database connection safely. This method is Thread safe.
        """
        if self._type == "sqlite":
            with self._lock:
                self.__unsafe_close()
        else:
            self.__unsafe_close()

    def __unsafe_close(self) -> None:
        """
        Close the internal database connection. Used internally without locks.
        """
        if self._db:
            self._db.close()
