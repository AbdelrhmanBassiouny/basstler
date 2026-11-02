"""
Tests for finding the plugin whose scripts the package runs, which only an exported
plugin root names.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from basstler import exceptions
from basstler.exceptions import PluginRootNotADirectoryError, PluginRootUnsetError
from basstler.locations import BasstlerVariable, PluginLocation, PluginSkillLocation
from basstler.plugin_root import PluginRoot

from .constants.environment import ScrubbedEnvironmentPrefix
from .constants.paths import RepositoryLocation

# %% the exported root


def test_the_plugin_root_is_the_one_the_configuration_exports(tmp_path: Path):
    """
    A module run by a hook or skill, which sourced the plugin's configuration, runs that
    plugin's scripts wherever the package itself is installed.
    """
    assert (
        PluginRoot.locate({BasstlerVariable.PLUGIN_ROOT: str(tmp_path)}).directory
        == tmp_path
    )


def test_the_suite_runs_this_checkouts_plugin_whatever_the_session_exports():
    """
    A session running the plugin exports its synced copy as the plugin root; the suite
    still tests this checkout's hooks, not the release that session synced.
    """
    assert PluginRoot.locate(os.environ).directory == RepositoryLocation.PLUGIN.value


@pytest.mark.parametrize(
    "location",
    [PluginLocation.SESSION_START_SCRIPT, PluginSkillLocation.STARTER_NOTES],
    ids=lambda member: member._name_,
)
def test_a_plugin_file_is_found_under_the_root(
    tmp_path: Path, location: PluginLocation | PluginSkillLocation
):
    """
    Each of the plugin's files is named relative to its root, and found under it.
    """
    assert PluginRoot(tmp_path).path_of(location) == tmp_path / location


# %% refusing a root that names no plugin


def test_refuses_an_unset_plugin_root():
    """
    An installed package has no plugin beside it to fall back to.
    """
    with pytest.raises(PluginRootUnsetError):
        PluginRoot.locate({})


def test_refuses_an_empty_plugin_root():
    """
    An exported but empty root names no plugin either.
    """
    with pytest.raises(PluginRootUnsetError):
        PluginRoot.locate({BasstlerVariable.PLUGIN_ROOT: ""})


@pytest.mark.parametrize("make_file", [True, False], ids=["a file", "missing"])
def test_refuses_a_plugin_root_that_is_not_a_directory(tmp_path: Path, make_file: bool):
    """
    A root that is a file, or is not there at all, would only fail at the first script
    run under it.
    """
    root = tmp_path / "plugin"
    if make_file:
        root.touch()
    with pytest.raises(PluginRootNotADirectoryError):
        PluginRoot.locate({BasstlerVariable.PLUGIN_ROOT: str(root)})


def test_the_package_imports_without_a_plugin_root():
    """
    Workflows run the package's modules with no plugin installed, so only running one of
    the plugin's scripts may need its root.
    """
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(ScrubbedEnvironmentPrefix.BASSTLER)
    }
    subprocess.run(
        [sys.executable, "-c", f"import {exceptions.__name__}"],
        check=True,
        env=environment,
    )
