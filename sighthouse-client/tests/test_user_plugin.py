import unittest
from typing import List

from sighthouse.client import Section, Function, LoggingSighthouse, SightHouseAnalysis


class SightHouseMockAnalysis(SightHouseAnalysis):

    def get_current_arch(self) -> str:
        """get current architecture and translate to ghidra one"""
        return "x86:LE:32:default"

    def update_progress(self, message: str) -> None:
        """show an update progress

        Args:
            message (str): message to show
        """

    def get_current_binary(self) -> bytes:
        """Retrieve the current binaries in bytes

        Returns:
            bytes: the content in bytes of the current binaries
        """
        b"\xde\xad\xbe\xef"

    def add_tag(self, address: int, tag: str, message: str) -> None:
        """Add a tag on the SRE

        Args:
            address (int): address where put the tag
            tag (str): tag of message
            message (str): message to show
        """

    def get_program_name(self) -> str:
        """Get program name

        Returns:
            str: the program name
        """
        return "program.bin"

    def get_sections(self) -> List[Section]:
        """Get sections

        Returns:
            List[Section]: list sections
        """
        return [
            Section(
                name=".text",
                start=0x1000,
                end=0x2000,
                fileoffset=42,
                perms="RWX",
                kind="",
            )
        ]

    def get_functions(self, section: Section) -> List[Function]:
        """get functions

        Args:
            section (Section): section

        Returns:
            List[Function]: list of function inside the section
        """
        if section.name == ".text":
            return [
                Function(name="foo", offset=12),
                Function(name="bar", offset=42, details={"thumb": False}),
            ]

        return []

    def get_hash_program(self) -> str:
        """get hash of program

        Returns:
            str: sha256 string
        """
        return "b31380ccd7be897eba66c46c6e7a1f9ef99258e9e578bc080e40eafdaf3c2c28"


class MockLoggingSighthouse(LoggingSighthouse):

    def __init__(self) -> None:
        """Initialize logging class"""

    def error(self, message: str):
        """Show an error message

        Args:
            message (str): The message to show
        """
        print(f"E:{message}")

    def warning(self, message: str):
        """Show an warning message

        Args:
            message (str): The message to show
        """
        print(f"W:{message}")

    def info(self, message: str):
        """Show an info message

        Args:
            message (str): The message to show
        """
        print(f"I:{message}")


class MockResponse:

    def __init__(self, status_code: int, json: dict = None):
        self.status_code = status_code
        self._json = json

    def json(self) -> dict:
        return self._json

    def raise_for_status(self):
        if self.status_code != 200:
            raise Exception("Bad status_code")


class MockSession:

    def get(self, url: str, *args, **kwargs):
        if url == "http://localhost/api/v1/programs":
            return MockResponse(200, json={"programs": []})

        if url == "http://localhost/api/v1/programs/5678/analyze":
            return MockResponse(
                200, json={"analysis": {"info": {"status": "finished"}}}
            )

        if url == "http://localhost/api/v1/programs/5678":
            return MockResponse(
                200,
                json={
                    "sections": [
                        {
                            "id": 9101,
                            "start": 0x1000,
                            "functions": [
                                {"id": 2468, "name": "foo", "offset": 12},
                                {
                                    "id": 1357,
                                    "name": "bar",
                                    "offset": 24,
                                    "matches": [
                                        {
                                            "name": "barz",
                                            "metadata": {
                                                "executable": '{"name":"libbarz","origin":"http://libbarz.com","version":"1234"}',
                                                "score": 100,
                                                "nb_match": 2,
                                            },
                                        }
                                    ],
                                },
                            ],
                        }
                    ]
                },
            )

        return MockResponse(400)

    def post(self, url: str, *args, **kwargs):
        if url == "http://localhost/api/v1/login":
            return MockResponse(200)

        if url == "http://localhost/api/v1/uploads":
            return MockResponse(200, json={"file": 1234})

        if url == "http://localhost/api/v1/programs":
            return MockResponse(
                200, json={"programs": [{"id": 5678, "name": "program.bin"}]}
            )

        if url == "http://localhost/api/v1/programs/5678/sections":
            return MockResponse(200, json={"sections": [{"id": 9101}]})

        if url == "http://localhost/api/v1/programs/5678/sections/9101/functions":
            return MockResponse(
                200,
                json={
                    "functions": [
                        {"id": 2468, "name": "foo"},
                        {"id": 1357, "name": "bar"},
                    ]
                },
            )

        if url == "http://localhost/api/v1/programs/5678/analyze":
            return MockResponse(200)

        return MockResponse(400)

    def delete(self, url: str, *args, **kwargs):
        if url == "http://localhost/api/v1/programs/5678/sections/":
            return MockResponse(200)

        return MockResponse(400)


class TestClient(unittest.TestCase):

    def test_mock_analysis(self):
        analysis = SightHouseMockAnalysis(
            "user", "password", "http://localhost", MockLoggingSighthouse()
        )
        # Patch client session
        analysis._client._session = MockSession()
        try:
            self.assertTrue(analysis.run())
        except Exception as e:
            self.fail(f"Failed to analyze: {e}")


if __name__ == "__main__":
    unittest.main()
