"""Model for Frontend objects"""

from typing import Optional, List
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from sighthouse.core.utils import get_hash, parse_uri


class Model:
    """Base for dict-serializable objects.

    TYPES maps each serialized field to its type (`list` means list of strings,
    a Model subclass is built from a nested dict), REQUIRED lists mandatory fields
    and DEFAULTS fills missing constructor arguments.
    """

    TYPES: dict = {}
    REQUIRED: tuple = ()
    DEFAULTS: dict = {}

    @classmethod
    def from_dict(cls, data: dict):
        """Build and validate an instance, raise ValueError on invalid data."""
        if not isinstance(data, dict):
            raise ValueError("data is not a dict")
        fields = dict(cls.DEFAULTS)
        for key, kind in cls.TYPES.items():
            value = data.get(key)
            if value is None:
                if key in cls.REQUIRED:
                    raise ValueError(f"{key} is required")
                continue
            if isinstance(kind, type) and issubclass(kind, Model):
                value = kind.from_dict(value)
            elif kind is list:
                if not isinstance(value, list) or not all(
                    isinstance(e, str) for e in value
                ):
                    raise ValueError(f"{key} must be a list of strings")
            elif not isinstance(value, kind):
                raise ValueError(
                    f"{key} must be of type {getattr(kind, '__name__', kind)}"
                )
            fields[key] = value
        obj = cls(**fields)
        obj.validate()
        return obj

    def validate(self) -> None:
        """Raise ValueError if a field is out of range."""

    def to_dict(self) -> dict:
        return {
            key: value.to_dict() if isinstance(value, Model) else value
            for key, value in ((k, getattr(self, k)) for k in self.TYPES)
        }


class User(Model, UserMixin):
    """Class to represent a user

    @NOTE: The id attribute is the unique identifier in the database but the 'real'
           identifier is the username (which is also unique)
    """

    INVALID_ID = 0
    VALID_ROLES = ["user", "admin"]
    DEFAULT_ROLE = "user"
    TYPES = {"id": int, "name": str, "hash": str, "role": str}
    REQUIRED = ("name", "hash", "role")
    DEFAULTS = {"id": INVALID_ID}

    def __init__(self, id: int, name: str, hash: str, role: Optional[str] = None):
        self.id = id
        self.name = name
        self.hash = hash
        self.role = role or self.DEFAULT_ROLE

    @classmethod
    def create(cls, name: str, password: str, role: str = DEFAULT_ROLE) -> "User":
        """Build a new user, not yet stored, from a clear password"""
        user = cls(cls.INVALID_ID, name, "", role)
        user.set_password(password)
        return user

    def set_password(self, password: str) -> None:
        """Set the current password for the user

        Args:
            password (str): The new password to set
        """
        self.hash = generate_password_hash(password, method="pbkdf2:sha256")

    def check_password(self, password: str) -> bool:
        """Check the given password against the current one.

        Args:
            password (str): The password to test

        Returns:
            bool: True if the password matches, False otherwise
        """
        return check_password_hash(self.hash, password)

    def validate(self) -> None:
        if self.role not in self.VALID_ROLES:
            raise ValueError(f"role must be one of: {', '.join(self.VALID_ROLES)}")

    def is_admin(self) -> bool:
        return self.role == "admin"

    def to_public_dict(self) -> dict:
        """Same as to_dict without the password hash."""
        return {"id": self.id, "name": self.name, "role": self.role}


class File(Model):
    """Class to represent a user file"""

    INVALID_ID = 0
    TYPES = {"id": int, "name": str, "user": int, "hash": str}
    REQUIRED = ("name", "user", "hash")
    DEFAULTS = {"id": INVALID_ID}

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


class Program(Model):
    """Class to represent user program"""

    INVALID_ID = 0
    TYPES = {"id": int, "name": str, "user": int, "language": str, "file": int}
    REQUIRED = ("name", "user", "language", "file")
    DEFAULTS = {"id": INVALID_ID}

    def __init__(self, id: int, name: str, user: int, language: str, file: int):
        self.id = id
        self.name = name
        self.user = user
        self.language = language
        self.file = file


class Section(Model):
    """Class to represent a program section"""

    INVALID_ID = 0
    TYPES = {
        "id": int,
        "name": str,
        "program": int,
        "file_offset": int,
        "start": int,
        "end": int,
        "perms": str,
        "kind": str,
    }
    REQUIRED = ("name", "program", "file_offset", "start", "end", "perms", "kind")
    DEFAULTS = {"id": INVALID_ID}

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


class Function(Model):
    """Class to represent a section function"""

    INVALID_ID = 0
    TYPES = {"id": int, "name": str, "offset": int, "section": int, "details": dict}
    REQUIRED = ("name", "offset", "section")
    DEFAULTS = {"id": INVALID_ID}

    def __init__(
        self,
        id: int,
        name: str,
        offset: int,
        section: int,
        details: Optional[dict] = None,
    ):
        self.id = id
        self.name = name
        self.offset = offset
        self.section = section
        self.details = details if details is not None else {}


class Match(Model):
    """Class to represent a function match"""

    INVALID_ID = 0
    TYPES = {"id": int, "name": str, "function": int, "metadata": dict}
    REQUIRED = ("name", "function", "metadata")
    DEFAULTS = {"id": INVALID_ID}

    def __init__(self, id: int, name: str, function: int, metadata: dict):
        self.id = id
        self.name = name
        self.function = function
        self.metadata = metadata


