from __future__ import annotations
from http.client import HTTPConnection
from io import BytesIO
from urllib.parse import urlparse
from typing import List

import logging
import requests
import hashlib
import json
import time


def get_hash(data: bytes) -> str:
    """Compute the SHA256 of the given data"""
    sha256_hash = hashlib.sha256()
    sha256_hash.update(data)
    return sha256_hash.hexdigest()


def debug_requests_on():
    """Switches on logging of the requests module."""
    HTTPConnection.debuglevel = 1

    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True


class Match(object):
    """Show match"""

    def __init__(self, executable: str, function: str, score: float, nb_match: int):
        self.executable = json.loads(executable)
        self.metadatas = self.executable.get("metadata", None)
        if self.metadatas is None:
            self.metadatas = [
                (self.executable.get("name"), self.executable.get("version"))
            ]
        self.origin = self.executable["origin"]
        self.function = function
        self.score = score
        self.nb_match = nb_match

    def to_string(self, indent=0) -> str:
        sdk = ", ".join(f"{name}@{version}" for name, version in self.metadatas)
        return (
            f"{indent * ' '}- Function: {self.function}\n"
            f"{indent * ' '}  SDK: {sdk} {self.origin}\n"
            f"{indent * ' '}  Score: {self.score:.4f}\n"
            f"{indent * ' '}  Number of match: {self.nb_match}"
        )


class Section(object):
    """Manipulate Section object"""

    def __init__(
        self,
        name: str,
        start: int,
        end: int,
        fileoffset: int,
        perms: str,
        kind: str,
        id: int = -1,
    ):
        self.name: str = name
        self.start: int = start
        self.end: int = end
        self.perms: str = perms
        self.kind: str = kind
        self.fileoffset = fileoffset
        self.id: int = id


class Function(object):
    """Manipulate Function object"""

    def __init__(self, name: str, offset: int, details: dict = None):
        self.name: str = name
        self.offset: int = offset
        self.id: int = -1
        # Details are architecture/SRE dependent information
        self.details: dict = details or {}


class Signature(object):
    """show signature"""

    def __init__(self, function: str, address: int, matches: list[Match]):
        self.function = function
        self.address = address
        self.matches = matches

    def __repr__(self) -> str:
        return "\n".join(m.to_string(2) for m in self.matches)


