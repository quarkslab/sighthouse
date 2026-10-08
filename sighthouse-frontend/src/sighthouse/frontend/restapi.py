"""Public REST API for SightHouse clients"""

from typing import List, Optional, Tuple, cast
from traceback import format_exception
from secrets import token_hex
from functools import wraps
from logging import Logger
from pathlib import Path
import threading
import signal
import time
import json
import os

from celery import Celery
from flask import (
    Flask,
    request,
    jsonify,
    Response,
    send_from_directory,
    abort,
    redirect,
)
from flask_login import (
    login_user,
    login_required,
    logout_user,
    current_user,
    LoginManager,
)
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

from sighthouse.version import __version__
from sighthouse.frontend.database import FrontendDatabase, RestError
from sighthouse.frontend.model import (
    User,
    File,
    Program,
    Section,
    Function,
    Analysis,
    AnalysisOptions,
    FrontendConfig,
)
from sighthouse.core.utils.analyzer import get_ghidra_languages
from sighthouse.core.utils.api import ServerThread
from sighthouse.core.utils import parse_uri


def admin_required(f):
    """Restrict a route to logged-in administrators"""

    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if not get_current_user().is_admin():
            abort(403)
        return f(*args, **kwargs)

    return wrapper


def get_current_user() -> User:
    """Wrapper function so mypy stop yelling at me"""
    # Cast LocalProxy to user
    return cast(User, current_user)


def build_analysis_databases(urls: List[str]) -> List[dict]:
    """Turn a list of BSIM/FIDB URIs into the analyzer's ``databases`` entries."""
    databases = []
    for e in (parse_uri(u) for u in urls):
        url = (
            f"{e['type']}://{e['host']}:{e['port']}/{e['dbname']}"
            if "dbname" in e
            else str(e["database"])
        )
        databases.append(
            {"url": url, "user": e.get("user", ""), "password": e.get("password") or ""}
        )
    return databases


