"""Standalone command-line analysis with two modes:

- **Auto** (default): upload the binary, create it as an "auto" program, run
  Ghidra's native importer server-side to detect the language + memory layout,
  then analyze and print the matches.

- **Manual / baremetal**: auto-detection can't help a raw firmware image (no
  recognizable format), so pass an explicit Ghidra `language` (and optional load
  address). The whole file is mapped as one RWX section at that address and
  Ghidra's auto-analysis discovers the functions.
"""

import os
import sys
import time
from typing import Optional

from sighthouse.client.SightHouseClient import (
    SightHouseClient,
    LoggingSighthouse,
    Section,
    AnalysisOptions,
)


class ConsoleLogging(LoggingSighthouse):
    """Minimal stdout logger for the standalone client."""

    def __init__(self) -> None:
        pass

    def error(self, message: str) -> None:
        print(f"[!] {message}", file=sys.stderr)

    def warning(self, message: str) -> None:
        print(f"[~] {message}", file=sys.stderr)

    def info(self, message: str) -> None:
        print(f"[+] {message}", file=sys.stderr)


class SightHouseClientStandalone:
    """Analyze a binary from the command line, via auto-detection or a manual layout."""

    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        logger: Optional[LoggingSighthouse] = None,
        verify_host: bool = True,
        force_submission: bool = False,
        options: Optional[AnalysisOptions] = None,
        poll_interval: int = 5,
    ) -> None:
        """
        Args:
            url (str): URL of the SightHouse frontend server.
            username (str): Username to log in with.
            password (str): Password to log in with.
            logger (LoggingSighthouse | None): Logger; defaults to stdout.
            verify_host (bool): Verify the server's TLS certificate.
            force_submission (bool): Replace a cached program of the same name.
            options (AnalysisOptions | None): Analysis options; defaults to
                auto_analysis so Ghidra performs function discovery.
            poll_interval (int): Seconds between status polls.
        """
        self._username = username
        self._password = password
        self._logger = logger or ConsoleLogging()
        self._client = SightHouseClient(url, self._logger, verify_host=verify_host)
        self._force = force_submission
        self._options = options or AnalysisOptions(auto_analysis=True)
        self._poll_interval = poll_interval

    def _wait_until_idle(self) -> None:
        """Block until the current server job (autoload or analysis) finishes."""
        while self._client.is_analyzing():
            time.sleep(self._poll_interval)

    def run(
        self, filename: str, language: Optional[str] = None, load_addr: int = 0
    ) -> bool:
        """Analyze `filename` and print any matches.

        Args:
            filename (str): Path to the binary to analyze.
            language (str | None): When None, the server auto-detects the format,
                language and layout (Auto mode). When set, use the manual/baremetal
                path: map the whole file as one RWX section at `load_addr` with this
                Ghidra language (e.g. "ARM:LE:32:v8").
            load_addr (int): Base address for the manual mapping (ignored in Auto mode).

        Returns:
            bool: True on success, False otherwise.
        """
        try:
            with open(filename, "rb") as fp:
                binary = fp.read()
        except OSError as e:
            self._logger.error(f"Cannot read {filename}: {e}")
            return False

        name = os.path.basename(filename)

        self._logger.info("Logging in to the signature server...")
        if not self._client.login(self._username, self._password):
            return False

        self._logger.info(f"Uploading {name}...")
        if not self._client.upload(name, binary):
            return False

        # "auto" is the sentinel that triggers server-side detection; a real
        # language means we supply the (baremetal) layout ourselves.
        program_language = language or "auto"
        program_id = self._client.get_program(name)
        do_import = True
        if self._force and program_id is not None:
            self._client.delete_program(program_id)
            program_id = None
        if program_id is None:
            if not self._client.create_program(name, program_language):
                return False
        else:
            self._logger.info("Program already exists, using cache.")
            do_import = False

        if do_import:
            if language is None:
                self._logger.info("Auto-detecting language and layout...")
                if not self._client.autoload():
                    return False
                self._wait_until_idle()
            else:
                self._logger.info(f"Mapping raw layout for {language}...")
                if not self._client.delete_sections():
                    return False
                section = Section(
                    name="raw",
                    start=load_addr,
                    end=load_addr + len(binary),
                    fileoffset=0,
                    perms="RWX",
                    kind="",
                )
                if not self._client.create_section(section):
                    return False

            self._logger.info("Analyzing the binary file...")
            if not self._client.start_analysis(options=self._options):
                return False
            self._wait_until_idle()

        self._logger.info("Request for matches...")
        signatures = self._client.get_matches()
        if not isinstance(signatures, list):
            return False

        self._logger.info(f"Got {len(signatures)} potential signature(s)!")
        for signature in signatures:
            print(str(signature))
        return True
