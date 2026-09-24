"""Binary Analyzer utils"""

from tempfile import TemporaryDirectory
from typing import List, Optional, Dict
from xml.etree.ElementTree import ElementTree, Element, parse
from pathlib import Path
from os import environ

from sighthouse.core.utils import run_process  # type: ignore[import-untyped]
from sighthouse.core.utils.database import Database


def clean_install(ghidradir: Path, jars: Optional[List[str]] = None) -> None:
    """Cleanup ghidra directory with the file we have installed"""
    # Check if the GHIDRA_DIR path exists
    if not ghidradir.exists() or not ghidradir.is_dir():
        raise FileNotFoundError(f"The path specified in '{ghidradir}' does not exist")

    # Remove all jar files
    jars = jars or []
    for jar in jars:
        jarpath = ghidradir / "Ghidra" / "patch" / jar
        if jarpath.exists():
            jarpath.unlink()


def build_script(ghidradir: Path, script_dir: Path) -> None:
    """Compile Ghidra scripts to .class files to speed up loading process
    and avoid random OSGi errors

    Reversed from https://github.com/NationalSecurityAgency/ghidra/blob/
                  7dd38f2d95597c618af3d921f950fd6674805dd2/Ghidra/Features/
                  Base/src/main/java/ghidra/app/plugin/core/osgi/GhidraSourceBundle.java#L1019
    """
    # Check if the GHIDRA_DIR path exists
    if not ghidradir.exists() or not ghidradir.is_dir():
        raise FileNotFoundError(f"The path specified in '{ghidradir}' does not exist")

    source_files = script_dir.rglob("*.java")
    source_path = script_dir

    # Find all jar of Ghidra and create the classpath argument
    jars = ":".join(map(str, ghidradir.rglob("**/*.jar")))
    classpath = f".:{jars}"

    # Iterate over the all the scripts to compile
    for source_file in source_files:
        javac_command = [
            "javac",
            "-g",
            "-d",
            str(script_dir),
            "-sourcepath",
            str(source_path),
            "-cp",
            classpath,
            "-proc:none",
            str(source_file),
        ]

        returncode, stdout, stderr = run_process(javac_command)
        if returncode != 0:
            raise Exception(
                f"Failed to compile '{source_file}': {stdout.decode()}\n{stderr.decode()}"
            )


def get_ghidra_languages(ghidradir: Path) -> List[str]:
    """Return the list of Ghidra supported languages"""
    # Check if the GHIDRA_DIR path exists
    if not ghidradir.exists() or not ghidradir.is_dir():
        raise FileNotFoundError(f"The path specified in '{ghidradir}' does not exist")

    # Processors directory holds the list of available processors
    processors: Path = ghidradir / "Ghidra" / "Processors/"
    if not processors.exists() or not processors.is_dir():
        raise FileNotFoundError(f"The path specified in '{processors}' does not exist")

    # Iterate over all the processors
    languages_id: List[str] = []
    for processor in processors.iterdir():
        languages: Path = processor / "data" / "languages"
        if languages.exists() and languages.is_dir():
            # Iterate over all the languages definition
            for ldef in languages.rglob("*.ldefs"):
                # Parse XML language definition
                root: ElementTree[Element[str]] = parse(str(ldef))
                for lang in root.getroot():
                    languages_id.append(lang.attrib["id"])

    return languages_id


def create_bsim_database(
    ghidradir: Path,
    bsim_urls: list[str],
    config_template: str = "medium_nosize",
    username: str = "bsim_user",
    capture_output: bool = False,
) -> bool:
    """Create an empty BSIM database

    Enumerated Options:
        <config_template> - large_32 | medium_32 | medium_64 | medium_cpool | medium_nosize
    """

    # Override username java properties so bsim client
    # won't complain when connecting
    my_env: Dict[str, str] = environ.copy()
    my_env["_JAVA_OPTIONS"] = f"-Duser.name={username}"
    for bsim_url in bsim_urls:
        args: List[str] = [
            str(ghidradir / "support" / "bsim"),
            "createdatabase",
            bsim_url,
            config_template,
        ]
        # Run process without a timeout
        if run_process(args, env=my_env, capture_output=capture_output)[0] != 0:
            return False

    return True


