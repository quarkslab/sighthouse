import os
import unittest
from pathlib import Path
from sighthouse.core.utils.analyzer import (
    get_ghidra_languages,
    run_ghidra_script,
    get_ghidra_version,
    build_script,
)


class TestGhidraAnalyzer(unittest.TestCase):

    ghidra_dir = Path(os.getenv("GHIDRA_INSTALL_DIR")) if os.getenv("GHIDRA_INSTALL_DIR") else None  # type: ignore[arg-type]
    # Temporary path for the Ghidra script
    temp_script_path = None

    @unittest.skipIf(
        ghidra_dir is None, "GHIDRA_INSTALL_DIR environment variable not set"
    )
    def setUp(self):
        # Create a temporary directory for the script
        temp_dir = Path("/tmp/a1a50e07-aeda-4164-a71c-93c9511a4779")
        temp_dir.mkdir(exist_ok=True, parents=True)
        self.temp_script_path = temp_dir / "HelloWorld.java"

        # Write the Ghidra script to the temporary location
        with open(self.temp_script_path, "w") as f:
            f.write("""import ghidra.app.script.GhidraScript;

public class HelloWorld extends GhidraScript {

    public void run() throws Exception {
        println("Hello world");
    }
}""")

    @unittest.skipIf(
        ghidra_dir is None, "GHIDRA_INSTALL_DIR environment variable not set"
    )
    def tearDown(self):
        if self.temp_script_path:
            for item in self.temp_script_path.parent.iterdir():
                item.unlink()
            self.temp_script_path.parent.rmdir()

    @unittest.skipIf(
        ghidra_dir is None, "GHIDRA_INSTALL_DIR environment variable not set"
    )
    def test_get_ghidra_languages(self):
        languages = get_ghidra_languages(Path(self.ghidra_dir))  # type: ignore[arg-type]
        self.assertIsInstance(languages, list)
        self.assertTrue(len(languages) > 0)
        print("Ghidra supports the following languages:", languages)

    @unittest.skipIf(
        ghidra_dir is None, "GHIDRA_INSTALL_DIR environment variable not set"
    )
    def test_run_ghidra_script(self):
        args = ["args1"]
        returncode, stdout, stderr = run_ghidra_script(
            Path(self.ghidra_dir),  # type: ignore[arg-type]
            script=self.temp_script_path,  # type: ignore[arg-type]
            args=args,
            capture_output=True,
        )
        self.assertEqual(returncode, 0)
        self.assertTrue(b"Hello world" in stdout)

    @unittest.skipIf(
        ghidra_dir is None, "GHIDRA_INSTALL_DIR environment variable not set"
    )
    def test_get_ghidra_version(self):
        version = get_ghidra_version(Path(self.ghidra_dir))  # type: ignore[arg-type]
        self.assertIsNotNone(version)
        print("Ghidra version:", version)

    @unittest.skipIf(
        ghidra_dir is None, "GHIDRA_INSTALL_DIR environment variable not set"
    )
    def test_build_script(self):
        try:
            build_script(Path(self.ghidra_dir), self.temp_script_path)  # type: ignore[arg-type]
            print("Successfully built Ghidra scripts.")
        except Exception as e:
            self.fail(f"Failed to build scripts: {e}")


if __name__ == "__main__":
    unittest.main()