class SightHouseClient(object):

    def __init__(
        self, url: str, logger: LoggingSighthouse, verify_host: bool = True
    ) -> None:
        """Initialize SightHouseClient

        Args:
            url (str): server url of sighthouse frontend
            logger (LoggingSighthouse): specific logger to use for SRE
        """
        self._logger = logger
        self._url = urlparse(url)
        self._session = requests.Session()
        self._fileid = None
        self._verify_host = verify_host

    def get_api_url(self) -> str:
        """get base API URL

        Returns:
            str: base API URL
        """
        return "/api/v1/"

    def check_web_error(self, response: requests.Response, error_msg: str) -> None:
        """Print the error return by server

        Args:
            response (requests.Response): Server response
            error_msg (str): error message
        """
        err = f"{error_msg} with status_code {response.status_code}"
        if 400 <= response.status_code <= 500:
            err += f": {response.json().get('error')}"

        self._logger.error(err)

    def login(self, user: str, password: str) -> bool:
        """
        Log in to a Sighthouse server.

        This function connects to a Sightouse server and tries to log in to it.

        Args:
            user (str): The Sighthouse username to use.
            password (str): The password corresponding to the username.

        Returns:
            bool: Whether the operation has succeeded (True) or not (False).
        """
        err_prefix = "Login failure"
        route = self.get_api_url() + "login"
        url = self._url._replace(path=route).geturl()
        try:
            resp = self._session.post(
                url,
                json={"user": user, "password": password},
                verify=self._verify_host,
            )
            resp.raise_for_status()
        except requests.exceptions.HTTPError:
            self.check_web_error(resp, err_prefix)
        except requests.exceptions.RequestException as e:
            self._logger.error(f"{err_prefix}: {e}")
        else:
            return True

        return False

    def upload(self, filename: str, data: bytes) -> bool:
        """
        Upload a program to the Sighthouse server.

        This function sends a bytestring to a distant Sighthouse server.

        Args:
            filename (str): filename
            data (bytes): content of file

        Returns:
            bool: Whether the operation has succeeded (True) or not (False).
        """
        err_prefix = "Upload failure"
        # TODO: API search binary to check if binary exist (by hash)
        route = self.get_api_url() + "uploads"
        url = self._url._replace(path=route).geturl()
        try:
            resp = self._session.post(
                url,
                files={"filename": (filename, BytesIO(data))},
                verify=self._verify_host,
            )
        except requests.exceptions.RequestException as e:
            self._logger.error(f"{err_prefix}: {e}")
            return False

        try:
            if resp.status_code != 409:
                resp.raise_for_status()
            body = resp.json()
            self._fileid = body.get("file")
            if not isinstance(self._fileid, int):
                self._logger.error(f"Server send a wrong fileid {self._fileid}")
                return False
        except requests.exceptions.HTTPError:
            self.check_web_error(resp, err_prefix)
        except (
            requests.exceptions.RequestException,
            requests.exceptions.JSONDecodeError,
        ) as e:
            self._logger.error(f"{err_prefix}: {e}")

        return self._fileid is not None

    def get_program(self, name: str) -> int | None:
        err_prefix = "Get program failure"
        route = self.get_api_url() + "programs"
        url = self._url._replace(path=route).geturl()
        try:
            resp = self._session.get(url, verify=self._verify_host)
            resp.raise_for_status()
            body = resp.json()
            programs = body.get("programs", [])
            # Loop over all the programs and return the id of the one to match the given name
            for program in programs:
                if program["name"] == name:
                    self._programid = program.get("id")
                    return self._programid

        except requests.exceptions.HTTPError:
            self.check_web_error(resp, err_prefix)
        except requests.exceptions.RequestException as e:
            self._logger.error(f"{err_prefix}: {e}")

        return None

    def create_program(self, name: str, processor: str | None = None) -> bool:
        """
        Import an uploaded program into the Sighthouse server.

        This function starts an import of a binary file that has previously been upload to a Sighthouse server.

        Args:
            name (str): Name of program choosen by user
            processor (str | None, optional): The target architecture to use on Sighthouse's side, can be None. Defaults to None.

        Returns:
            bool: Whether the operation has succeeded (True) or not (False).
        """
        err_prefix = "Create program failure"
        route = self.get_api_url() + "programs"
        # TODO: API search program to check if program exist (by hash)
        # params = {"hash": self.get_hash_program(), "name": name}
        # if it's the case remove all sections and restart
        params = {"name": name, "file": self._fileid}
        if processor is not None:
            params.update({"language": processor})

        url = self._url._replace(path=route).geturl()
        try:
            resp = self._session.post(
                url, json={"programs": [params]}, verify=self._verify_host
            )
            resp.raise_for_status()
            if resp.status_code != 409:
                resp.raise_for_status()
            body = resp.json()
            self._programid = None
            programs = body.get("programs")
            if len(programs) == 1:
                self._programid = programs[0].get("id")
            if not isinstance(self._programid, int):
                self._logger.error(f"Server send a wrong programid {self._programid}")
                return False
        except requests.exceptions.HTTPError:
            self.check_web_error(resp, err_prefix)
        except requests.exceptions.RequestException as e:
            self._logger.error(f"{err_prefix}: {e}")
        else:
            return self._programid is not None

        return False

    def delete_program(self, program_id: int) -> None:
        err_prefix = "Delete program failure"
        route = self.get_api_url() + "programs/{}".format(program_id)
        url = self._url._replace(path=route).geturl()
        try:
            resp = self._session.delete(url, json={}, verify=self._verify_host)
            resp.raise_for_status()
            if resp.status_code != 200:
                resp.raise_for_status()
            self._programid = None
            return True
        except requests.exceptions.HTTPError:
            self.check_web_error(resp, err_prefix)
        except requests.exceptions.RequestException as e:
            self._logger.error(f"{err_prefix}: {e}")
        return False

    def list_sections(self, program_id: int) -> List[Section]:
        """List all sections inside program imported

        Args:
            program_id (int): id of program

        Returns:
            List[Section] : return the list of program section
        """
        err_prefix = "List sections failure"
        route = self.get_api_url() + "programs/{}/sections".format(program_id)
        url = self._url._replace(path=route).geturl()
        try:
            resp = self._session.get(url, verify=self._verify_host)
            body = resp.json()
            tmp_sections = body.get("sections", [])
            sections = []
            for tmp_section in tmp_sections:
                sections.append(
                    Section(
                        tmp_section.get("name"),
                        tmp_section.get("start"),
                        tmp_section.get("end"),
                        tmp_section.get("file_offset"),
                        tmp_section.get("perms"),
                        tmp_section.get("kind"),
                        tmp_section.get("id"),
                    )
                )
        except requests.exceptions.HTTPError:
            self.check_web_error(resp, err_prefix)
        except requests.exceptions.RequestException as e:
            self._logger.error(f"{err_prefix}: {e}")
        else:
            return sections

        return []

    def remove_section(self, section: Section) -> bool:
        """Remove a section inside program imported

        Args:
            section (Section): Section to remove

        Returns:
            bool: Whether the operation has succeeded (True) or not (False).
        """
        err_prefix = "Remove section failure"
        route = self.get_api_url() + "programs/{}/sections/{}".format(
            self._programid, section.id
        )
        url = self._url._replace(path=route).geturl()
        try:
            resp = self._session.delete(url, verify=self._verify_host)
            resp.raise_for_status()

        except requests.exceptions.HTTPError:
            self.check_web_error(resp, err_prefix)
        except requests.exceptions.RequestException as e:
            self._logger.error(f"{err_prefix}: {e}")
        else:
            return True

        return False

    def create_section(self, section: Section) -> bool:
        """Create a section inside program imported

        Args:
            section (Section): Section to create

        Returns:
            bool: Whether the operation has succeeded (True) or not (False).
        """
        err_prefix = "Create section failure"
        route = self.get_api_url() + "programs/{}/sections".format(self._programid)
        params = {
            "name": section.name,
            "start": section.start,
            "end": section.end,
            "file_offset": section.fileoffset,
            "perms": section.perms,
            "kind": section.kind,
        }
        url = self._url._replace(path=route).geturl()
        try:
            resp = self._session.post(
                url, json={"sections": [params]}, verify=self._verify_host
            )
            if resp.status_code != 409:
                resp.raise_for_status()
            body = resp.json()
            sections = body.get("sections")
            if len(sections) == 1:
                section.id = sections[0].get("id")
            if not isinstance(section.id, int) and section.id != -1:
                self._logger.error(f"Server send a wrong section_id {section.id}")
                return False

        except requests.exceptions.HTTPError:
            self.check_web_error(resp, err_prefix)
        except requests.exceptions.RequestException as e:
            self._logger.error(f"{err_prefix}: {e}")
        else:
            return True

        return False

    def delete_sections(self) -> bool:
        err_prefix = "Delete sections failure"
        route = self.get_api_url() + "programs/{}/sections/".format(self._programid)
        url = self._url._replace(path=route).geturl()
        try:
            resp = self._session.delete(url, json={}, verify=self._verify_host)
            resp.raise_for_status()
            if resp.status_code != 200:
                resp.raise_for_status()
            return True
        except requests.exceptions.HTTPError:
            self.check_web_error(resp, err_prefix)
        except requests.exceptions.RequestException as e:
            self._logger.error(f"{err_prefix}: {e}")
        return False

    def add_functions(self, functions: List[Function], section: Section) -> bool:
        """Create function inside program imported to guide the analysis

        Args:
            functions (List[Function]): List of function to create inside program imported
            section (Section): section where the function should be created

        Returns:
            bool: Whether the operation has succeeded (True) or not (False).
        """
        err_prefix = "Add function failure"
        route = self.get_api_url() + "programs/{}/sections/{}/functions".format(
            self._programid, section.id
        )
        params = {"functions": []}
        for function in functions:
            params["functions"].append(
                {
                    "name": function.name,
                    "offset": function.offset,
                    "details": function.details,
                }
            )

        url = self._url._replace(path=route).geturl()
        try:
            resp = self._session.post(url, json=params, verify=self._verify_host)
            resp.raise_for_status()
        except requests.exceptions.HTTPError:
            self.check_web_error(resp, err_prefix)
        except requests.exceptions.RequestException as e:
            if resp.status_code == 409:
                return True
            self._logger.error(f"{err_prefix}: {e}")
        else:
            return True
        return False

    def start_analysis(self, options: dict = None) -> bool:
        """Start the analysis on the server

        Returns:
            bool: Whether the operation has succeeded (True) or not (False).
        """
        # TODO: Add option bobross
        err_prefix = "Analyze failure"
        route = self.get_api_url() + "programs/{}/analyze".format(self._programid)
        url = self._url._replace(path=route).geturl()
        try:
            resp = self._session.post(
                url, json=options if options else {}, verify=self._verify_host
            )
            resp.raise_for_status()
        except requests.exceptions.HTTPError:
            self.check_web_error(resp, err_prefix)
        except requests.exceptions.RequestException as e:
            self._logger.error(f"{err_prefix}: {e}")
        else:
            return True

        return False

    def is_analyzing(self) -> bool:
        """Check if a program is analyzing or not

        Returns:
            bool: True if an analysis for the program is currently running, False otherwise
        """
        err_prefix = "Fail to get analysis"
        route = self.get_api_url() + "programs/{}/analyze".format(self._programid)
        url = self._url._replace(path=route).geturl()
        try:
            resp = self._session.get(url, verify=self._verify_host)
            resp.raise_for_status()
            body = resp.json()
            # If an analysis is running, we should have some details in the 'analysis' field
            analysis = body.get("analysis")
            if not isinstance(analysis, dict):
                self._logger.error(f"No Analysis")
                return False
            info = analysis.get("info")
            if not info:
                self._logger.error(f"No Analysis")
                return False
            self._logger.info(f"{info.get('status')} : {info.get('progress')}")
            if info.get("status") != "finished":
                return True
        except requests.exceptions.HTTPError:
            self.check_web_error(resp, err_prefix)
        except requests.exceptions.RequestException as e:
            self._logger.error(f"{err_prefix}: {e}")

        return False

    def analyze(self, delay: int = 30, options=None) -> bool:
        """Analyze current program

        Returns:
            bool: Whether the operation has succeeded (True) or not (False).
        """
        if not self.start_analysis(options=options):
            return False

        # Poll periodically
        while self.is_analyzing():
            # Sleep
            time.sleep(delay)

        return True

    def get_matches(self) -> list[Signature] | None:
        """
        Query signatures from a Sighthouse server.

        This functions fetches signature matches from the Sighthouse server
        it's connected to.

        Returns:
            list[Signature] | None: A list of signatures containing its 10 most significant matches on success, None if
            an error occurred.
        """
        err_prefix = "Failed to get matches"
        route = self.get_api_url() + "programs/{}".format(self._programid)
        url = self._url._replace(path=route).geturl()
        try:
            resp = self._session.get(
                url, params={"recursive": True}, verify=self._verify_host
            )
            resp.raise_for_status()
            all = resp.json()
            # self._logger.info(str(all))
        except requests.exceptions.HTTPError:
            self.check_web_error(resp, err_prefix)
            return None
        except (
            requests.exceptions.RequestException,
            requests.exceptions.JSONDecodeError,
            TypeError,
        ) as err:
            self._logger.error(f"{err_prefix}: {err}")
            return None

        # Iterate over all the signatures
        res = []
        for section in all.get("sections", []):
            for function in section.get("functions", []):
                matches = []
                for match in function.get("matches", []):
                    metadata = match.get("metadata")
                    matches.append(
                        Match(
                            metadata.get("executable"),
                            match.get("name"),
                            metadata.get("score"),
                            metadata.get("nb_match"),
                        )
                    )

                # Add signatures only when there are matches
                if len(matches) > 0:
                    matches = sorted(matches, key=lambda m: m.score)
                    res.append(
                        Signature(
                            function.get("name"),
                            section.get("start") + function.get("offset"),
                            matches,
                        )
                    )
        return res


