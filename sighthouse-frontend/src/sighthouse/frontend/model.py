"""Model for Frontend objects"""

from typing import Optional
from flask_login import UserMixin

from sighthouse.core.utils import get_hash


class User(UserMixin):
    """Class to represent a user

    @NOTE: The id attribute is the unique identifier in the database but the 'real'
           identifier is the username (which is also unique)
    """

    INVALID_ID = 0

    def __init__(self, id: int, name: str, hash: str):
        self.id = id
        self.name = name
        self.hash = hash

    @staticmethod
    def from_dict(data: dict) -> "User":
        """
        Create a User instance from a dictionary.

        Args:
            data (dict): A dictionary containing the user data.
                          Must include 'id' (int) and 'name' (str).

        Returns:
            User: An instance of the User class.

        Raises:
            ValueError: If any of the required fields are of the wrong type.
        """
        if not isinstance(data, dict):
            raise ValueError("data is not a dict")
        if not isinstance(data.get("id", User.INVALID_ID), int):
            raise ValueError("id must be an integer")
        if not isinstance(data.get("name"), str):
            raise ValueError("name must be a string")
        if not isinstance(data.get("hash"), str):
            raise ValueError("hash must be a string")

        return User(
            id=data.get("id", User.INVALID_ID), name=data["name"], hash=data["hash"]
        )

    def to_dict(self) -> dict:
        """
        Convert the User instance to a dictionary.

        Returns:
            dict: A dictionary representation of the User instance.
        """
        return {"id": self.id, "name": self.name, "hash": self.hash}


class File:
    """Class to represent a user file"""

    INVALID_ID = 0

    def __init__(
        self,
        id: int,
        name: str,
        user: int,
        hash: Optional[str] = None,
        content: bytes | None = None,
    ):
        self.id = id
        self.name = name
        self.user = user
        self.content = content
        self.hash = hash
        if self.hash is None and self.content:
            self.hash = get_hash(self.content)

    @staticmethod
    def from_dict(data: dict) -> "File":
        """
        Create a File instance from a dictionary.

        Args:
            data (dict): A dictionary containing the file data.
                          Must include 'id' (int), 'name' (str),
                          'user' (int), and 'content' (bytes).

        Returns:
            File: An instance of the File class.

        Raises:
            ValueError: If any of the required fields are of the wrong type.
        """
        if not isinstance(data, dict):
            raise ValueError("data is not a dict")
        if not isinstance(data.get("id", File.INVALID_ID), int):
            raise ValueError("id must be an integer")
        if not isinstance(data.get("name"), str):
            raise ValueError("name must be a string")
        if not isinstance(data.get("user"), int):
            raise ValueError("user must be an integer")
        if not isinstance(data.get("hash"), str):
            raise ValueError("hash must be a string")
        # if not isinstance(data.get("content"), bytes):
        #    raise ValueError("hash must be a string")

        return File(
            id=data.get("id", File.INVALID_ID),
            name=data["name"],
            user=data["user"],
            hash=data["hash"],
        )

    def to_dict(self) -> dict:
        """
        Convert the File instance to a dictionary.

        Returns:
            dict: A dictionary representation of the File instance.
        """
        return {"id": self.id, "name": self.name, "user": self.user, "hash": self.hash}


