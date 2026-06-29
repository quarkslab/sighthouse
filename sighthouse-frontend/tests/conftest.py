"""Shared pytest setup for the test suite.

Point ``$XDG_DATA_HOME`` at a throw-away directory before any sighthouse module
is imported, so nothing in the suite touches (or needs write access to) the real
user data directory.
"""

import os
import tempfile

os.environ.setdefault("XDG_DATA_HOME", tempfile.mkdtemp(prefix="sighthouse_xdg_"))