class LoggingSighthouse(object):

    def __init__(self) -> None:
        """Initialize logging class"""
        raise NotImplementedError("LoggingSighthouse")

    def error(self, message: str):
        """Show an error message

        Args:
            message (str): The message to show
        """
        raise NotImplementedError("error")

    def warning(self, message: str):
        """Show an warning message

        Args:
            message (str): The message to show
        """
        raise NotImplementedError("warning")

    def info(self, message: str):
        """Show an info message

        Args:
            message (str): The message to show
        """
        raise NotImplementedError("info")


class SightHouseAnalysis:

    def __init__(
        self,
        username: str,
        password: str,
        url: str,
        logger: LoggingSighthouse,
        verify_host: bool = True,
        force_submission: bool = False,
        options: dict = None,
    ) -> None:
        """Initialize SightHouseAnalysis

        Args:
            username (str): username to connect to server
            password (str): password to connect to server
            url (str): URL of Sighthouse server
            client (LoggingSighthouse): A Sighthouse Logging linked to SRE
            verify_host (bool): Option to enable or disable certificate verification
        """
        self._username = username
        self._password = password
        self._logger = logger
        self._client = SightHouseClient(url, self._logger, verify_host=verify_host)
        self._force_submission = force_submission
        self.processor = self.get_current_arch()
        if self.processor is None:
            self._logger.error("architecture not found or not supported yet")
            return None

        self._options = options if options else {}

    def get_current_arch(self) -> None:
        """get current architecture and translate to ghidra one"""
        raise NotImplementedError("get_current_arch")

    def update_progress(self, message: str) -> None:
        """show an update progress

        Args:
            message (str): message to show
        """
        raise NotImplementedError("update_progress")

    def get_current_binary(self) -> bytes:
        """Retrieve the current binaries in bytes

        Returns:
            bytes: the content in bytes of the current binaries
        """
        raise NotImplementedError("get_current_binary")

    def add_tag(self, address: int, tag: str, message: str) -> None:
        """Add a tag on the SRE

        Args:
            address (int): address where put the tag
            tag (str): tag of message
            message (str): message to show
        """
        raise NotImplementedError("add_tag")

    def get_program_name(self) -> str:
        """Get program name

        Returns:
            str: the program name
        """
        raise NotImplementedError("get_program_name")

    def get_sections(self) -> List[Section]:
        """Get sections

        Returns:
            List[Section]: list sections
        """
        raise NotImplementedError("get_sections")

    def get_functions(self, section: Section) -> List[Function]:
        """get functions

        Args:
            section (Section): section

        Returns:
            List[Function]: list of function inside the section
        """
        raise NotImplementedError("get_functions")

    def get_hash_program(self) -> str:
        """get hash of program

        Returns:
            str: sha256 string
        """
        raise NotImplementedError("get_hash_program")

    def run(self) -> bool:
        """Run the complete analysis"""
        try:
            self.update_progress("Logging in to the signature server...")
            if not self._client.login(self._username, self._password):
                return False

            binary = self.get_current_binary()
            if binary == b"":
                return False

            self.update_progress("Uploading current binary...")
            # potentially check if file already upload
            program_name = self.get_program_name()
            if not self._client.upload(program_name, binary):
                return False

            self.update_progress("Importing current binary...")
            # Check for previous program
            program_id = self._client.get_program(program_name)
            do_import = True
            if program_id is None:
                # No program found, create a new one
                if not self._client.create_program(program_name, self.processor):
                    return False

            elif self._force_submission:
                self._client.delete_program(program_id)
                self._client.create_program(program_name, self.processor)
            else:
                # Program exists and force_submission is false -> use cache
                do_import = False

            if do_import:
                self.update_progress("Importing sections binary...")
                if not self._client.delete_sections():
                    return False

                sections = self.get_sections()
                for section in sections:
                    if not self._client.create_section(section):
                        return

                    if section.perms[-1] == "X":
                        functions = self.get_functions(section)
                        if not self._client.add_functions(functions, section):
                            return False

                self.update_progress("Analyzing the binary file...")
                if not self._client.analyze(options=self._options):
                    return False

            self.update_progress("Request for matches...")
            signatures = self._client.get_matches()
            if isinstance(signatures, list):
                self.update_progress(f"Got {len(signatures)} potential signatures!")
                for signature in signatures:
                    self.add_tag(
                        signature.address, "SightHouse matches", "\n" + str(signature)
                    )

                return True
        except Exception as e:
            self._logger.error(str(e))
            raise e

        return False
