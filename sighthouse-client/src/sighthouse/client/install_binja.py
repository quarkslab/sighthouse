import platform
import os
from pathlib import Path
from shutil import rmtree


def get_binja_user_dir() -> Path:
    # Linux
    user_settings_dir: Path = Path.home() / ".binaryninja"
    if platform.system() == "Windows":
        user_settings_dir = Path(os.environ["APPDATA"]) / "Binary Ninja"
    if platform.system() == "Darwin":
        user_settings_dir = (
            Path.home() / "Library" / "Application Support" / "Binary Ninja"
        )

    if not user_settings_dir.exists() or not user_settings_dir.is_dir():
        print("Fail to find Binja user directory")
        exit(1)

    return user_settings_dir


def main() -> None:
    plugins_dir: Path = get_binja_user_dir() / "plugins"
    print(f"Installing Sighthouse client script to '{plugins_dir}'")
    sighthouse_dir: Path = plugins_dir / "sighthouse"
    try:
        rmtree(sighthouse_dir)
    except Exception:
        pass
    sighthouse_dir.mkdir(exist_ok=True)
    # Copy sighthouse depencency
    module = Path(__file__).parent / "SightHouseClient.py"
    if not module.exists() or not module.is_file():
        print("Error: Fail to find Sighthouse client module for Binja")
        return

    # Copy script
    with open(str(module), "r") as fpin:
        with open(str(sighthouse_dir / "SightHouseClient.py"), "w") as fpout:
            fpout.write(fpin.read())

    # Copy client script
    client_script = Path(__file__).parent / "SightHouseClientBinja.py"
    if not client_script.exists() or not client_script.is_file():
        print("Error: Fail to find Sighthouse client script for Binja")
        return

    # Copy script
    with open(str(client_script), "r") as fpin:
        with open(str(sighthouse_dir / "__init__.py"), "w") as fpout:
            fpout.write(fpin.read())

    print("Sighthouse client script installed!")


if __name__ == "__main__":
    main()