class Analysis(Model):
    """Class that represent a running analysis

    @NOTE: This class contains the program and user which is redondant as program already holds
           the user identifier, however it allow to quickly check if an analysis is running for
           a given user and a given program without having to query the database.

           If we did not had the user identifier in the analysis, it could allow another user
           to check if an analysis is running for any given program, including programs that he
           does not own.
    """

    TYPES = {"program": int, "user": int, "info": dict}
    REQUIRED = ("program", "user", "info")

    def __init__(self, program: int, user: int, info: dict):
        self.program = program
        self.user = user
        self.info = info


class AnalysisOptions(Model):
    """Class that store analysis options for the frontend

    This class holds all options relevant for running the analysis. Those options
    can impact different steps. For instance, `bob_ross` is a post analysis option
    while `auto_analysis` is relevant when running the analysis inside the ghidra
    script.
    """

    TYPES = {"bob_ross": bool, "auto_analysis": bool}

    def __init__(self, bob_ross: bool = False, auto_analysis: bool = False):
        self.bob_ross = bob_ross
        self.auto_analysis = auto_analysis


class AnalyzerConfig(Model):
    """Base configuration shared by analyzers: database urls and function size filter"""

    TYPES = {"urls": list, "min_instructions": int, "max_instructions": int}

    def __init__(
        self,
        urls: Optional[List[str]] = None,
        min_instructions: int = 0,
        max_instructions: int = 0,
    ):
        self.urls = urls or []
        self.min_instructions = min_instructions
        self.max_instructions = max_instructions

    def validate(self) -> None:
        for e in self.urls:
            parse_uri(e)
        if self.max_instructions < 0:
            raise ValueError("max_instructions must be positive")
        if self.min_instructions < 0:
            raise ValueError("min_instructions must be positive")
        if self.max_instructions != 0 and self.max_instructions < self.min_instructions:
            raise ValueError(
                "max_instructions must be greater than min_instructions when not set to zero"
            )


class FidbConfig(AnalyzerConfig):
    """FIDB analysis configuration"""

    def __init__(
        self,
        urls: Optional[List[str]] = None,
        min_instructions: int = 2,
        max_instructions: int = 0,
    ):
        super().__init__(urls, min_instructions, max_instructions)


class BSimConfig(AnalyzerConfig):
    """BSIM analysis configuration"""

    TYPES = {
        **AnalyzerConfig.TYPES,
        "number_of_matches": int,
        "similarity": (int, float),
        "confidence": (int, float),
    }

    def __init__(
        self,
        urls: Optional[List[str]] = None,
        min_instructions: int = 10,
        max_instructions: int = 0,
        number_of_matches: int = 10,
        similarity: float = 0.7,
        confidence: float = 1.0,
    ):
        super().__init__(urls, min_instructions, max_instructions)
        self.number_of_matches = number_of_matches
        self.similarity = similarity
        self.confidence = confidence

    def validate(self) -> None:
        super().validate()
        if self.number_of_matches <= 0:
            raise ValueError("number_of_matches must be greater than 0")
        if self.similarity < 0.0 or self.similarity > 1.0:
            raise ValueError("similarity must be between 0.0 and 1.0")
        if self.confidence < 0.0:
            raise ValueError("confidence must be positive")


class FrontendConfig(Model):
    """Frontend configuration"""

    TYPES = {
        "database_uri": str,
        "repo_url": str,
        "ghidra_dir": str,
        "host": str,
        "port": int,
        "worker_url": str,
        "worker_count": int,
        "bsim_config": BSimConfig,
        "fidb_config": FidbConfig,
    }
    REQUIRED = ("database_uri",)
    # Fields that only take effect after a server restart
    RESTART_FIELDS = (
        "repo_url",
        "ghidra_dir",
        "host",
        "port",
        "worker_url",
        "worker_count",
    )

    def __init__(
        self,
        database_uri: str,
        repo_url: Optional[str] = None,
        ghidra_dir: Optional[str] = None,
        host: Optional[str] = None,
        port: int = 6671,
        worker_url: Optional[str] = None,
        worker_count: int = 1,
        bsim_config: Optional[BSimConfig] = None,
        fidb_config: Optional[FidbConfig] = None,
    ):
        self.database_uri = database_uri
        self.repo_url = repo_url or "local://data"
        self.ghidra_dir = ghidra_dir
        self.host = host or "0.0.0.0"
        self.port = port
        self.worker_url = worker_url or "redis://localhost:6379/0"
        self.worker_count = worker_count
        self.bsim_config = bsim_config or BSimConfig()
        self.fidb_config = fidb_config or FidbConfig()

    def restart_required(self, previous: "FrontendConfig") -> List[str]:
        """Return the restart-only fields whose value differs from `previous`."""
        return [
            f for f in self.RESTART_FIELDS if getattr(self, f) != getattr(previous, f)
        ]

    def validate(self) -> None:
        parse_uri(self.database_uri)
        parse_uri(self.repo_url)
        parse_uri(self.worker_url)
        if self.port < 1024 or self.port > 65535:
            raise ValueError("port must be between 1024 and 65535")
        if self.worker_count <= 0:
            raise ValueError("worker_count must be greater than zero")
        self.bsim_config.validate()
        self.fidb_config.validate()
