"""Threaded HTTP server"""

from threading import Thread
from werkzeug.serving import BaseWSGIServer, make_server


class ServerThread(Thread):
    """
    A threaded HTTP server that runs a Flask application.

    This class extends the `Thread` class to host a Flask application in a separate thread,
    allowing for non-blocking operation in applications that need to handle concurrent
    requests. The server will run until explicitly shut down.
    """

    def __init__(self, app: "Flask", host: str, port: int):  # type: ignore[name-defined]
        """
        Initializes a new instance of the ServerThread class.

        Args:
            app (Flask): The Flask application instance that this server will host.
            host (str): The host address (e.g., '127.0.0.1' or '0.0.0.0') on which the server
                        will listen for incoming requests.
            port (int): The port number (typically between 1024 and 65535) on which the server
                        will accept connections.
        """
        Thread.__init__(self)
        self.__app = app
        self.__ctx = app.app_context()
        self.__ctx.push()
        self.__host = host
        self.__port = port
        self.__server: BaseWSGIServer = make_server(
            self.__host, self.__port, self.__app, threaded=True
        )

    def run(self) -> None:
        """Starts the HTTP server, listening for incoming requests
        and serving the Flask application."""
        self.__server.serve_forever()

    def shutdown(self) -> None:
        """Shuts down the running server gracefully."""
        self.__server.shutdown()