class Program:
    """Class to represent user program"""

    INVALID_ID = 0

    def __init__(self, id: int, name: str, user: int, language: str, file: int):
        self.id = id
        self.name = name
        self.user = user
        self.language = language
        self.file = file

    @staticmethod
    def from_dict(data: dict) -> "Program":
        """
        Create a Program instance from a dictionary.

        Args:
            data (dict): A dictionary containing the program data.
                          Must include 'id' (int), 'name' (str),
                          'user' (int), language (str) and file (int).

        Returns:
            Program: An instance of the Program class.

        Raises:
            ValueError: If any of the required fields are of the wrong type.
        """
        if not isinstance(data, dict):
            raise ValueError("data is not a dict")
        if not isinstance(data.get("id", Program.INVALID_ID), int):
            raise ValueError("id must be an integer")
        if not isinstance(data.get("name"), str):
            raise ValueError("name must be a string")
        if not isinstance(data.get("user"), int):
            raise ValueError("user must be an integer")
        if not isinstance(data.get("language"), str):
            raise ValueError("language must be a string")
        if not isinstance(data.get("file"), int):
            raise ValueError("file must be an integer")

        return Program(
            id=data.get("id", Program.INVALID_ID),
            name=data["name"],
            user=data["user"],
            language=data["language"],
            file=data["file"],
        )

    def to_dict(self) -> dict:
        """
        Convert the Program instance to a dictionary.

        Returns:
            dict: A dictionary representation of the Program instance.
        """
        return {
            "id": self.id,
            "name": self.name,
            "user": self.user,
            "language": self.language,
            "file": self.file,
        }


class Section:
    """Class to represent a program section"""

    INVALID_ID = 0

    def __init__(
        self,
        id: int,
        name: str,
        program: int,
        file_offset: int,
        start: int,
        end: int,
        perms: str,
        kind: str,
    ):
        self.id = id
        self.name = name
        self.program = program
        self.file_offset = file_offset
        self.start = start
        self.end = end
        self.perms = perms
        self.kind = kind

    @staticmethod
    def from_dict(data: dict) -> "Section":
        """
        Create a Section instance from a dictionary.

        Args:
            data (dict): A dictionary containing the section data.
                          Must include 'id' (int), 'name' (str), 'program' (int),
                          'file_offset' (int), 'start' (int), 'end' (int),
                          'perms' (str), and 'kind' (str).

        Returns:
            Section: An instance of the Section class.

        Raises:
            ValueError: If any of the required fields are of the wrong type.
        """
        if not isinstance(data, dict):
            raise ValueError("data is not a dict")
        if not isinstance(data.get("id", Section.INVALID_ID), int):
            raise ValueError("id must be an integer")
        if not isinstance(data.get("name"), str):
            raise ValueError("name must be a string")
        if not isinstance(data.get("program"), int):
            raise ValueError("program must be an integer")
        if not isinstance(data.get("file_offset"), int):
            raise ValueError("file_offset must be an integer")
        if not isinstance(data.get("start"), int):
            raise ValueError("start must be an integer")
        if not isinstance(data.get("end"), int):
            raise ValueError("end must be an integer")
        if not isinstance(data.get("perms"), str):
            raise ValueError("perms must be a string")
        if not isinstance(data.get("kind"), str):
            raise ValueError("kind must be a string")

        return Section(
            id=data.get("id", Section.INVALID_ID),
            name=data["name"],
            program=data["program"],
            file_offset=data["file_offset"],
            start=data["start"],
            end=data["end"],
            perms=data["perms"],
            kind=data["kind"],
        )

    def to_dict(self) -> dict:
        """
        Convert the Section instance to a dictionary.

        Returns:
            dict: A dictionary representation of the Section instance.
        """
        return {
            "id": self.id,
            "name": self.name,
            "program": self.program,
            "file_offset": self.file_offset,
            "start": self.start,
            "end": self.end,
            "perms": self.perms,
            "kind": self.kind,
        }


