import unittest
from pathlib import Path
import tarfile
from io import BytesIO
from tempfile import TemporaryDirectory
from sighthouse.core.utils import run_process, create_tar, extract_tar


class TestUtilityFunctions(unittest.TestCase):

    def test_run_process_single_command(self):
        # Test running a simple command ('echo')
        returncode, stdout, stderr = run_process(["echo", "test"], capture_output=True)
        self.assertEqual(returncode, 0)
        self.assertEqual(stdout.strip(), b"test")
        self.assertEqual(stderr, b"")

    def test_run_process_pipeline(self):
        # Test running a pipeline command (['echo', 'test'], ['sed', 's/test/success/g'])
        returncode, stdout, stderr = run_process(
            [["echo", "test"], ["sed", "s/test/success/g"]], capture_output=True
        )
        self.assertEqual(returncode, 0)
        self.assertEqual(stdout.strip(), b"success")
        self.assertEqual(stderr, b"")

    def test_run_process_timeout(self):
        # Test running a command with a timeout
        with self.assertRaises(Exception):
            returncode, stdout, stderr = run_process(
                ["sleep", "2"], timeout=0.3, capture_output=True
            )

            self.assertEqual(returncode, -9)  # Should return -9 for timeout (SIGKILL)
            self.assertEqual(stdout, b"")
            self.assertEqual(stderr, b"")

    def test_create_tar(self):
        # Test creating a tar file
        base_name = Path(__file__).parent
        files = [Path(__file__)]  # Add current file path as test
        result = create_tar(base_name, files)

        # Verify the result is a BytesIO object
        self.assertIsInstance(result, BytesIO)

        # Further test if contents can be read from the tar
        result.seek(0)  # Move to the start of BytesIO
        with tarfile.open(fileobj=result, mode="r:gz") as tar:
            members = tar.getnames()
            self.assertIn(Path(__file__).name, members)

    def test_extract_tar(self):
        # Test extracting a tar file
        base_name = Path(__file__).parent
        files = [Path(__file__)]  # Using current file as content
        tar_data = create_tar(base_name, files)

        with TemporaryDirectory() as tmpdir:
            extract_to = Path(tmpdir)
            extract_to.mkdir(exist_ok=True)

            # Extract the tar data
            success = extract_tar(tar_data, extract_to)
            self.assertTrue(success)

            # Verify that the file was extracted
            extracted_file = extract_to / Path(__file__).name
            self.assertTrue(extracted_file.is_file())


if __name__ == "__main__":
    unittest.main()
