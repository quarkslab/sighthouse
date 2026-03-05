"""Generic abstraction for storing files"""

from typing import Any, Optional
from pathlib import Path
from io import BytesIO
from minio import Minio

from sighthouse.core.utils import parse_uri, download_file  # type: ignore[import-untyped]


class Repo:
    """
    A class that abstract the storage of files. Repository can be a local file based
    or rely on a S3 compatible server to store and retrieve files.
    """

    def __init__(self, uri: str, exist_ok: bool = False, secure: bool = True):
        """
        Initializes a repository instance.

        Args:
            uri (str): The URI of the repository which could be local or S3.
                       Local URIs typically start with "file://" and S3 URIs
                       start with "s3://".
        """
        self._uri = parse_uri(uri)
        self._uri["uri"] = uri
        self._client: Any = None

        if self._uri["type"] == "local":
            full_path = Path(self._uri["database"])
            if not full_path.exists() and not exist_ok:
                raise FileNotFoundError(f"Directory '{full_path}' does not exists")

        elif self._uri["type"] == "s3":
            self._client = Minio(
                endpoint=f"{self._uri['host']}:{self._uri['port']}",
                access_key=self._uri["user"],
                secret_key=self._uri["password"],
                secure=secure,
            )
        else:
            raise ValueError(f"Unsupported URI scheme: {self._uri.get('type')}")

    def __repr__(self) -> str:
        """Return a textual representation of this object"""
        return f'<{self.__class__.__name__}(uri="{self._uri["uri"]}")>'

    def push_file(self, upload_path: str, content: bytes) -> bool:
        """
        Pushes or uploads a file to the specified path in either local filesystem or S3.

        Args:
            upload_path (str): The path where the file should be uploaded.
            content (bytes): The content of the file to be uploaded.

        Returns:
            bool: True if successful, False otherwise.

        Raises:
            ValueError: If URI scheme is unsupported.
        """
        if self._uri["type"] == "local":
            full_path = Path(upload_path)
            if not full_path.is_absolute():
                full_path = (self._uri["database"] / full_path).resolve()
            elif not full_path.is_relative_to(self._uri["database"]):
                root = Path(self._uri["database"])
                full_path = root / full_path.relative_to(full_path.anchor)

            if not full_path.is_relative_to(self._uri["database"]):
                raise FileNotFoundError(
                    f"The given file does not exists: '{full_path}'"
                )

            # write file on filesystem
            full_path.parent.mkdir(parents=True, exist_ok=True)
            with open(full_path, "wb") as fp:
                fp.write(content)

        elif self._uri["type"] == "s3":
            self._client.put_object(
                self._uri["dbname"],
                str(Path(self._uri["directory"], upload_path).resolve()),
                BytesIO(content),
                len(content),
            )

        else:
            raise ValueError(f"Unsupported URI scheme: {self._uri.get('type')}")

        return True

    def delete_file(self, upload_path: str) -> None:
        """
        Deletes the specified file from either local filesystem or S3.

        Args:
            upload_path (str): The path of the file to be deleted.

        Raises:
            ValueError: If URI scheme is unsupported.
        """
        if self._uri["type"] == "local":
            full_path = Path(upload_path)
            if not full_path.is_absolute():
                full_path = (self._uri["database"] / full_path).resolve()
            elif not full_path.is_relative_to(self._uri["database"]):
                root = Path(self._uri["database"])
                full_path = root / full_path.relative_to(full_path.anchor)

            if not full_path.exists() or not full_path.is_relative_to(
                self._uri["database"]
            ):
                raise FileNotFoundError(
                    f"The given file does not exists: '{full_path}'"
                )

            full_path.unlink()
            # Remove empty dir up to root
            for parent in full_path.relative_to(self._uri["database"]).parents:
                try:
                    parent.rmdir()  # Remove only if directory is empty
                except OSError:
                    break

        elif self._uri["type"] == "s3":
            self._client.remove_object(
                self._uri["dbname"],
                str(Path(self._uri["directory"], upload_path).resolve()),
            )

        else:
            raise ValueError(f"Unsupported URI scheme: {self._uri.get('type')}")

    def get_file(self, upload_path: str) -> Optional[bytes]:
        """
        Retrieves the content of the specified file from either local filesystem or S3.

        Args:
            upload_path (str): The path of the file to be retrieved.

        Returns:
            bytes | None: The content of the file if found, otherwise None.

        Raises:
            ValueError: If URI scheme is unsupported.
        """
        if self._uri["type"] == "local":
            full_path = Path(upload_path)
            if not full_path.is_absolute():
                full_path = (self._uri["database"] / full_path).resolve()
            elif not full_path.is_relative_to(self._uri["database"]):
                root = Path(self._uri["database"])
                full_path = root / full_path.relative_to(full_path.anchor)

            if not full_path.exists() or not full_path.is_relative_to(
                self._uri["database"]
            ):
                raise FileNotFoundError(
                    f"The given file does not exists: '{full_path}'"
                )

            with open(full_path, "rb") as f:
                return f.read()

        elif self._uri["type"] == "s3":
            response = self._client.get_object(
                self._uri["dbname"],
                str(Path(self._uri["directory"], upload_path).resolve()),
            )
            return response.data if response else None

        else:
            raise ValueError(f"Unsupported URI scheme: {self._uri.get('type')}")

    def list_directory(self, path: str | Path) -> list[str]:
        """
        Lists all files in the specified directory from either local filesystem or S3.

        Args:
            path (str | Path): The directory to be listed.

        Returns:
            list[str]: A list of file names and directories within the specified path.

        Raises:
            ValueError: If URI scheme is unsupported.
        """
        if self._uri["type"] == "local":
            full_path = Path(path)
            if not full_path.is_absolute():
                full_path = (self._uri["database"] / full_path).resolve()
            elif not full_path.is_relative_to(self._uri["database"]):
                root = Path(self._uri["database"])
                full_path = root / full_path.relative_to(full_path.anchor)

            if (
                not full_path.exists()
                or not full_path.is_dir()
                or not full_path.is_relative_to(self._uri["database"])
            ):
                raise FileNotFoundError(
                    f"The given file does not exists: '{full_path}'"
                )

            return list(map(str, full_path.iterdir()))

        if self._uri["type"] == "s3":
            return list(
                map(
                    lambda e: e.object_name,
                    self._client.list_objects(self._uri["dbname"], prefix=str(path)),
                )
            )

        raise ValueError(f"Unsupported URI scheme: {self._uri.get('type')}")

    def get_sharefile(self, upload_path: str) -> Path | str:
        """
        Returns the path or URL for sharing the file.

        Args:
            upload_path (str): The path of the file to be shared.

        Returns:
            Path | str: A POSIX absolute path if local, a pre-signed URL if S3.

        Raises:
            ValueError: If URI scheme is unsupported.
        """
        if self._uri["type"] == "local":
            full_path = Path(upload_path)
            if not full_path.is_absolute():
                full_path = (self._uri["database"] / full_path).resolve()
            elif not full_path.is_relative_to(self._uri["database"]):
                root = Path(self._uri["database"])
                full_path = root / full_path.relative_to(full_path.anchor)

            if not full_path.exists() or not full_path.is_relative_to(
                self._uri["database"]
            ):
                raise FileNotFoundError(
                    f"The given file does not exists: '{full_path}'"
                )

            return full_path.absolute().as_posix()

        if self._uri["type"] == "s3":
            return self._client.get_presigned_url(
                "GET",
                self._uri["dbname"],
                str(Path(self._uri["directory"], upload_path).resolve()),
            )

        raise ValueError(f"Unsupported URI scheme: {self._uri.get('type')}")

    @staticmethod
    def download_sharefile(url: str, timeout: int = 3600) -> Optional[bytes]:
        """
        Downloads and returns the content of a file from a given URL or local path.

        Args:
            url (str): The URL or local path to the file to be downloaded.
            timeout (int): Timeout in seconds

        Returns:
            bytes | None: The content of the file if found, otherwise None.
        """
        if url.startswith("http://") or url.startswith("https://"):
            file = download_file(url, timeout=timeout)
            if file is not None:
                return file.read()

        if url.startswith("/"):
            with open(url, "rb") as f:
                return f.read()

        return None