class Function:
    """Class to represent a section function"""

    INVALID_ID = 0

    def __init__(self, id: int, name: str, offset: int, section: int, details: dict):
        self.id = id
        self.name = name
        self.offset = offset
        self.section = section
        self.details = details

    @staticmethod
    def from_dict(data: dict) -> "Function":
        """
        Create a Function instance from a dictionary.

        Args:
            data (dict): A dictionary containing the function data.
                          Must include 'id' (int), 'name' (str), 'offset' (int),
                          'section' (int) and details (dict).

        Returns:
            Function: An instance of the Function class.

        Raises:
            ValueError: If any of the required fields are of the wrong type.
        """
        if not isinstance(data, dict):
            raise ValueError("data is not a dict")
        if not isinstance(data.get("id", Function.INVALID_ID), int):
            raise ValueError("id must be an integer")
        if not isinstance(data.get("name"), str):
            raise ValueError("name must be a string")
        if not isinstance(data.get("offset"), int):
            raise ValueError("offset must be an integer")
        if not isinstance(data.get("section"), int):
            raise ValueError("section must be an integer")
        if not isinstance(data.get("details", {}), dict):
            raise ValueError("details must be a dict")

        return Function(
            id=data.get("id", Function.INVALID_ID),
            name=data["name"],
            offset=data["offset"],
            section=data["section"],
            details=data.get("details", {}),
        )

    def to_dict(self) -> dict:
        """
        Convert the Function instance to a dictionary.

        Returns:
            dict: A dictionary representation of the Function instance.
        """
        return {
            "id": self.id,
            "name": self.name,
            "offset": self.offset,
            "section": self.section,
            "details": self.details,
        }


class Match:
    """Class to represent a function match"""

    INVALID_ID = 0

    def __init__(self, id: int, name: str, function: int, metadata: dict):
        self.id = id
        self.name = name
        self.function = function
        self.metadata = metadata

    @staticmethod
    def from_dict(data: dict) -> "Match":
        """
        Create a Match instance from a dictionary.

        Args:
            data (dict): A dictionary containing the match data.
                          Must include 'id' (int), 'name' (str),
                          'function' (int), and 'metadata' (dict).

        Returns:
            Match: An instance of the Match class.

        Raises:
            ValueError: If any of the required fields are of the wrong type.
        """
        if not isinstance(data, dict):
            raise ValueError("data is not a dict")
        if not isinstance(data.get("id", Match.INVALID_ID), int):
            raise ValueError("id must be an integer")
        if not isinstance(data.get("name"), str):
            raise ValueError("name must be a string")
        if not isinstance(data.get("function"), int):
            raise ValueError("function must be an integer")
        if not isinstance(data.get("metadata"), dict):
            raise ValueError("metadata must be a dictionary")

        return Match(
            id=data.get("id", Match.INVALID_ID),
            name=data["name"],
            function=data["function"],
            metadata=data["metadata"],
        )

    def to_dict(self) -> dict:
        """
        Convert the Match instance to a dictionary.

        Returns:
            dict: A dictionary representation of the Match instance.
        """
        return {
            "id": self.id,
            "name": self.name,
            "function": self.function,
            "metadata": self.metadata,
        }


class Analysis:
    """Class that represent a running analysis

    @NOTE: This class contains the program and user which is redondant as program already holds
           the user identifier, however it allow to quickly check if an analysis is running for
           a given user and a given program without having to query the database.

           If we did not had the user identifier in the analysis, it could allow another user
           to check if an analysis is running for any given program, including programs that he
           does not own.
    """

    def __init__(self, program: int, user: int, info: dict):
        self.program = program
        self.user = user
        self.info = info

    @staticmethod
    def from_dict(data: dict) -> "Analysis":
        """
        Create an Analysis instance from a dictionary.

        Args:
            data (dict): A dictionary containing the analysis data.
                          Must include 'program' (int), user (int)
                          and 'info' (dict).

        Returns:
            Match: An instance of the Analysis class.

        Raises:
            ValueError: If any of the required fields are of the wrong type.
        """
        if not isinstance(data, dict):
            raise ValueError("data is not a dict")
        if not isinstance(data.get("program"), int):
            raise ValueError("program must be an integer")
        if not isinstance(data.get("user"), int):
            raise ValueError("user must be an int")
        if not isinstance(data.get("info"), dict):
            raise ValueError("info must be a dictionary")

        return Analysis(
            program=data["program"],
            user=data["user"],
            info=data["info"],
        )

    def to_dict(self) -> dict:
        """
        Convert the Analysis instance to a dictionary.

        Returns:
            dict: A dictionary representation of the Analysis instance.
        """
        return {
            "program": self.program,
            "user": self.user,
            "info": self.info,
        }
