"""Database to store/retireve Frontend objects"""

from typing import Optional, List, Dict, Union
from threading import Lock
from pathlib import Path
import json

from sighthouse.core.utils.database import Database
from sighthouse.core.utils.repo import Repo
from .model import User, File, Program, Section, Function, Match, Analysis


class RestError(ValueError):
    """Custom exception that extends ValueError."""

    def __init__(self, message, code: Optional[int] = None):
        super().__init__(message)
        self.code = code
        self.error = message


class FrontendDatabase(Database):
    """Frontend database used to store/retireve objects"""

    USER_UPLOAD_DIR = "/uploads"
    USER_LOGS_DIR = "/logs"

    def __init__(self, uri: str, repo: str, exist_ok: bool = False):
        super().__init__(uri, exist_ok=exist_ok)

        self.repo = Repo(repo, exist_ok=exist_ok, secure=False)

        # Create tables if they do not exists
        self._init_database()
        self._analysis_lock = Lock()
        self._running_analysis: Dict[int, Analysis] = {}

    def __repr__(self):
        return (
            f"<FrontendDatabase(uri={self._uri}, repo={self.repo} "
            f"connected={self._db is not None})>"
        )

    ## Repo stuff

    def get_username(self, user: User | int) -> str:
        """Create user directory to store files with root as parent"""
        if isinstance(user, int):
            db_user = self.get_user(user)
            if db_user is None:
                raise Exception(f"Fail to retrieve user from database (user_id: {user}")

        else:
            db_user = user

        if not isinstance(db_user, User):
            raise TypeError(
                f"Invalid type for user. Expecting 'User' but got {type(db_user)}"
            )

        return db_user.name

    def get_upload_dir(self, user: User | int) -> str:
        """Return the upload directory of the given user

        Args:
            user (User | int): The given user or user_id

        Returns:
            str: The path to the user uploads directory
        """
        return self.get_username(user) + "/" + self.USER_UPLOAD_DIR + "/"

    def __push_file(self, file: File) -> bool:
        if file.hash is None or file.content is None:
            return False

        upload_path = self.get_upload_dir(file.user) + file.hash
        return self.repo.push_file(upload_path, file.content)

    def __delete_file(self, file: File) -> None:
        if file.hash is not None:
            upload_path = self.get_upload_dir(file.user) + file.hash
            self.repo.delete_file(upload_path)

    def get_file(self, file: File) -> Optional[bytes]:
        """Return the content associated with a given file object

        Args:
            file (File): The file object to retrieve content from

        Returns:
            Optional[bytes]: The file content on success, None otherwise
        """
        if file.hash is None:
            return None

        upload_path = self.get_upload_dir(file.user) + file.hash
        return self.repo.get_file(upload_path)

    def get_sharefile(self, file: File) -> Union[Path, str]:
        """Return the path to the given file object

        Args:
           file (File): The file object to retrieve content from

        Returns:
            Path | str: A path-like object corresponding to the file location
        """
        if file.hash is None:
            return ""

        upload_path = self.get_upload_dir(file.user) + file.hash
        return self.repo.get_sharefile(upload_path)

    ## DB stuff

    def _init_database(self):
        """Initialize database (create table if they don't exists)"""

        if self._type == "sqlite":
            # Enable foreign key support
            self.execute("PRAGMA foreign_keys = ON;")
            auto_increment = "INTEGER"
        elif self._type in ["postgres", "postgresql"]:
            auto_increment = "SERIAL"
        else:
            auto_increment = "INTEGER"

        self.execute(f"""
            CREATE TABLE IF NOT EXISTS Users (
                id {auto_increment} PRIMARY KEY,
                name TEXT NOT NULL,
                hash TEXT NOT NULL
            );
            """)

        self.execute(f"""
            CREATE TABLE IF NOT EXISTS File (
                id {auto_increment} PRIMARY KEY,
                name TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                hash TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES Users(id) ON DELETE CASCADE
            );
            """)

        self.execute(f"""
        CREATE TABLE IF NOT EXISTS Program (
            id {auto_increment} PRIMARY KEY,
            name TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            language TEXT NOT NULL,
            file INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES Users(id) ON DELETE CASCADE
        );
        """)

        self.execute(f"""
        CREATE TABLE IF NOT EXISTS Section (
            id {auto_increment} PRIMARY KEY,
            name TEXT NOT NULL,
            program INTEGER,
            file_offset INTEGER NOT NULL,
            start INTEGER NOT NULL,
            "end" INTEGER NOT NULL,
            perms TEXT NOT NULL,
            kind TEXT NOT NULL,
            FOREIGN KEY (program) REFERENCES Program(id) ON DELETE CASCADE
        );
        """)

        self.execute(f"""
        CREATE TABLE IF NOT EXISTS Function (
            id {auto_increment} PRIMARY KEY,
            name TEXT NOT NULL,
            "offset" INTEGER NOT NULL,
            section INTEGER NOT NULL,
            details TEXT NOT NULL,
            FOREIGN KEY (section) REFERENCES Section(id) ON DELETE CASCADE
        );
        """)

        # Storing metadata as JSON text
        self.execute(f"""
        CREATE TABLE IF NOT EXISTS Match (
            id {auto_increment} PRIMARY KEY,
            name TEXT NOT NULL,
            function INTEGER,
            metadata TEXT NOT NULL,
            FOREIGN KEY (function) REFERENCES Function(id) ON DELETE CASCADE
        );
        """)

    def add_user(self, user: User) -> Optional[User]:
        """Add a new user to the database.

        Args:
            user (User): An instance of the User class containing user details.

        Returns:
            Optional[User]: The updated user instance if added or None if an error occured.

        Raises:
            TypeError: If the provided argument is not an instance of User.
        """
        if not isinstance(user, User):
            raise TypeError(
                f"Invalid type for user. Expecting 'User' but got {type(user)}"
            )

        # Unsure there is no other user with already the same name
        rows = self.fetch("SELECT name FROM Users WHERE name = ?;", (user.name,))
        if len(rows) > 0:
            return None

        user_id = self.execute(
            "INSERT INTO Users (name, hash) VALUES (?, ?);", (user.name, user.hash)
        )
        if user_id is None:
            return None

        user.id = user_id
        return user

    def get_user(self, user_id: int) -> Optional[User]:
        """Retrieve a user from the database by ID.

        Args:
            user_id (int): The ID of the user to retrieve.

        Returns:
            Optional[User]: An instance of the User class with the retrieved user details,
                            or None if not found.
        """
        rows = self.fetch("SELECT id, name, hash FROM Users WHERE id = ?;", (user_id,))
        if len(rows) == 1:
            return User(
                id=rows[0][0], name=rows[0][1], hash=rows[0][2]  # id  # name  # hash
            )

        return None

    def get_user_by_name(self, name: str) -> Optional[User]:
        """Retrieve a user from the database by name.

        Args:
            name (str): The name of the user to retrieve.

        Returns:
            Optional[User]: An instance of the User class with the retrieved user details,
                            or None if not found.
        """
        rows = self.fetch("SELECT id, name, hash FROM Users WHERE name = ?;", (name,))
        if len(rows) == 1:
            return User(
                id=rows[0][0], name=rows[0][1], hash=rows[0][2]  # id  # name  # hash
            )

        return None

    def update_user(self, user: User) -> bool:
        """
        Updates the details of a user in the database.
        Args:
            user (User): The User object containing the updated information.
                         It must have 'name', 'hash', and 'id' attributes.

        Returns:
            bool: True if the update was successful.

        Raises:
            TypeError: If the provided user is not an instance of the User class.
        """
        if not isinstance(user, User):
            raise TypeError(
                f"Invalid type for user. Expecting 'User' but got {type(user)}"
            )

        self.execute(
            "UPDATE Users SET name = ?, hash = ? WHERE id = ?;",
            (user.name, user.hash, user.id),
        )
        return True

    def list_users(self) -> list[User]:
        """
        Retrieves a list of all users from the database.

        Returns:
            list[User]: A list of User objects.
        """
        users = []
        rows = self.fetch("SELECT id, name, hash FROM Users;")
        for row in rows:
            users.append(
                User(id=row[0], name=row[1], hash=row[2])  # id  # name  # hash
            )

        return users

    def delete_user(self, user: User) -> bool:
        """Delete a user from the database by their unique identifier.

        Args:
            user_id (int): The unique identifier of the user to be deleted.

        Returns:
            bool: True if the user was successfully deleted, False otherwise.

        Raises:
            TypeError: If the provided argument is not an instance of User.
        """
        if not isinstance(user, User):
            raise TypeError(
                f"Invalid type for user. Expecting 'User' but got {type(user)}"
            )

        self.execute("DELETE FROM Users WHERE id = ?;", (user.id,))
        return True

    def add_file_user(self, file: File) -> File:
        """Add a new file to the database.

        Args:
            file (File): An instance of the File class containing file details.

        Returns:
            File: The updated file instance if added or None if an error occurred.

        Raises:
            TypeError: If the provided argument is not an instance of File.
            RestError: If the provided file already exists
        """

        existing_file = self.get_file_by_hash(file.hash, user_id=file.user)
        if existing_file:
            raise RestError(
                {
                    "error": f"File '{existing_file.name}' with hash '{existing_file.hash}' "
                    "already exists",
                    "file": existing_file.id,
                },
                code=409,
            )

        if not isinstance(file, File):
            raise TypeError(
                f"Invalid type for file. Expecting 'File' but got {type(file)}"
            )

        # Ensure there is no other file with the same hash for the same user
        rows = self.fetch(
            "SELECT name FROM File WHERE hash = ? AND user_id = ?;",
            (file.hash, file.user),
        )
        if len(rows) > 0:
            raise RestError(
                {
                    "error": f"File '{file.name}' with hash '{file.hash}' already exists",
                    "file": file.id,
                },
                code=409,
            )

        file_id = self.execute(
            "INSERT INTO File (name, user_id, hash) VALUES (?, ?, ?);",
            (file.name, file.user, file.hash),
        )
        if file_id is None:
            raise RestError(
                {
                    "error": "Internal server error",
                },
                code=500,
            )

        file.id = file_id
        if self.__push_file(file):
            return file

        # @TODO: remove from SQL if failed to push file
        raise RestError(
            {
                "error": "Internal server error",
            },
            code=500,
        )

    def get_file_user(
        self, file_id: int, user_id: Optional[int] = None
    ) -> Optional[File]:
        """Retrieve a file from the database by ID.

        Args:
            file_id (int): The ID of the file to retrieve.
            user_id (Optional[int]): The ID of the user owning the file

        Returns:
            Optional[File]: An instance of the File class with the retrieved file details,
                            or None if not found.
        """
        if isinstance(user_id, int):
            rows = self.fetch(
                "SELECT id, name, user_id, hash FROM File WHERE id = ? and user_id = ?;",
                (file_id, user_id),
            )
        else:
            rows = self.fetch(
                "SELECT id, name, user_id, hash FROM File WHERE id = ?;", (file_id,)
            )
        if len(rows) == 1:
            return File(
                id=rows[0][0],  # id
                name=rows[0][1],  # name
                user=rows[0][2],  # user
                hash=rows[0][3],  # hash
            )

        return None

    def get_file_by_hash(
        self, file_hash: Optional[str] = None, user_id: Optional[int] = None
    ) -> Optional[File]:
        """Retrieve a file from the database by its hash.

        Args:
            file_hash (str): The hash of the file to retrieve.

        Returns:
            Optional[File]: An instance of the File class with the retrieved file details,
                            or None if not found.
        """
        if not isinstance(file_hash, str):
            raise TypeError(
                f"Invalid type for file_hash. Expecting 'str' but got {type(file_hash)}"
            )

        if isinstance(user_id, int):
            rows = self.fetch(
                "SELECT id, name, user_id, hash FROM File WHERE hash = ? and user_id = ?;",
                (file_hash, user_id),
            )
        else:
            rows = self.fetch(
                "SELECT id, name, user_id, hash FROM File WHERE hash = ?;", (file_hash,)
            )

        if len(rows) == 1:
            return File(
                id=rows[0][0],  # id
                name=rows[0][1],  # name
                user=rows[0][2],  # user
                hash=rows[0][3],  # hash
            )

        return None

    def get_user_file(self, user_id: int) -> List[File]:
        """Retrieve all files associated with a specific user by user ID.

        Args:
            user_id (int): The ID of the user for which to retrieve files.

        Returns:
            List[File]: A list of File instances associated with the user.
        """
        if not isinstance(user_id, int):
            raise TypeError(
                f"Invalid type for user_id. Expecting 'int' but got {type(user_id)}"
            )

        rows = self.fetch(
            "SELECT id, name, user_id, hash FROM File WHERE user_id = ?;", (user_id,)
        )
        files = []

        for row in rows:
            files.append(
                File(
                    id=row[0],  # id
                    name=row[1],  # name
                    user=row[2],  # user
                    hash=row[3],  # hash
                )
            )

        return files

    def delete_file(self, file: File) -> bool:
        """Delete a file from the database by its unique identifier.

        Args:
            file (File): An instance of the File class to be deleted.

        Returns:
            bool: True if the file was successfully deleted, False otherwise.

        Raises:
            TypeError: If the provided argument is not an instance of File.
        """

        if not isinstance(file, File):
            raise TypeError(
                f"Invalid type for file. Expecting 'File' but got {type(file)}"
            )

        self.execute("DELETE FROM File WHERE id = ?;", (file.id,))

        self.__delete_file(file)

        return True

    def delete_user_files(self, user_id: int) -> bool:
        """
        Delete all files associated with a specific user.

        Args:
            user_id (int): The unique identifier of the user whose files are to be deleted.

        Returns:
            bool: True if the deletion was successful, False otherwise.
        """
        self.execute(
            "DELETE FROM File WHERE user_id = ?;",
            (user_id,),
        )
        return True

    def add_program(self, program: Program) -> Optional[Program]:
        """Add a new program to the database.

        Args:
            program (Program): An instance of the Program class containing program details.

        Returns:
            Optional[Program]: The updated program instance if added or None if an error occured.

        Raises:
            TypeError: If the provided argument is not an instance of Program.
        """
        if not isinstance(program, Program):
            raise TypeError(
                f"Invalid type for program. Expecting 'Program' but got {type(program)}"
            )

        program_id = self.execute(
            "INSERT INTO Program (name, user_id, language, file) VALUES (?, ?, ?, ?);",
            (program.name, program.user, program.language, program.file),
        )
        if program_id is None:
            return None

        program.id = program_id
        return program

    def get_program(
        self, program_id: int, user_id: Optional[int] = None
    ) -> Optional[Program]:
        """Retrieve a program from the database by ID.

        Args:
            program_id (int): The ID of the program to retrieve.
            user_id (int): The ID of the user that hold the program

        Returns:
            Optional[Program]: An instance of the Program class with the retrieved program details,
                               or None if not found.
        """
        if isinstance(user_id, int):
            rows = self.fetch(
                "SELECT id, name, user_id, language, file FROM Program WHERE id = ? "
                "and user_id = ?;",
                (program_id, user_id),
            )

        else:
            rows = self.fetch(
                "SELECT id, name, user_id, language, file FROM Program WHERE id = ?;",
                (program_id,),
            )

        if len(rows) == 1:
            return Program(
                id=rows[0][0],  # id
                name=rows[0][1],  # name
                user=rows[0][2],  # user
                language=rows[0][3],  # language
                file=rows[0][4],  # file
            )

        return None

    def update_program(self, program: Program, user_id: Optional[int] = None) -> bool:
        """Update a program in the database.

        Args:
            program (Program): An instance of the Program class containing the updated details.
            user_id (Optional[int]): The ID of the user that holds the program.

        Returns:
            bool: True if the update was successful, False otherwise.

        Raises:
            TypeError: If the provided argument is not an instance of Program.
        """
        if not isinstance(program, Program):
            raise TypeError(
                f"Invalid type for program. Expecting 'Program' but got {type(program)}"
            )

        if isinstance(user_id, int):
            # Update the program only if the user_id matches
            self.execute(
                "UPDATE Program SET name = ?, language = ?, file = ? "
                "WHERE id = ? AND user_id = ?;",
                (
                    program.name,
                    program.language,
                    program.file,
                    program.id,
                    user_id,
                ),
            )
        else:
            # Update the program without checking user_id
            self.execute(
                "UPDATE Program SET name = ?, language = ?, file = ? WHERE id = ?;",
                (
                    program.name,
                    program.language,
                    program.file,
                    program.id,
                ),
            )

        return True

    def list_user_programs(self, user_id: int) -> list[Program]:
        """
        Retrieve a list of programs associated with a specific user.

        This method queries the database for all programs that belong to the user
        identified by the given user_id.

        Args:
            user_id (int): The unique identifier of the user whose programs are to be retrieved.

        Returns:
            list[Program]: A list of Program objects associated with the specified user.
                            If the user has no associated programs, an empty list is returned.
        """
        programs = []
        rows = self.fetch(
            "SELECT id, name, user_id, language, file FROM Program WHERE user_id = ?;",
            (user_id,),
        )
        for row in rows:
            programs.append(
                Program(
                    id=row[0],  # id
                    name=row[1],  # name
                    user=row[2],  # user
                    language=row[3],  # language
                    file=row[4],  # file
                )
            )

        return programs

    def delete_program(self, program: Program) -> bool:
        """Delete a program from the database by its unique identifier.

        Args:
            program (Program): The Program object to be deleted.

        Returns:
            bool: True if the program was successfully deleted, False otherwise.

        Raises:
            TypeError: If the provided argument is not an instance of Program.
        """
        if not isinstance(program, Program):
            raise TypeError(
                f"Invalid type for program. Expecting 'Program' but got {type(program)}"
            )

        self.execute("DELETE FROM Program WHERE id = ?;", (program.id,))
        return True

    def delete_user_programs(self, user_id: int) -> bool:
        """
        Delete all programs associated with a specific user.

        Args:
            user_id (int): The unique identifier of the user whose programs are to be deleted.

        Returns:
            bool: True if the deletion was successful, False otherwise.
        """
        self.execute(
            "DELETE FROM Program WHERE user_id = ?;",
            (user_id,),
        )
        return True

    def add_section(self, section: Section) -> Optional[Section]:
        """Add a new section to the database.

        Args:
            section (Section): An instance of the Section class containing section details.

        Returns:
            Optional[Section]: The updated section instance if added or None if an error occured.
        """
        if not isinstance(section, Section):
            raise TypeError(
                f"Invalid type for section. Expecting 'Section' but got {type(section)}"
            )

        section_id = self.execute(
            'INSERT INTO Section (name, program, file_offset, start, "end", perms, kind) '
            "VALUES (?, ?, ?, ?, ?, ?, ?);",
            (
                section.name,
                section.program,
                section.file_offset,
                section.start,
                section.end,
                section.perms,
                section.kind,
            ),
        )
        if section_id is None:
            return None

        section.id = section_id
        return section

    def get_section(
        self, section_id: int, program_id: Optional[int] = None
    ) -> Optional[Section]:
        """Retrieve a section from the database by ID.

        Args:
            section_id (int): The ID of the section to retrieve.
            program_id (Optional[int]): The ID of the program that own this section.

        Returns:
            Optional[Section]: An instance of the Section class with the retrieved section details,
                               or None if not found.
        """

        if isinstance(program_id, int):
            rows = self.fetch(
                'SELECT id, name, program, file_offset, start, "end", perms, kind FROM Section '
                "WHERE id = ? and program = ?;",
                (section_id, program_id),
            )

        else:
            rows = self.fetch(
                'SELECT id, name, program, file_offset, start, "end", perms, kind FROM Section'
                " WHERE id = ?;",
                (section_id,),
            )

        if len(rows) == 1:
            return Section(
                id=rows[0][0],  # id
                name=rows[0][1],  # name
                program=rows[0][2],  # program
                file_offset=rows[0][3],  # file_offset
                start=rows[0][4],  # start
                end=rows[0][5],  # end
                perms=rows[0][6],  # perms
                kind=rows[0][7],  # kind
            )

        return None

    def list_program_sections(self, program_id: int) -> list[Section]:
        """Retrieve a list of sections associated with a specific program.

        This method queries the database for all sections that belong to the
        program identified by the given program_id.

        Args:
            program_id (int): The unique identifier of the program whose sections
                              are to be retrieved.

        Returns:
            list[Section]: A list of Section objects associated with the specified
                            program. If the program has no associated sections,
                            an empty list is returned.
        """
        sections = []
        rows = self.fetch(
            'SELECT id, name, program, file_offset, start, "end", perms, kind FROM Section '
            "WHERE program = ?;",
            (program_id,),
        )
        for row in rows:
            sections.append(
                Section(
                    id=row[0],  # id
                    name=row[1],  # name
                    program=row[2],  # program
                    file_offset=row[3],  # file_offset
                    start=row[4],  # start
                    end=row[5],  # end
                    perms=row[6],  # perms
                    kind=row[7],  # kind
                )
            )

        return sections

    def delete_section(self, section: Section) -> bool:
        """Delete a section from the database by its unique identifier.

        Args:
            section (Section): The Section object to be deleted.

        Returns:
            bool: True if the section was successfully deleted, False otherwise.

        Raises:
            TypeError: If the provided argument is not an instance of Section.
        """
        if not isinstance(section, Section):
            raise TypeError(
                f"Invalid type for section. Expecting 'Section' but got {type(section)}"
            )

        self.execute("DELETE FROM Section WHERE id = ?;", (section.id,))
        return True

    def delete_program_sections(self, program_id: int) -> bool:
        """
        Delete all sections associated with a specific program.

        Args:
            program_id (int): The unique identifier of the program whose
                              sections are to be deleted.

        Returns:
            bool: True if the deletion was successful, False otherwise.
        """
        self.execute(
            "DELETE FROM Section WHERE program = ?;",
            (program_id,),
        )
        return True

    def add_function(self, function: Function) -> Optional[Function]:
        """Add a new function to the database.

        Args:
            function (Function): An instance of the Function class containing function details.

        Returns:
            Optional[Function]: The updated function instance if added or None if an error occured.
        """
        if not isinstance(function, Function):
            raise TypeError(
                f"Invalid type for function. Expecting 'Function' but got {type(function)}"
            )

        function_id = self.execute(
            'INSERT INTO Function (name, "offset", section, details) VALUES (?, ?, ?, ?);',
            (
                function.name,
                function.offset,
                function.section,
                json.dumps(function.details),
            ),
        )
        if function_id is None:
            return None

        function.id = function_id
        return function

    def get_function(
        self, function_id: int, section_id: Optional[int] = None
    ) -> Optional[Function]:
        """Retrieve a function from the database by ID.

        Args:
            function_id (int): The ID of the function to retrieve.
            section_id (Optional[int]): The ID of the section that own this function.

        Returns:
            Optional[Function]: An instance of the Function class with the retrieved function
                                details, or None if not found.
        """
        if isinstance(section_id, int):
            rows = self.fetch(
                'SELECT id, name, "offset", section, details FROM Function '
                "WHERE id = ? and section = ?;",
                (function_id, section_id),
            )
        else:
            rows = self.fetch(
                'SELECT id, name, "offset", section, details FROM Function WHERE id = ?;',
                (function_id,),
            )

        if len(rows) == 1:
            return Function(
                id=rows[0][0],  # id
                name=rows[0][1],  # name
                offset=rows[0][2],  # offset
                section=rows[0][3],  # section
                details=json.loads(rows[0][4]),  # details
            )

        return None

    def list_section_functions(self, section_id: int) -> list[Function]:
        """Retrieve a list of fucntions associated with a specific section.

        This method queries the database for all functions that belong to the
        section identified by the given section_id.

        Args:
            section_id (int): The unique identifier of the section whose functions
                              are to be retrieved.

        Returns:
            list[Function]: A list of Function objects associated with the specified
                            section. If the section has no associated fucntions,
                            an empty list is returned.
        """
        functions = []
        rows = self.fetch(
            'SELECT id, name, "offset", section, details FROM Function WHERE section = ?;',
            (section_id,),
        )
        for row in rows:
            functions.append(
                Function(
                    id=row[0],  # id
                    name=row[1],  # name
                    offset=row[2],  # offset
                    section=row[3],  # section
                    details=json.loads(row[4]),  # details
                )
            )

        return functions

    def delete_section_functions(self, section_id: int) -> bool:
        """
        Deletes all functions associated with a specific section in the database.

        Parameters:
            section_id (int): The ID of the section whose associated functions
                          are to be deleted. Must be an integer.

        Returns:
            bool: Returns True if the deletion was successful.

        Raises:
            TypeError: If section_id is not of type int.
        """
        if not isinstance(section_id, int):
            raise TypeError(
                f"Invalid type for section_id. Expecting 'int' but got {type(section_id)}"
            )

        self.execute("DELETE FROM Function WHERE section = ?;", (section_id,))
        return True

    def delete_function(self, function: Function) -> bool:
        """Delete a function from the database by its unique identifier.

        Args:
            function (Function): The Function object to be deleted.

        Returns:
            bool: True if the function was successfully deleted, False otherwise.

        Raises:
            TypeError: If the provided argument is not an instance of Function.
        """
        if not isinstance(function, Function):
            raise TypeError(
                f"Invalid type for function. Expecting 'Function' but got {type(function)}"
            )

        self.execute("DELETE FROM Function WHERE id = ?;", (function.id,))
        return True

    def add_match(self, match: Match) -> Optional[Match]:
        """Add a new match to the database.

        Args:
            match (Match): An instance of the Match class containing match details.

        Returns:
            Optional[Match]: The updated match instance if added or None if an error occured.
        """
        if not isinstance(match, Match):
            raise TypeError(
                f"Invalid type for match. Expecting 'Match' but got {type(match)}"
            )

        # Convert dict to JSON string for storage
        match_id = self.execute(
            "INSERT INTO Match (name, function, metadata) VALUES (?, ?, ?);",
            (match.name, match.function, json.dumps(match.metadata)),
        )
        if match_id is None:
            return None

        match.id = match_id
        return match

    def get_match(self, match_id: int) -> Optional[Match]:
        """Retrieve a match from the database by ID.

        Args:
            match_id (int): The ID of the match to retrieve.

        Returns:
            Optional[Match]: An instance of the Match class with the retrieved match details,
                             or None if not found.
        """
        rows = self.fetch(
            "SELECT id, name, function, metadata FROM Match WHERE id = ?;", (match_id,)
        )
        if len(rows) == 1:
            # Convert JSON string back to dict
            return Match(
                id=rows[0][0],  # id
                name=rows[0][1],  # name
                function=rows[0][2],  # function
                metadata=json.loads(rows[0][3]),  # metadata
            )

        return None

    def list_function_matches(self, function_id: int) -> list[Match]:
        """Retrieve a list of matches associated with a specific function.

        This method queries the database for all matches that belong to the
        function identified by the given function_id.

        Args:
            function_id (int): The unique identifier of the function whose matches
                              are to be retrieved.

        Returns:
            list[Match]: A list of matche objects associated with the specified
                            function. If the function has no associated fucntions,
                            an empty list is returned.
        """
        matches = []
        rows = self.fetch(
            "SELECT id, name, function, metadata FROM Match WHERE function = ?;",
            (function_id,),
        )
        for row in rows:
            matches.append(
                Match(
                    id=row[0],  # id
                    name=row[1],  # name
                    function=row[2],  # function
                    metadata=json.loads(row[3]),  # metadata
                )
            )

        return matches

    def delete_match(self, match: Match) -> bool:
        """Delete a match from the database by its unique identifier.

        Args:
            match (Match): The Match object to be deleted.

        Returns:
            bool: True if the match was successfully deleted, False otherwise.

        Raises:
            TypeError: If the provided argument is not an instance of Match.
        """
        if not isinstance(match, Match):
            raise TypeError(
                f"Invalid type for match. Expecting 'Match' but got {type(match)}"
            )

        self.execute("DELETE FROM Match WHERE id = ?;", (match.id,))
        return True

    def add_analysis(self, analysis: Analysis) -> Optional[Analysis]:
        """Adds an analysis to the running analyses.

        Args:
            analysis (Analysis): The Analysis object to be added.

        Raises:
            TypeError: If `analysis` is not an instance of `Analysis`.

        Returns:
            Optional[Analysis]: The added Analysis object if successful,
                or None if the analysis for the given program is already running.
        """
        if not isinstance(analysis, Analysis):
            raise TypeError(
                f"Invalid type for analysis. Expecting 'Analysis' but got {type(analysis)}"
            )

        with self._analysis_lock:
            if analysis.program in self._running_analysis:
                # self._logger.debug(
                #     "Analysis for program {} is already running".format(
                #         analysis.program
                #     )
                # )
                return None

            self._running_analysis.update({analysis.program: analysis})
            return analysis

    def get_analysis(
        self, program_id: int, user_id: Optional[int] = None
    ) -> Optional[Analysis]:
        """Retrieves the analysis associated with a given program ID.

        Args:
            program_id (int): The ID of the program whose analysis is to be retrieved.
            user_id (Optional[int]): The ID of the user associated with the analysis,
                                     if specified.

        Returns:
            Optional[Analysis]: The Analysis object if found and belonging to the
                specified user, or None otherwise.
        """
        analysis = None
        with self._analysis_lock:
            analysis = self._running_analysis.get(program_id)

        # If the user_id was specified, also unsure that this analysis belong
        # to the given user, if not set it to None
        if analysis and user_id and not analysis.user == user_id:
            analysis = None

        return analysis

    def delete_analysis(self, analysis: Analysis) -> bool:
        """Deletes an analysis from the running analyses.

        Args:
            analysis (Analysis): The Analysis object to be deleted.

        Raises:
            TypeError: If `analysis` is not an instance of `Analysis`.

        Returns:
            bool: True if the analysis was successfully deleted,
                False if it was not found in the running analyses.
        """
        if not isinstance(analysis, Analysis):
            raise TypeError(
                "Invalid type for analysis. Expecting 'Analysis' but got {type(analysis)}"
            )

        with self._analysis_lock:
            if analysis.program not in self._running_analysis:
                return False

            del self._running_analysis[analysis.program]

        return True