def create_sighthouse_database(
    ghidradir: Path,
    urls: list[str],
    config_template: str = "medium_nosize",
    username: str = "bsim_user",
    capture_output: bool = False,
) -> bool:
    """Create an empty SightHouse database (built on top of the BSIM one).

    Warning: The new database is NOT guaranteed to be compatible with the ghidra BSIM client.

    Enumerated Options:
        <config_template> - large_32 | medium_32 | medium_64 | medium_cpool | medium_nosize
    """
    for url in urls:
        if not url.startswith("postgres"):
            raise ValueError(
                "Unsupported database format. Only PostgreSQL is supported"
            )

    if not create_bsim_database(
        ghidradir,
        urls,
        config_template=config_template,
        username=username,
        capture_output=capture_output,
    ):
        # Failed to create the bsim database, abort
        return False

    # Lazy import
    import psycopg

    success = True
    # Add our custom tables on top of BSIM ones.
    for url in urls:
        handle = Database(url)
        try:
            handle.execute("""
                CREATE TABLE IF NOT EXISTS project (
                    id           BIGSERIAL PRIMARY KEY,
                    origin       TEXT,
                    name         TEXT,
                    version      TEXT,
                    ingest_date  TIMESTAMPTZ DEFAULT now(),
                    UNIQUE (origin, name, version)
                );
            """)

            handle.execute("""
                CREATE TABLE IF NOT EXISTS program (
                    id            BIGSERIAL PRIMARY KEY,
                    md5           TEXT UNIQUE,
                    name          TEXT,
                    id_arch       INTEGER REFERENCES archtable(id)
                );
            """)

            handle.execute("""
                CREATE TABLE IF NOT EXISTS project_program (
                    id_project  BIGINT REFERENCES project(id) ON DELETE CASCADE,
                    id_program  BIGINT REFERENCES program(id) ON DELETE CASCADE,
                    PRIMARY KEY (id_project, id_program)
                );
            """)

            handle.execute("""
                CREATE TABLE IF NOT EXISTS fidb (
                    id                            BIGSERIAL PRIMARY KEY,
                    full_hash                     BIGINT,
                    specific_hash                 BIGINT,
                    specific_hash_additional_size SMALLINT,
                    code_unit_size                SMALLINT,
                    UNIQUE (full_hash, specific_hash, specific_hash_additional_size, code_unit_size)
                );
            """)
            handle.execute(
                "CREATE INDEX IF NOT EXISTS fidb_full_hash_idx ON fidb (full_hash);"
            )

            handle.execute("""
                CREATE TABLE IF NOT EXISTS functions (
                    id            BIGSERIAL PRIMARY KEY,
                    id_program    BIGINT REFERENCES program(id) ON DELETE CASCADE,
                    name          TEXT,
                    id_vector     BIGINT REFERENCES vectable(id),
                    id_fidb       BIGINT REFERENCES fidb(id)
                );
            """)
            handle.execute(
                "CREATE INDEX IF NOT EXISTS functions_id_vector_idx ON functions (id_vector);"
            )
            handle.execute(
                "CREATE INDEX IF NOT EXISTS functions_id_fidb_idx   ON functions (id_fidb);"
            )
        except psycopg.Error:
            # Failed to create one or more tables, fail
            success = False
        finally:
            handle.close()

    return success


def run_ghidra_script(
    ghidradir: Path,
    script: Path,
    args: List[str],
    env: Optional[Dict[str, str]] = None,
    capture_output: bool = False,
    logfile: Optional[Path] = None,
) -> tuple[int, bytes, bytes]:
    """Run a given Ghidra script"""

    # Check if the GHIDRA_DIR path exists
    if not ghidradir.exists() or not ghidradir.is_dir():
        raise FileNotFoundError(f"The path specified in '{ghidradir}' does not exist")

    if not script.exists() or not script.is_file():
        raise FileNotFoundError(f"The path specified in '{script}' does not exist")

    if script.suffix not in {".java", ".class"}:
        raise Exception(
            f"Invalid script file. Expecting a java or class file but got '{script.suffix}'"
        )

    script_path: Path = script.parent
    compiled_script: Path = script.with_suffix(".class")
    # Compile script if not already done
    if not compiled_script.exists():
        build_script(ghidradir, script_path)

    # Project is stored in temp directory
    with TemporaryDirectory() as tmpdirname:
        process_args: List[str] = [
            str(ghidradir / "support" / "analyzeHeadless"),
            tmpdirname,
            "tmpproj",
        ]
        # Log file need to be place here if defined
        if logfile is not None:
            process_args += ["-log", str(logfile.absolute())]

        process_args += [
            "-scriptPath",
            str(script_path),
            "-preScript",
            compiled_script.name,
        ]
        process_args += args

        # Run process without a timeout
        return run_process(process_args, env=env, capture_output=capture_output)


def get_ghidra_version(ghidradir: Path) -> Optional[str]:
    """Return the version of a given ghidra installation or None on failure"""
    # Check if the GHIDRA_DIR path exists
    if not ghidradir.exists() or not ghidradir.is_dir():
        raise FileNotFoundError(f"The path specified in '{ghidradir}' does not exist")

    # Look for the application.properties file
    application: Path = ghidradir / "Ghidra" / "application.properties"
    if not application.exists() or not application.is_file():
        raise FileNotFoundError("Fail to find application.properties")

    # Parse the application.version entry
    with open(application, "r", encoding="utf-8") as fp:
        for line in fp:
            if line and line.startswith("application.version="):
                return line[20:].strip()

    # Fail to find the version
    return None
