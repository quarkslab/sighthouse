"""Local REST API for analyzer worker to push results"""

from typing import Optional, List, Tuple, Dict
from flask import Flask, request, jsonify, Response
from werkzeug.exceptions import HTTPException

from sighthouse.core.utils.api import ServerThread
from .database import FrontendDatabase
from .model import Function, Match, Analysis, Section


class LocalRestAPI(ServerThread):
    """
    Local REST API for analyzer worker to push results
    """

    def __init__(
        self,
        database: FrontendDatabase,
        host: str = "localhost",
        port: int = 6670,
    ):
        self.__database: FrontendDatabase = database
        self.__app = Flask(__name__)
        self.__register_routes()
        self.__register_error_handlers()

        super().__init__(self.__app, host, port)

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
                return jsonify({"error": e.description}), e.code
            return jsonify({"error": str(e)}), 500

    def __register_routes(self):
        """Register all routes for LocalRestApi"""

        @self.__app.route("/api/v1/ping", methods=["GET"])
        def ping() -> tuple[Response, int]:
            """Just a ping function

            Returns:
                tuple[Response, int]: A tuple containing the HTTP response code and the data
                to send to the remote peer
            """
            return jsonify({"ping": "pong"}), 200

        @self.__app.route("/api/v1/programs/<int:program_id>/analyze", methods=["PUT"])
        def update_analysis(program_id: int) -> Tuple[Response, int]:
            """Update analysis to implement

            Args:
                program_id (int): program id

            Returns:
                tuple[Response, int]: A tuple containing the HTTP response code and the data
                to send to the remote peer
            """
            data = request.get_json()
            status = data["status"]  # pending
            progress = data["progress"]  # je raconte ma vie
            analysis: Optional[Analysis] = self.__database.get_analysis(program_id)
            if not analysis:
                return jsonify({"error": "Fail to find analysis"}), 404

            # Update analysis infos
            analysis.info = {"status": status, "progress": progress}
            if status == "finished":
                # @TODO: is this the right place to delete the config file ?
                program = self.__database.get_program(program_id)
                if program is None:
                    return jsonify({"error": "No program found for this analysis"}), 404
                try:
                    file = (
                        self.__database.get_upload_dir(program.user)
                        + f"{program.id}_config.json"
                    )
                    self.__database.repo.delete_file(file)
                except Exception as e:
                    print(e)
            return jsonify({"success": "Analysis status updated"}), 200

        @self.__app.route(
            "/api/v1/programs/<int:program_id>/sections", methods=["POST"]
        )
        def create_sections(program_id: int) -> Tuple[Response, int]:
            """Create sections discovered by the autoload pass.

            Args:
                program_id (int): program id

            Returns:
                tuple[Response, int]: A tuple containing the HTTP response code and the data
                to send to the remote peer
            """
            program = self.__database.get_program(program_id)
            if program is None:
                return jsonify({"error": "Fail to find program"}), 404

            data = request.get_json()
            if not isinstance(data, dict) or not isinstance(data.get("sections"), list):
                return (
                    jsonify({"error": "Bad parameters, missing 'sections' list"}),
                    400,
                )

            # First parse all the input data
            sections_list = []
            for section_data in data["sections"]:
                if not isinstance(section_data, dict):
                    return jsonify({"error": "Invalid section data found"}), 400

                # Set program id
                section_data["program"] = program.id
                try:
                    sections_list.append(Section.from_dict(section_data))
                except ValueError as e:
                    return jsonify({"error": str(e)}), 400

            # Then add elements to the database, skipping names that already exist
            # so a re-run of autoload is idempotent
            existing = {
                s.name: s for s in self.__database.list_program_sections(program.id)
            }
            results = []
            for section in sections_list:
                if section.name in existing:
                    results.append(existing[section.name])
                    continue
                db_section = self.__database.add_section(section)
                if db_section is None:
                    return jsonify({"error": "Failed to add section"}), 500
                results.append(db_section)

            return jsonify({"sections": [s.to_dict() for s in results]}), 201

        @self.__app.route("/api/v1/programs/<int:program_id>/language", methods=["PUT"])
        def update_language(program_id: int) -> Tuple[Response, int]:
            """Set a program's language.

            Args:
                program_id (int): program id

            Returns:
                tuple[Response, int]: A tuple containing the HTTP response code and the data
                to send to the remote peer
            """
            program = self.__database.get_program(program_id)
            if program is None:
                return jsonify({"error": "Fail to find program"}), 404

            data = request.get_json()
            language = data.get("language") if isinstance(data, dict) else None
            if not isinstance(language, str):
                return jsonify({"error": "Bad parameters, missing 'language'"}), 400

            program.language = language
            self.__database.update_program(program)
            return jsonify({"success": "Language updated"}), 200

        @self.__app.route(
            "/api/v1/programs/<int:program_id>/sections/<int:section_id>/functions",
            methods=["POST"],
        )
        def create_function(program_id: int, section_id: int) -> Tuple[Response, int]:
            """Create a new function discover inside the database

            Args:
                program_id (int): program id
                section_id (int): section id

            Returns:
                tuple[Response, int]: A tuple containing the HTTP response code and the data
                to send to the remote peer
            """
            section = self.__database.get_section(section_id, program_id=program_id)
            if section is None:
                return jsonify({"error": "Fail to find section"}), 404

            data = request.get_json()

            if not isinstance(data, dict) or not isinstance(
                data.get("functions"), list
            ):
                return (
                    jsonify({"error": "Bad parameters, missing 'functions' list"}),
                    400,
                )

            # First parse all the input data
            functions_list = []
            for function_data in data["functions"]:
                if not isinstance(function_data, dict):
                    return jsonify({"error": "Invalid function data found"}), 400

                # Set section id
                function_data["section"] = section.id
                try:
                    function = Function.from_dict(function_data)
                    functions_list.append(function)
                except ValueError as e:
                    return jsonify({"error": str(e)}), 400

            # Then add elements to the database
            for function in functions_list:
                # Add function to database
                self.__database.add_function(function)

            return jsonify({"functions": [f.to_dict() for f in functions_list]}), 201

        @self.__app.route(
            "/api/v1/programs/<int:program_id>/sections/<int:section_id>/functions",
            methods=["DELETE"],
        )
        def delete_functions(program_id: int, section_id: int) -> Tuple[Response, int]:
            """Delete a function inside the database

            Args:
                program_id (int): program id
                section_id (int): section id

            Returns:
                tuple[Response, int]: A tuple containing the HTTP response code and the data
                to send to the remote peer
            """
            # Delete function should also delete all the matches
            if not self.__database.delete_section_functions(section_id):
                return (
                    jsonify(
                        {
                            "error": "Fail to delete the functions inside the given section"
                        }
                    ),
                    500,
                )
            return jsonify({"success": "Functions deleted successfully"}), 200

        @self.__app.route(
            "/api/v1/programs/<int:program_id>/sections/<int:section_id>"
            "/functions/<int:function_id>/matches",
            methods=["POST"],
        )
        def create_matches(
            program_id: int, section_id: int, function_id: int
        ) -> Tuple[Response, int]:
            """Create a new matches inside the database

            Args:
                program_id (int): program id
                section_id (int): section id
                function_id (int): function id

            Returns:
                Tuple[Response, int]: A tuple containing the HTTP response code and the data
                to send to the remote peer
            """
            function = self.__database.get_function(function_id, section_id=section_id)
            if function is None:
                return jsonify({"error": "Fail to find function"}), 404

            data = request.get_json()

            if not isinstance(data, dict) or not isinstance(data.get("matches"), list):
                return jsonify({"error": "Bad parameters, missing 'matches' list"}), 400

            # First parse all the input data
            matches_list = []
            for match_data in data["matches"]:
                if not isinstance(match_data, dict):
                    return jsonify({"error": "Invalid match data found"}), 400

                # Set section id
                match_data["function"] = function.id
                try:
                    match = Match.from_dict(match_data)
                    matches_list.append(match)
                except ValueError as e:
                    return jsonify({"error": str(e)}), 400

            for match in matches_list:
                self.__database.add_match(match)

            return jsonify({"matches": [m.to_dict() for m in matches_list]}), 201
