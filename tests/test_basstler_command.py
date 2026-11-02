"""
Tests for the ``basstler`` command, the entry point every v3 command is mounted on.
"""

from __future__ import annotations

import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import pytest

from basstler.locations import PackageLocation

INSTALLED_COMMAND = Path(sys.executable).with_name(PackageLocation.DIRECTORY.name)
"""
The console script the package installs beside the interpreter running the tests.
"""

# %% the version


@pytest.mark.parametrize(
    "invocation",
    [
        [str(INSTALLED_COMMAND)],
        [sys.executable, "-m", PackageLocation.DIRECTORY.name],
    ],
    ids=["console-script", "module-runner"],
)
def test_the_command_reports_the_installed_package_version(invocation):
    result = subprocess.run(
        [*invocation, "--version"], capture_output=True, text=True, check=False
    )

    assert (result.returncode, result.stdout.strip()) == (
        0,
        version(PackageLocation.DIRECTORY.name),
    )
