from sighthouse.client.SightHouseClient import SightHouseAnalysis


class LoggingRadareSighthouse(object):

    def __init__(self) -> None:
        """Initialize logging class"""
        # TODO
        raise "Not Implemented"

    def error(self, message: str):
        """Show an error message

        Args:
            message (str): The message to show
        """
        # TODO
        raise "Not Implemented"

    def warning(self, message: str):
        """Show an warning message

        Args:
            message (str): The message to show
        """
        # TODO
        raise "Not Implemented"

    def info(self, message: str):
        """Show an info message

        Args:
            message (str): The message to show
        """
        # TODO
        raise "Not Implemented"


class SightHouseRadareAnalysis(SightHouseAnalysis):

    def get_current_arch(self) -> None:
        """get current architecture and translate to ghidra one"""
        # TODO
        raise "Not Implemented"

    def update_progress(self, message: str) -> None:
        """show an update progress

        Args:
            message (str): message to show
        """
        # TODO
        raise "Not Implemented"

    def get_base_addr(self) -> int:
        """Get the base address of the binary

        Returns:
            int: return the base address of binary
        """
        # TODO
        raise "Not Implemented"

    def get_current_binary(self) -> bytes:
        """Retrieve the current binaries in bytes

        Returns:
            bytes: the content in bytes of the current binaries
        """
        # TODO
        raise "Not Implemented"

    def add_tag(self, address: int, tag: str, message: str) -> None:
        """Add a tag on the SRE

        Args:
            address (int): address where put the tag
            tag (str): tag of message
            message (str): message to show
        """
        # TODO
        raise "Not Implemented"


if __name__ == "__main__":
    analyzer = SightHouseRadareAnalysis(
        "http://localhost:6669", "toto", "83ef32ec6adb69b19acb5c37eda8b2e3"
    )
    analyzer.run()