class FrontendRestAPI(ServerThread):
    """REST API server for SightHouse public API"""

    def __init__(
        self,
        database: FrontendDatabase,
        logger: Logger,
    ):
        self.__config = database.get_config()
        self.__database: FrontendDatabase = database
        self.__logger = logger
        self.__app = Flask(__name__, static_url_path="", static_folder="web")
        self.__app.secret_key = token_hex(32)
        self.__register_routes()
        self.__register_error_handlers()
        self.__login_manager = LoginManager()
        self.__login_manager.init_app(self.__app)
        self.__register_user_stuff()
        self.__languages_cache: Optional[List[str]] = (
            None  # lazily-filled Ghidra language list
        )
        self.__celery_app = Celery(
            "", broker=self.__config.worker_url, backend=self.__config.worker_url
        )
        self.__static_dir = Path(self.__app.root_path) / "web"

        super().__init__(self.__app, self.__config.host, self.__config.port)

    def __register_user_stuff(self) -> None:
        """Register login manager handler to flask"""

        @self.__login_manager.user_loader
        def load_user(user_id: int) -> Optional[User]:
            return self.__database.get_user(user_id)

    def __register_error_handlers(self) -> None:
        """Register the error handler"""

        @self.__app.errorhandler(Exception)
        def handle_exception(e):
            """Handle an error and return the appropriate error code, can be surcharged

            Args:
                exception (Exception): The exception to handle
            Returns:
                tuple[Response, int]: A tuple containing the HTTP error code and
                                   the data to send to the remote peer
            """
            if isinstance(e, HTTPException):
                # Avoid logging 401/404 errors, for example when the favicon is not found
                self.__logger.debug("".join(format_exception(e)))
                return jsonify({"error": e.description}), e.code
            # Unexpected server error, keep the full traceback for debugging
            self.__logger.error("".join(format_exception(e)))
            return jsonify({"error": str(e)}), 500

    def __register_routes(self) -> None:

        def config_response() -> dict:
            """Body shared by GET and PUT /api/v1/config."""
            return {"version": __version__, **self.__config.to_dict()}

        @self.__app.route("/", methods=["GET"])
        def index():
            """Serve the analysis app, or the setup wizard on a fresh install"""
            if not self.__database.database_is_setup():
                return redirect("/setup")
            return send_from_directory(self.__static_dir, "index.html")

        @self.__app.route("/setup", methods=["GET"])
        def setup_page():
            """Serve the first-run wizard, only while the app is unconfigured."""
            if self.__database.database_is_setup():
                return redirect("/")
            return send_from_directory(self.__static_dir, "setup.html")

        @self.__app.route("/admin", methods=["GET"])
        @admin_required
        def admin_page():
            """Serve the admin page"""
            return send_from_directory(self.__static_dir, "admin.html")

        @self.__app.route("/api/v1/setup", methods=["GET"])
        def need_setup() -> Tuple[Response, int]:
            """
            Setup check endpoint

            Returns:
                200: successful operation
                     ```
                     {
                         "need_setup": <True / False>
                     }
                     ```
            """
            return jsonify({"need_setup": not self.__database.database_is_setup()}), 200

        @self.__app.route("/api/v1/setup", methods=["POST"])
        def do_setup() -> Tuple[Response, int]:
            """
            Perform setup endpoint

            Params:
                user (User): First user to create as admin

            Returns:
                200: successful operation
                     ```
                     {
                         "success": "Setup successful"
                     }
                     ```

                400: Invalid user/password value
                    ```
                    {
                       "error": "Missing user or password"
                    }
                    ```

                500: Internal server error
                    ```
                    {
                       "error": "Fail to add user to database"
                    }
                    ```
            """
            if self.__database.database_is_setup():
                return jsonify({"error": "Frontend is already setup"}), 400

            data = request.get_json()
            if not data or not data.get("user") or not data.get("password"):
                return jsonify({"error": "Missing user or password"}), 400

            user = self.__database.add_user(
                User.create(data["user"], data["password"], "admin")
            )
            if user is None:
                return jsonify({"error": "Fail to add user to database"}), 500

            self.__database.mark_setup_done()
            return jsonify({"success": "Setup successful"}), 200

        @self.__app.route("/api/v1/users", methods=["GET"])
        @admin_required
        def get_users():
            """
            Return the list of users without their password hash

            Returns:
                200: Successful operation
                    ```
                    {
                       "users": [{
                            "id": 1234,
                            "name": "test",
                            "role": "user"
                        }, {...}]
                    }
                    ```
            """
            users = self.__database.list_users()
            return jsonify({"users": [u.to_public_dict() for u in users]}), 200

        @self.__app.route("/api/v1/users", methods=["POST"])
        @admin_required
        def add_user():
            """
            Add a new user in the database

            Returns:
                201: Successful operation
                    ```
                    {
                       "success": "User was added"
                    }
                    ```

                400: Invalid user/password value
                    ```
                    {
                       "error": "Missing user or password"
                    }
                    ```

                500: Internal server error
                    ```
                    {
                       "error": "Fail to add user to database"
                    }
                    ```
            """

            data = request.get_json()
            if (
                not data
                or not data.get("user")
                or not data.get("password")
                or not data.get("role") in User.VALID_ROLES
            ):
                return jsonify({"error": "Missing user, password or role"}), 400

            user = self.__database.add_user(
                User.create(data["user"], data["password"], data["role"])
            )
            if user is None:
                return jsonify({"error": "Fail to add user to database"}), 500

            return jsonify({"success": "User was added"}), 201

        @self.__app.route("/api/v1/users", methods=["DELETE"])
        @admin_required
        def remove_user():
            """
            Delete a user, revoke the session if an administrator deletes itself

            Returns:
                200: Successful operation
                    ```
                    {
                       "success": "User was deleted"
                    }
                    ```

                400: Invalid parameters or last administrator
                    ```
                    {
                       "error": "Missing user"
                    }
                    ```

                500: Internal server error
                    ```
                    {
                       "error": "Fail to delete user to database"
                    }
                    ```
            """

            data = request.get_json()
            if not data or not data.get("user"):
                return jsonify({"error": "Missing user"}), 400

            user = self.__database.get_user_by_name(data["user"])
            if user is None:
                # Deleting a missing user is a no-op
                return jsonify({"success": "User was deleted"}), 200

            if user.is_admin() and self.__database.count_admins() == 1:
                return jsonify({"error": "Cannot delete the last administrator"}), 400

            if not self.__database.delete_user(user):
                return jsonify({"error": "Fail to delete user to database"}), 500

            if user.is_admin() and user.id == get_current_user().id:
                logout_user()

            return jsonify({"success": "User was deleted"}), 200

        @self.__app.route("/api/v1/users", methods=["PUT"])
        @admin_required
        def update_user():
            """
            Update a user role or password in the database

            Returns:
                200: Successful operation
                    ```
                    {
                       "success": "User was updated"
                    }
                    ```

                400: Invalid user/password value
                    ```
                    {
                       "error": "Missing user/role/password"
                    }
                    ```

                500: Internal server error
                    ```
                    {
                       "error": "Fail to update user in database"
                    }
                    ```
            """
            data = request.get_json()
            if not data or not data.get("user"):
                return jsonify({"error": "Missing user"}), 400

            if not data.get("password") and not data.get("role"):
                return jsonify({"error": "Missing password/role"}), 400

            if data.get("role") and data["role"] not in User.VALID_ROLES:
                return jsonify({"error": "Invalid role"}), 400

            user = self.__database.get_user_by_name(data["user"])
            if user is None:
                return jsonify({"error": "User does not exists"}), 400

            was_admin = user.is_admin()
            if (
                was_admin
                and data.get("role") == "user"
                and self.__database.count_admins() == 1
            ):
                return (
                    jsonify(
                        {"error": "Cannot remove role from the last administrator"}
                    ),
                    400,
                )

            if data.get("role"):
                user.role = data["role"]
            if data.get("password"):
                user.set_password(data["password"])

            if not self.__database.update_user(user):
                return jsonify({"error": "Fail to update user in database"}), 500

            # Revoke the session of an administrator demoting itself
            if was_admin and not user.is_admin() and user.id == get_current_user().id:
                logout_user()

            return jsonify({"success": "User was updated"}), 200

        @self.__app.route("/api/v1/config", methods=["GET"])
        @admin_required
        def get_server_config():
            """
            Get the server configuration

            Returns:
                200: Successful operation
                    ```
                    {
                       "configuration": {
                            "version": "1.0.0",
                            "host": "0.0.0.0",
                            ...
                       }
                    }
                    ```
            """
            return jsonify({"configuration": config_response()}), 200

        @self.__app.route("/api/v1/config", methods=["PUT"])
        @admin_required
        def update_config():
            """
            Update (partially) the frontend configuration

            Returns:
                200: Successful operation
                    ```
                    {
                       "configuration": {...},
                       "restart_required": ["port", ...]
                    }
                    ```

                400: Invalid parameters
                    ```
                    {
                       "error": "port must be between 1024 and 65535"
                    }
                    ```
            """
            data = request.get_json() or {}
            try:
                merged = self.__config.to_dict()
                for key, value in data.items():
                    if key in ("bsim_config", "fidb_config") and isinstance(
                        value, dict
                    ):
                        merged[key].update(value)
                    else:
                        merged[key] = value
                # database_uri is not client-settable
                merged["database_uri"] = self.__config.database_uri

                config = FrontendConfig.from_dict(merged)
            except ValueError as e:
                return jsonify({"error": str(e)}), 400

            # BSIM/FIDB settings apply on the next analysis, others need a restart
            restart_required = config.restart_required(self.__config)
            self.__database.set_config(config)
            self.__config = config

            return (
                jsonify(
                    {
                        "configuration": config_response(),
                        "restart_required": restart_required,
                    }
                ),
                200,
            )

        @self.__app.route("/api/v1/restart", methods=["POST"])
        @admin_required
        def restart_server() -> Tuple[Response, int]:
            """
            Restart the server to apply restart-only configuration changes.
            Requires the SIGHUP handler installed by `frontend start`.

            Returns:
                200: the server is restarting
                    ```
                    {
                        "success": "Server is restarting"
                    }
                    ```

                501: restart is not supported in this environment
                    ```
                    {
                        "error": "Restart is not supported in this environment"
                    }
                    ```
            """
            data = request.get_json() or {}
            if self.__database.analysis_count() > 0 and (
                "force" not in data or data.get("force", "").lower() != "true"
            ):
                return (
                    jsonify(
                        {"error": "Server has running analyses. Need to force restart"}
                    ),
                    400,
                )

            if not hasattr(signal, "SIGHUP") or signal.getsignal(signal.SIGHUP) in (
                signal.SIG_DFL,
                signal.SIG_IGN,
                None,
            ):
                return (
                    jsonify({"error": "Restart is not supported in this environment"}),
                    501,
                )

            def _trigger() -> None:
                # Let the response flush first
                time.sleep(0.5)
                os.kill(os.getpid(), signal.SIGHUP)

            threading.Thread(target=_trigger, daemon=True).start()
            return jsonify({"success": "Server is restarting"}), 200

        @self.__app.route("/api/v1/ping", methods=["GET"])
        def ping() -> Tuple[Response, int]:
            """
            Health check endpoint

            Returns:
                200: successful operation
                     ```
                     {
                         "success": "Pong !"
                     }
                     ```
            """
            return jsonify({"success": "Pong !"}), 200

        @self.__app.route("/api/v1/login", methods=["POST"])
        def login() -> Tuple[Response, int]:
            """
            Login endpoint

            Params:
                user (str): The username for the login
                password (str): The password for the login

            Returns:
                200: Successful operation
                    ```
                    {
                       "success": "Login successful"
                    }
                    ```

                400: Invalid user/password value
                    ```
                    {
                       "error": "Missing user or password"
                    }
                    ```

                401: Invalid credentials
                    ```
                    {
                       "error": "Invalid credentials"
                    }
                    ```
            """
            data = request.get_json()
            if not data or not data.get("user") or not data.get("password"):
                return jsonify({"error": "Missing user or password"}), 400

            user = self.__database.get_user_by_name(data["user"])
            if not user or not user.check_password(data["password"]):
                return jsonify({"error": "Invalid credentials"}), 401

            login_user(user, remember=False)

            return jsonify({"success": "Login successful"}), 200

        @self.__app.route("/api/v1/logout", methods=["POST"])
        @login_required
        def logout() -> Tuple[Response, int]:
            """
            Logout endpoint

            Returns:
                200: Successful operation
                    ```
                    {
                       "success": "Login successful"
                    }
                    ```
            """
            logout_user()
            return jsonify({"success": "Logout successful"}), 200

        @self.__app.route("/api/v1/me", methods=["GET"])
        @login_required
        def get_user_info() -> Tuple[Response, int]:
            """
            Get current user informations endpoint

            Returns:
                200: Successful operation
                    ```
                    {
                       "user": {
                            "id": 1234,
                            "name": "test",
                            "role": "user"
                       }
                    }
                    ```
            """
            return jsonify({"user": get_current_user().to_public_dict()}), 200

        @self.__app.route("/api/v1/languages", methods=["GET"])
        def list_languages() -> Tuple[Response, int]:
            """
            List languages supported by the analyzer

            Returns:
                200: Successful operation
                    ```
                    {
                       "languages": ["ARM", ...]
                    }
                    ```
            """
            return jsonify({"languages": self.__languages()}), 200

        @self.__app.route("/api/v1/uploads", methods=["POST"])
        @login_required
        def upload_file() -> Tuple[Response, int]:
            """
            Endpoint for upload files into the server

            Params:
                filename (str, bytes): Multipart encoded file to upload

            Returns:
                200: Successful operation
                    ```
                    {
                       "success": "File uploaded",
                       "file: 1234
                    }
                    ```

                400: Invalid parameters
                    ```
                    {
                       "error": "Missing 'filename' field in upload data"
                    }
                    ```

                500: Internal server error
                    ```
                    {
                       "error": "Fail to add file to database"
                    }
                    ```
            """

            # check presence of file in request
            if "filename" not in request.files:
                return (
                    jsonify({"error": "Missing 'filename' field in upload data"}),
                    400,
                )

            file_storage = request.files["filename"]
            if (
                file_storage is None
                or file_storage.filename is None
                or file_storage.filename == ""
            ):
                return jsonify({"error": "Empty filename"}), 400

            # get content file
            content = file_storage.read()

            # clean filename
            filename = secure_filename(file_storage.filename)

            # Add in database
            new_file = File(
                id=File.INVALID_ID,
                name=filename,
                content=content,
                user=get_current_user().id,
            )
            try:
                new_file = self.__database.add_file_user(new_file)
                if not new_file:
                    return jsonify({"error": "Fail to add file to database"}), 500
            except RestError as e:
                return jsonify(e.error), e.code or 500

            return jsonify({"success": "File uploaded", "file": new_file.id}), 201

        @self.__app.route("/api/v1/uploads", methods=["GET"])
        @login_required
        def list_files() -> Tuple[Response, int]:
            """
            List the files uploaded on the server

            Returns:
                200: Successful operation
                    ```
                    {
                       "files: [{
                            "id": 1234,
                            "name": "ls.bin",
                            "user": 5678,
                            "hash": "9fed8..."
                        }, {...}]
                    }
                    ```
            """
            files = self.__database.get_user_file(get_current_user().id)
            return jsonify({"files": [f.to_dict() for f in files]}), 200

        @self.__app.route("/api/v1/uploads/<string:hash>", methods=["DELETE"])
        @login_required
        def delete_file(hash) -> Tuple[Response, int]:
            """
            Endpoint for deleting files from the upload server

            Params:
                hash (str): hash of the file to delete

            Returns:
                200: Successful operation
                    ```
                    {
                       "success": "File deleted"
                    }
                    ```

                404: Invalid parameters
                    ```
                    {
                       "error": "The given file does not exists"
                    }
                    ```

                500: Internal server error
                    ```
                    {
                       "error": "Fail to delete file from database"
                    }
                    ```
            """
            file = self.__database.get_file_by_hash(hash, user_id=get_current_user().id)
            if not file:
                return jsonify({"error": "The given file does not exists"}), 404
            try:
                if not self.__database.delete_file(file):
                    return jsonify({"error": "Fail to delete file from database"}), 500
            except RestError as e:
                return jsonify({"error": e.error}), e.code or 500

            return jsonify({"success": "File deleted"}), 200

        @self.__app.route("/api/v1/programs", methods=["POST"])
        @login_required
        def create_program() -> Tuple[Response, int]:
            """
            Endpoint for creating new programs in the system.

            Params:
                programs (list[program]): A list of JSON program to create

            Returns:
                201: Successful operation
                    ```
                    {
                       "programs": [<list of created program>]
                    }
                    ```

                400: Bad request for missing or invalid parameters
                    ```
                    {
                       "error": "Invalid program data in program list"
                    }
                    ```
            """

            data = request.get_json()
            if not isinstance(data, dict) or not isinstance(data.get("programs"), list):
                return (
                    jsonify({"error": "Bad parameters, missing 'programs' list"}),
                    400,
                )

            programs_list = []
            for program_data in data["programs"]:
                if not isinstance(program_data, dict):
                    return (
                        jsonify({"error": "Invalid program data in program list"}),
                        400,
                    )

                # Validate file
                file_id = program_data.get("file", File.INVALID_ID)
                file = self.__database.get_file_user(
                    file_id, user_id=get_current_user().id
                )
                if not file:
                    return jsonify({"error": "File is invalid"}), 400

                # Validate language from Ghidra list and 'auto' reserved keyword
                language = program_data.get("language")
                if not self.__is_valid_language(language, allow_auto=True):
                    return jsonify({"error": "Language is invalid"}), 400

                # Attach user ID
                program_data["user"] = get_current_user().id

                try:
                    program_obj = Program.from_dict(program_data)
                    if program_obj is None:
                        return (
                            jsonify({"error": "Invalid program data in program list"}),
                            400,
                        )

                except ValueError as e:
                    return jsonify({"error": str(e)}), 400

                programs_list.append(program_obj)

            # Add programs to DB
            for program in programs_list:
                self.__database.add_program(program)

            return jsonify({"programs": [p.to_dict() for p in programs_list]}), 201

        @self.__app.route("/api/v1/programs", methods=["GET"])
        @login_required
        def get_programs() -> Tuple[Response, int]:
            """
            Endpoint for retrieving all programs associated with the current user.

            Returns:
                200: Successfully retrieved user programs
                    ```
                    {
                       "programs": [{"id": 1234, "name": "ls.bin", ...}, {...}]
                    }
                    ```
            """
            programs = self.__database.list_user_programs(get_current_user().id)
            return jsonify({"programs": [p.to_dict() for p in programs]}), 200

        @self.__app.route("/api/v1/programs/<int:program_id>", methods=["GET"])
        @login_required
        def get_program(program_id) -> Tuple[Response, int]:
            """
            Endpoint for retrieving a specific program by its ID.

            Params:
                program_id (int): ID of the requested program
                recursive (str): A string corresponding to a boolean (either 'true' or 'false')
                                 that tell the server to return the program sub elements such
                                 as functions.

            Returns:
                200: Successfully retrieved the program
                    ```
                    {
                        "id": 1234,
                        "name": "ls.bin",
                        "user": 4567,
                        "language": "x86_64",
                        "file": 2468,
                    }
                    ```

                404: Program not found
                    ```
                    {
                       "error": "Program not found"
                    }
                    ```
            """
            program = self.__database.get_program(
                program_id, user_id=get_current_user().id
            )

            if program is None:
                return jsonify({"error": "Program not found"}), 404

            recursive = request.args.get("recursive", "").lower() == "true"

            if recursive:
                sections_data = []
                sections = self.__database.list_program_sections(program.id)

                for section in sections:
                    functions_data = []
                    functions = self.__database.list_section_functions(section.id)

                    for function in functions:
                        function_data = function.to_dict()
                        matches = self.__database.list_function_matches(function.id)
                        function_data["matches"] = [m.to_dict() for m in matches]
                        functions_data.append(function_data)

                    section_data = section.to_dict()
                    section_data["functions"] = functions_data
                    sections_data.append(section_data)

                program_data = program.to_dict()
                program_data["sections"] = sections_data
                return jsonify(program_data), 200

            return jsonify(program.to_dict()), 200

        @self.__app.route("/api/v1/programs/<int:program_id>", methods=["DELETE"])
        @login_required
        def delete_program(program_id) -> Tuple[Response, int]:
            """
            Endpoint for deleting a specific program by its ID.

            Params:
                program_id (int): ID of the program to delete

            Returns:
                200: Successful operation
                    ```
                    {
                       "success": "Program deleted"
                    }
                    ```

                403: Forbidden if the program is under analysis
                    ```
                    {
                       "error": "Cannot modify program while it is being analyzed"
                    }
                    ```

                404: Program not found
                    ```
                    {
                       "error": "Program not found"
                    }
                    ```

                500: Internal server error if deletion fails
                    ```
                    {
                       "error": "Fail to delete program"
                    }
                    ```
            """

            # Step 1: Assert program is not being analyzed
            if self.__is_program_under_analysis(program_id):
                return (
                    jsonify(
                        {"error": "Cannot modify program while it is being analyzed"}
                    ),
                    403,
                )
            program = self.__database.get_program(
                program_id, user_id=get_current_user().id
            )
            if program is None:
                return jsonify({"error": "Program not found"}), 404

            success = self.__database.delete_program(program)
            if not success:
                return jsonify({"error": "Fail to delete program"}), 500

            return jsonify({"success": "Program deleted"}), 200

        @self.__app.route("/api/v1/programs/<int:program_id>/analyze", methods=["GET"])
        @login_required
        def get_analysis(program_id) -> Tuple[Response, int]:
            """
            Endpoint for retrieving the analysis data of a specific program.

            Params:
                program_id (int): ID of the program to analyze

            Returns:
                200: Successfully retrieved analysis data
                    ```
                    {
                       "analysis": {
                            "program": 1234,
                            "user": 5678,
                            "info": <analysis data>
                        }
                    }
                    ```

                404: No analysis found for the program
                    ```
                    {
                       "error": "No analysis found"
                    }
                    ```
            """
            analysis = self.__database.get_analysis(program_id, get_current_user().id)
            if analysis is None:
                return jsonify({"error": "No analysis found"}), 404

            return jsonify({"analysis": analysis.to_dict()}), 200

        @self.__app.route("/api/v1/programs/<int:program_id>/analyze", methods=["POST"])
        @login_required
        def analyze_program(program_id) -> Tuple[Response, int]:
            """
            Endpoint for initiating the analysis of a specific program.

            Params:
                program_id (int): ID of the program to analyze.

            Returns:
                200: Analysis is successfully initiated
                    ```
                    {
                       "message": "We are currently analyzing your program"
                    }
                    ```

                404: The specified program does not exist
                    ```
                    {
                       "error": "Program not found"
                    }
                    ```

                500: Internal server error when analysis is not finished
                    ```
                    {
                       "error": "Analyzed not finished"
                    }
                    ```
            """
            # Unsure that everything is ready for analysis
            ghidra_dir = (
                Path(self.__config.ghidra_dir) if self.__config.ghidra_dir else None
            )
            if ghidra_dir is None or not ghidra_dir.is_dir() or not ghidra_dir.exists():
                return (
                    jsonify(
                        {
                            "error": "Ghidra directory not set. Set it in the administrator panel."
                        }
                    ),
                    500,
                )

            if (
                len(self.__config.bsim_config.urls) == 0
                and len(self.__config.fidb_config.urls) == 0
            ):
                return (
                    jsonify(
                        {
                            "error": "No FIDB or BSIM database set. Set it in the administrator panel."
                        }
                    ),
                    500,
                )

            program = self.__database.get_program(
                program_id, user_id=get_current_user().id
            )
            if program is None:
                return jsonify({"error": "Program not found"}), 404

            # Unsure that language has been set
            if not self.__is_valid_language(program.language):
                return (
                    jsonify(
                        {
                            "error": "Program language is not set."
                            " Run autoload or set a language first."
                        }
                    ),
                    400,
                )

            # Unsure the program has at least one section
            if len(self.__database.list_program_sections(program.id)) == 0:
                return (
                    jsonify({"error": "Program has no memory layout."}),
                    400,
                )

            analysis = self.__database.get_analysis(program_id, get_current_user().id)
            if not analysis:
                analysis = Analysis(program=program_id, user=program.user, info={})
            elif analysis.info.get("status") != "finished":
                return jsonify({"error": "Analyzed not finished"}), 500

            # Resolve the binary before marking the analysis pending
            sharefile = self.__resolve_sharefile(program)
            if sharefile is None:
                return (
                    jsonify({"error": "Fail to get file associated with program"}),
                    500,
                )

            bsim_opts = self.__config.bsim_config.to_dict()
            fidb_opts = self.__config.fidb_config.to_dict()
            config = {
                "program": self.__jsonify_program(program),
                "databases": build_analysis_databases(bsim_opts.pop("urls")),
                "bsim": bsim_opts,
                "fidb": fidb_opts,
            }
            upload_file_config = (
                self.__database.get_upload_dir(program.user)
                + f"{program.id}_config.json"
            )
            if not self.__database.require_repo().push_file(
                upload_file_config, json.dumps(config).encode("utf-8")
            ):
                return (
                    jsonify(
                        {
                            "error": f"We cannot upload the configuration file for {program.name}"
                        }
                    ),
                    500,
                )

            # Now mark pending and enqueue (Add an already exisiting analysis is safe)
            self.__database.add_analysis(analysis)
            analysis.info = {"status": "pending", "enqueue": time.time()}
            options = AnalysisOptions.from_dict(request.get_json() or {})
            self.__celery_app.send_task(
                "frontendanalyzer.do_search_signatures",
                queue="frontendanalyzer",
                kwargs={
                    "job_data": {
                        "program": program.id,
                        "binary": str(sharefile),
                        "config": str(
                            self.__database.require_repo().get_sharefile(
                                upload_file_config
                            )
                        ),
                        "options": options.to_dict(),
                    }
                },
            )
            return (
                jsonify({"message": "We are currently analyzing your program"}),
                200,
            )

        @self.__app.route(
            "/api/v1/programs/<int:program_id>/autoload", methods=["POST"]
        )
        @login_required
        def autoload_program(program_id) -> Tuple[Response, int]:
            """
            Endpoint for the Auto-mode "detect" pass: run Ghidra's native importer
            to detect the program's language and memory layout. The worker persists
            the detected language + sections via localapi; the user then reviews and
            edits them before running analysis.

            Returns:
                200: Autoload is successfully initiated
                404: The specified program does not exist
                500: Internal server error
            """
            # Unsure that everything is ready for analysis
            ghidra_dir = (
                Path(self.__config.ghidra_dir) if self.__config.ghidra_dir else None
            )
            if ghidra_dir is None or not ghidra_dir.is_dir() or not ghidra_dir.exists():
                return (
                    jsonify(
                        {
                            "error": "Ghidra directory not set. Set it in the administrator panel."
                        }
                    ),
                    500,
                )

            program = self.__database.get_program(
                program_id, user_id=get_current_user().id
            )
            if program is None:
                return jsonify({"error": "Program not found"}), 404

            # Resolve the binary before marking the analysis pending
            analysis = self.__database.get_analysis(program_id, get_current_user().id)
            if not analysis:
                analysis = Analysis(program=program_id, user=program.user, info={})
            elif analysis.info.get("status") != "finished":
                return jsonify({"error": "Analyzed not finished"}), 500

            sharefile = self.__resolve_sharefile(program)
            if sharefile is None:
                return (
                    jsonify({"error": "Fail to get file associated with program"}),
                    500,
                )

            # Now mark pending and enqueue (Add an already exisiting analysis is safe)
            self.__database.add_analysis(analysis)
            analysis.info = {"status": "pending", "enqueue": time.time()}
            self.__celery_app.send_task(
                "frontendanalyzer.do_autoload",
                queue="frontendanalyzer",
                kwargs={
                    "job_data": {
                        "program": program.id,
                        "binary": str(sharefile),
                    }
                },
            )
            return (
                jsonify({"message": "Autoload is running"}),
                200,
            )

        @self.__app.route("/api/v1/programs/<int:program_id>/language", methods=["PUT"])
        @login_required
        def set_program_language(program_id) -> Tuple[Response, int]:
            """
            Endpoint for setting or overriding a program's language. Recovery path
            for when autoload didn't run / failed / can't detect the format, and a
            way to override a detected language.

            Body:
                {"language": str} - validated against the Ghidra language list.

            Returns:
                200: Language updated
                400: Invalid language
                404: Program not found
            """
            program = self.__database.get_program(
                program_id, user_id=get_current_user().id
            )
            if program is None:
                return jsonify({"error": "Program not found"}), 404

            data = request.get_json()
            language = data.get("language") if isinstance(data, dict) else None
            if not self.__is_valid_language(language):
                return jsonify({"error": "Language is invalid"}), 400

            # Language is valid at this point
            program.language = language  # type: ignore[assignment]
            self.__database.update_program(program, user_id=get_current_user().id)
            return jsonify({"success": "Language updated"}), 200

        @self.__app.route(
            "/api/v1/programs/<int:program_id>/sections", methods=["POST"]
        )
        @login_required
        def create_section(program_id) -> Tuple[Response, int]:
            """
            Endpoint for creating sections within a specific program.

            Params:
                program_id (int): ID of the program to which sections are being added.

            Returns:
                201: Successfully created sections
                    ```
                    {
                       "sections": [<list of created section data>]
                    }
                    ```

                400: Bad request for missing or invalid parameters
                    ```
                    {
                       "error": "Invalid section data in section list"
                    }
                    ```

                403: Forbidden if the program is currently under analysis
                    ```
                    {
                       "error": "Cannot modify program while it is being analyzed"
                    }
                    ```

                404: Program not found
                    ```
                    {
                       "error": "Program not found"
                    }
                    ```
            """
            # Step 1: Assert program is not being analyzed
            if self.__is_program_under_analysis(program_id):
                return (
                    jsonify(
                        {"error": "Cannot modify program while it is being analyzed"}
                    ),
                    403,
                )

            # Step 2: Get program object
            program = self.__database.get_program(
                program_id, user_id=get_current_user().id
            )
            if program is None:
                return jsonify({"error": "Program not found"}), 404

            # Step 3: Parse and validate JSON
            data = request.get_json()
            if not isinstance(data, dict) or not isinstance(data.get("sections"), list):
                return (
                    jsonify({"error": "Bad parameters, missing 'sections' list"}),
                    400,
                )

            existing_sections = {
                s.name: s for s in self.__database.list_program_sections(program.id)
            }

            sections_list = []
            for section_data in data["sections"]:
                if not isinstance(section_data, dict):
                    return (
                        jsonify({"error": "Invalid section data in section list"}),
                        400,
                    )

                # Set program ID
                section_data["program"] = program.id

                try:
                    section_obj = Section.from_dict(section_data)
                    if section_obj is None:
                        return (
                            jsonify({"error": "Invalid section data in section list"}),
                            400,
                        )
                    sections_list.append(section_obj)
                except ValueError as e:
                    return jsonify({"error": str(e)}), 400

            # Step 4: Add new sections (skip duplicates by name)
            results = []
            for section in sections_list:
                if section.name not in existing_sections:
                    db_section = self.__database.add_section(section)
                    if db_section is None:
                        return (
                            jsonify({"error": "Invalid section data in section list"}),
                            400,
                        )
                    results.append(db_section)
                else:
                    results.append(existing_sections[section.name])

            return jsonify({"sections": [s.to_dict() for s in results]}), 201

        @self.__app.route("/api/v1/programs/<int:program_id>/sections", methods=["GET"])
        @login_required
        def get_sections(program_id) -> Tuple[Response, int]:
            """
            Endpoint for retrieving all sections associated with a specific program.

            Params:
                program_id (int): ID of the program whose sections are to be retrieved.

            Returns:
                200: Successfully retrieved sections
                    ```
                    {
                       "sections": [<list of sections data>]
                    }
                    ```

                404: Program not found
                    ```
                    {
                       "error": "Program not found"
                    }
                    ```
            """
            program = self.__database.get_program(
                program_id, user_id=get_current_user().id
            )
            if program is None:
                return jsonify({"error": "Program not found"}), 404

            sections = self.__database.list_program_sections(program.id)
            return jsonify({"sections": [s.to_dict() for s in sections]}), 200

        @self.__app.route(
            "/api/v1/programs/<int:program_id>/sections/<int:section_id>",
            methods=["GET"],
        )
        @login_required
        def get_section(program_id, section_id) -> Tuple[Response, int]:
            """
            Endpoint for retrieving a specific section by its ID within a program.

            Params:
                program_id (int): ID of the program the section belongs to.
                section_id (int): ID of the section to retrieve.

            Returns:
                200: Successfully retrieved the section
                    ```
                    <section data>
                    ```

                404: Program or section not found
                    ```
                    {
                       "error": "Section not found"
                    }
                    ```
            """
            program = self.__database.get_program(
                program_id, user_id=get_current_user().id
            )
            if program is None:
                return jsonify({"error": "Program not found"}), 404

            # Get section from database
            section = self.__database.get_section(section_id, program_id=program.id)
            if not section:
                return jsonify({"error": "Section not found"}), 404

            recursive = request.args.get("recursive", "").lower() == "true"

            if recursive:
                functions_data = []
                functions = self.__database.list_section_functions(section.id)

                for function in functions:
                    function_data = function.to_dict()
                    matches = self.__database.list_function_matches(function.id)
                    function_data["matches"] = [m.to_dict() for m in matches]
                    functions_data.append(function_data)

                section_data = section.to_dict()
                section_data["functions"] = functions_data
                return jsonify(section_data), 200

            return jsonify(section.to_dict()), 200

        @self.__app.route(
            "/api/v1/programs/<int:program_id>/sections/<int:section_id>",
            methods=["DELETE"],
        )
        @login_required
        def delete_section(program_id, section_id) -> Tuple[Response, int]:
            """
            Endpoint for deleting a specific section from a program.

            Params:
                program_id (int): ID of the program the section belongs to.
                section_id (int): ID of the section to delete.

            Returns:
                200: Successfully deleted the section
                    ```
                    {
                       "success": "Section deleted"
                    }
                    ```

                403: Forbidden if the program is currently under analysis
                    ```
                    {
                       "error": "Cannot modify program while it is being analyzed"
                    }
                    ```

                404: Program or section not found
                    ```
                    {
                       "error": "Section not found"
                    }
                    ```

            """
            # Step 1: Assert program is not being analyzed
            if self.__is_program_under_analysis(program_id):
                return (
                    jsonify(
                        {"error": "Cannot modify program while it is being analyzed"}
                    ),
                    403,
                )
            program = self.__database.get_program(
                program_id, user_id=get_current_user().id
            )
            if program is None:
                return jsonify({"error": "Program not found"}), 404

            # Get section from database
            section = self.__database.get_section(section_id, program_id=program.id)
            if not section:
                return jsonify({"error": "Section not found"}), 404

            self.__database.delete_section(section_id)
            return jsonify({"success": "Section deleted"}), 200

        @self.__app.route(
            "/api/v1/programs/<int:program_id>/sections/", methods=["DELETE"]
        )
        @login_required
        def delete_all_sections(program_id) -> Tuple[Response, int]:
            """
            Endpoint for deleting all sections associated with a specific program.

            Params:
                program_id (int): ID of the program whose sections are to be deleted.

            Returns:
                200: Successfully deleted all sections
                    ```
                    {
                       "success": "All sections deleted"
                    }
                    ```

                403: Forbidden if the program is currently under analysis
                    ```
                    {
                       "error": "Cannot modify program while it is being analyzed"
                    }
                    ```

                404: Program not found
                    ```
                    {
                       "error": "Program not found"
                    }
                    ```
            """
            # Step 1: Assert program is not being analyzed
            if self.__is_program_under_analysis(program_id):
                return (
                    jsonify(
                        {"error": "Cannot modify program while it is being analyzed"}
                    ),
                    403,
                )
            program = self.__database.get_program(
                program_id, user_id=get_current_user().id
            )
            if program is None:
                return jsonify({"error": "Program not found"}), 404

            self.__database.delete_program_sections(program.id)
            return jsonify({"success": "All sections deleted"}), 200

        @self.__app.route(
            "/api/v1/programs/<int:program_id>/sections/<int:section_id>/functions",
            methods=["POST"],
        )
        @login_required
        def create_function(program_id, section_id) -> Tuple[Response, int]:
            """
            Endpoint for creating functions within a specific section of a program.

            Params:
                program_id (int): ID of the program containing the section.
                section_id (int): ID of the section where functions are being added.

            Returns:
                201: Successfully created functions
                    ```
                    {
                       "functions": [<list of created function data>]
                    }
                    ```

                400: Bad request for missing or invalid parameters
                    ```
                    {
                       "error": "Invalid function data in list"
                    }
                    ```

                403: Forbidden if the program is currently under analysis
                    ```
                    {
                       "error": "Cannot modify program while it is being analyzed"
                    }
                    ```

                404: Program or section not found
                    ```
                    {
                       "error": "Program not found"
                    }
                    ```
            """
            # Step 1: Assert program is not being analyzed
            if self.__is_program_under_analysis(program_id):
                return (
                    jsonify(
                        {"error": "Cannot modify program while it is being analyzed"}
                    ),
                    403,
                )

            # Step 2: Get section
            program = self.__database.get_program(
                program_id, user_id=get_current_user().id
            )
            if program is None:
                return jsonify({"error": "Program not found"}), 404

            # Get section from database
            section = self.__database.get_section(section_id, program_id=program.id)
            if not section:
                return jsonify({"error": "Section not found"}), 404

            # Step 3: Parse and validate JSON body
            data = request.get_json()
            if not isinstance(data, dict) or not isinstance(
                data.get("functions"), list
            ):
                return (
                    jsonify({"error": "Bad parameters, missing 'functions' list"}),
                    400,
                )

            functions_list = []
            for function_data in data["functions"]:
                if not isinstance(function_data, dict):
                    return jsonify({"error": "Invalid function data in list"}), 400

                # Set section ID
                function_data["section"] = section.id

                try:
                    function_obj = Function.from_dict(function_data)
                    functions_list.append(function_obj)
                except ValueError as e:
                    return jsonify({"error": str(e)}), 400

            # Step 4: Add functions to DB
            for function in functions_list:
                self.__database.add_function(function)

            return jsonify({"functions": [f.to_dict() for f in functions_list]}), 201

        @self.__app.route(
            "/api/v1/programs/<int:program_id>/sections/<int:section_id>/functions",
            methods=["GET"],
        )
        @login_required
        def get_functions(program_id, section_id) -> Tuple[Response, int]:
            """
            Endpoint for retrieving all functions within a specific section of a program.

            Params:
                program_id (int): ID of the program containing the section.
                section_id (int): ID of the section whose functions are to be retrieved.

            Returns:
                200: Successfully retrieved functions
                    ```
                    {
                       "functions": [<list of function data>]
                    }
                    ```

                404: Program or section not found
                    ```
                    {
                       "error": "Program not found"
                    }
                    ```
            """
            program = self.__database.get_program(
                program_id, user_id=get_current_user().id
            )
            if program is None:
                return jsonify({"error": "Program not found"}), 404

            # Get section from database
            section = self.__database.get_section(section_id, program_id=program.id)
            if not section:
                return jsonify({"error": "Section not found"}), 404

            functions = self.__database.list_section_functions(section.id)
            return jsonify({"functions": [f.to_dict() for f in functions]}), 200

        @self.__app.route(
            "/api/v1/programs/<int:program_id>/sections/<int:section_id>"
            "/functions/<int:function_id>",
            methods=["GET"],
        )
        @login_required
        def get_function(program_id, section_id, function_id) -> Tuple[Response, int]:
            """
            Endpoint for retrieving a specific function by its ID within a section of a program.

            Params:
                program_id (int): ID of the program containing the section.
                section_id (int): ID of the section where the function resides.
                function_id (int): ID of the function to retrieve.

            Returns:
                200: Successfully retrieved the function
                    ```
                    <function data>
                    ```

                404: Program, section, or function not found
                    ```
                    {
                       "error": "Function not found"
                    }
                    ```
            """
            program = self.__database.get_program(
                program_id, user_id=get_current_user().id
            )
            if program is None:
                return jsonify({"error": "Program not found"}), 404

            # Get section from database
            section = self.__database.get_section(section_id, program_id=program.id)
            if not section:
                return jsonify({"error": "Section not found"}), 404

            # Step 1: Retrieve function
            function = self.__database.get_function(function_id, section_id=section.id)
            if function is None:
                return jsonify({"error": "Function not found"}), 404

            # Step 2: Check for `recursive=true`
            recursive = request.args.get("recursive", "").lower() == "true"

            if recursive:
                function_data = function.to_dict()
                matches = self.__database.list_function_matches(function.id)
                function_data["matches"] = [m.to_dict() for m in matches]
                return jsonify(function_data), 200

            return jsonify(function.to_dict()), 200

        @self.__app.route(
            "/api/v1/programs/<int:program_id>/sections/<int:section_id>"
            "/functions/<int:function_id>",
            methods=["DELETE"],
        )
        @login_required
        def delete_function(
            program_id, section_id, function_id
        ) -> Tuple[Response, int]:
            """
            Endpoint for deleting a specific function from a section of a program.

            Params:
                program_id (int): ID of the program containing the section.
                section_id (int): ID of the section where the function resides.
                function_id (int): ID of the function to delete.

            Returns:
                200: Successfully deleted the function
                    ```
                    {
                       "success": "Function deleted"
                    }
                    ```

                403: Forbidden if the program is currently under analysis
                    ```
                    {
                       "error": "Cannot modify program while it is being analyzed"
                    }
                    ```

                404: Program, section, or function not found
                    ```
                    {
                       "error": "Function not found"
                    }
                    ```
            """
            # Step 1: Assert program is not being analyzed
            if self.__is_program_under_analysis(program_id):
                return (
                    jsonify(
                        {"error": "Cannot modify program while it is being analyzed"}
                    ),
                    403,
                )
            # Step 1: Assert program is not being analyzed
            program = self.__database.get_program(
                program_id, user_id=get_current_user().id
            )
            if program is None:
                return jsonify({"error": "Program not found"}), 404

            # Get section from database
            section = self.__database.get_section(section_id, program_id=program.id)
            if not section:
                return jsonify({"error": "Section not found"}), 404

            # Step 1: Retrieve function
            function = self.__database.get_function(function_id, section_id=section.id)
            if function is None:
                return jsonify({"error": "Function not found"}), 404

            self.__database.delete_function(function)
            return jsonify({"success": "Function deleted"}), 200

        @self.__app.route(
            "/api/v1/programs/<int:program_id>/sections/<int:section_id>"
            "/functions/<int:function_id>/matches",
            methods=["GET"],
        )
        @login_required
        def get_matches(program_id, section_id, function_id) -> Tuple[Response, int]:
            """
            Endpoint for retrieving all matches related to a specific function
            within a section of a program.

            Params:
                program_id (int): ID of the program containing the section.
                section_id (int): ID of the section where the function resides.
                function_id (int): ID of the function whose matches are to be retrieved.

            Returns:
                200: Successfully retrieved function matches
                    ```
                    {
                       "matches": [<list of match data>]
                    }
                    ```

                404: Program, section, or function not found
                    ```
                    {
                       "error": "Function not found"
                    }
                    ```
            """
            program = self.__database.get_program(
                program_id, user_id=get_current_user().id
            )
            if program is None:
                return jsonify({"error": "Program not found"}), 404

            # Get section from database
            section = self.__database.get_section(section_id, program_id=program.id)
            if not section:
                return jsonify({"error": "Section not found"}), 404

            # Step 1: Retrieve function
            function = self.__database.get_function(function_id, section_id=section.id)
            if function is None:
                return jsonify({"error": "Function not found"}), 404

            matches = self.__database.list_function_matches(function.id)
            return jsonify({"matches": [m.to_dict() for m in matches]}), 200

    def __languages(self) -> list:
        """The Ghidra language list, scanned once and cached"""
        # ghidra_dir may be unset
        if not self.__config.ghidra_dir:
            return []
        if self.__languages_cache is None:
            self.__languages_cache = get_ghidra_languages(
                Path(self.__config.ghidra_dir)
            )
        return self.__languages_cache

    def __is_valid_language(
        self, language: Optional[str], allow_auto: bool = False
    ) -> bool:
        """Whether `language` is a real Ghidra language (or the "auto" sentinel
        when `allow_auto`)."""
        if not isinstance(language, str):
            return False
        if allow_auto and language == "auto":
            return True
        return language in self.__languages()

    def __resolve_sharefile(self, program: Program):
        """Resolve a program's binary sharefile, or None if unavailable."""
        file = self.__database.get_file_user(program.file, user_id=program.user)
        if file is None:
            return None
        return self.__database.get_sharefile(file)

    def __is_program_under_analysis(self, program_id: int) -> bool:
        """Return whether the given program is under analysis or not

        Args:
            program_id (int): The ID of the program

        Returns:
            bool: True if the program is currently being analyzed, False otherwise
        """
        analysis = self.__database.get_analysis(program_id)
        if not analysis or analysis.info.get("status") == "finished":
            return False

        return True

    def __jsonify_program(self, program: Program) -> dict:
        # Generate all the program data up to function level into a json file that will
        # be given to the ghidra analyzer
        sections_data = []
        sections = self.__database.list_program_sections(program.id)
        for section in sections:
            functions = self.__database.list_section_functions(section.id)
            section_data = section.to_dict()
            section_data.update({"functions": [f.to_dict() for f in functions]})
            sections_data.append(section_data)

        program_data = program.to_dict()
        program_data.update({"sections": sections_data})

        return program_data
