"""
The ``basstler`` command: one command tree that each v3 command is mounted on.
"""

from __future__ import annotations

from functools import partial
from importlib.metadata import version

from cyclopts import App

from basstler.code_rules.command_line import code_rules_app
from basstler.locations import PackageLocation
from basstler.plan.repository_rules_command import repository_rules_app

app = App(
    name=PackageLocation.DIRECTORY.name,
    help="Workflow tooling for stacked pull requests and plans.",
    version=partial(version, PackageLocation.DIRECTORY.name),
)
"""
The command tree; a v3 command is added with ``@app.command``.
"""

app.command(code_rules_app)
app.command(repository_rules_app)

if __name__ == "__main__":
    app()
