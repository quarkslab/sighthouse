from tempfile import TemporaryDirectory
from unittest.mock import MagicMock
from pathlib import Path
import unittest
import shutil
import os

from sighthouse.core.utils.analyzer import build_script


class TestAnalyzerScript(unittest.TestCase):

    GHIDRA_DIR = Path(os.getenv("GHIDRA_INSTALL_DIR")) if os.getenv("GHIDRA_INSTALL_DIR") else None  # type: ignore[arg-type]
    SCRIPT_DIR = (
        Path(__file__).parent.parent
        / "src"
        / "sighthouse"
        / "pipeline"
        / "core_modules"
        / "GhidraAnalyzer"
        / "ghidrascripts"
    )

    @unittest.skipIf(
        GHIDRA_DIR is None, "GHIDRA_INSTALL_DIR environment variable not set"
    )
    def test_analyzer_script_compile(self):
        analyzer_script_path = self.SCRIPT_DIR / "SightHouseAnalyzerScript.java"
        try:
            with TemporaryDirectory() as tmpdirname:
                tmpdir = Path(tmpdirname)
                shutil.copy(analyzer_script_path, tmpdir)
                build_script(Path(self.GHIDRA_DIR), tmpdir)  # type: ignore[arg-type]
                print("Successfully built Ghidra scripts.")
        except Exception as e:
            self.fail(f"Failed to build scripts: {e}")


if __name__ == "__main__":
    unittest.main()
