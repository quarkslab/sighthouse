import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from sighthouse.core.utils.repo import Repo


class TestRepo(unittest.TestCase):

    def test_init_local(self):
        repo = Repo("local:///tmp/")
        self.assertEqual(repo._uri["uri"], "local:///tmp/")
        self.assertIsNone(repo._client)

    def test_init_s3(self):
        repo = Repo("s3://test-bucket/dir")
        self.assertEqual(repo._uri["uri"], "s3://test-bucket/dir")
        self.assertIsNotNone(repo._client)

    def test_init_invalid_scheme(self):
        with self.assertRaises(ValueError):
            Repo("invalid:///tmp/test")

    def test_list_directory_local(self):
        repo = Repo("local:///tmp/")
        with patch.object(
            Path, "iterdir", return_value=[Path("file1.txt"), Path("file2.txt")]
        ):
            files = repo.list_directory("/")

        self.assertEqual(files, ["file1.txt", "file2.txt"])

    def test_list_directory_s3(self):
        repo = Repo("s3://test-bucket/dir")
        mock_client = MagicMock()
        mock_client.list_objects.return_value = [
            MagicMock(object_name="file1.txt"),
            MagicMock(object_name="file2.txt"),
        ]
        repo._client = mock_client
        files = repo.list_directory("/")
        self.assertEqual(files, ["file1.txt", "file2.txt"])

    def test_get_sharefile_local(self):
        repo = Repo("local:///tmp/")
        with patch.object(Path, "exists", return_value=True):
            share_path = repo.get_sharefile("/file.txt")

        self.assertEqual(share_path, "/tmp/file.txt")

    def test_get_sharefile_s3(self):
        repo = Repo("s3://test-bucket/dir")
        mock_client = MagicMock()
        mock_client.get_presigned_url.return_value = "http://presigned.url"
        repo._client = mock_client
        url = repo.get_sharefile("/some/file.txt")
        self.assertEqual(url, "http://presigned.url")

    @patch("pathlib.Path.exists", return_value=True)
    @patch(
        "builtins.open", new_callable=unittest.mock.mock_open, read_data=b"Test content"
    )
    def test_get_file_local_exists(self, mock_open, mock_exists):
        repo = Repo("local:///tmp/")
        result = repo.get_file("sample.txt")
        mock_open.assert_called_once_with(Path("/tmp/sample.txt"), "rb")
        self.assertEqual(result, b"Test content")

    def test_get_file_local_not_found(self):
        repo = Repo("local:///tmp/")
        with self.assertRaises(FileNotFoundError):
            repo.get_file("missing_file.txt")


if __name__ == "__main__":
    unittest.main()
