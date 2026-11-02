"""
The ``basstler`` command: one command tree that each v3 command is mounted on.
"""

from __future__ import annotations

from functools import partial
from importlib.metadata import version

from cyclopts import App

from basstler.locations import PackageLocation

app = App(
    name=PackageLocation.DIRECTORY.name,
    help="Workflow tooling for stacked pull requests and plans.",
    version=partial(version, PackageLocation.DIRECTORY.name),
)
"""
The command tree; a v3 command is added with ``@app.command``.
"""

if __name__ == "__main__":
    app()
