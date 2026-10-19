"""
The paths the package names, and how a member stands in for its path.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import basstler
from .constants.environment import ScrubbedEnvironmentPrefix
from .constants.paths import RepositoryLocation
from basstler import locations
from basstler.locations import (
    BasstlerVariable,
    PackageLocation,
    PluginLocation,
    ProjectLocation,
)

# %% a member stands in for its path


@pytest.mark.parametrize(
    "location", list(ProjectLocation), ids=lambda member: member._name_
)
def test_a_member_formats_as_its_path(location: ProjectLocation):
    """
    Members are written into ``git`` references, ``bash -c`` lines and reports as text,
    where an enumeration's own formatting would print its name.
    """
    assert f"{location}" == str(location.value)


def test_a_member_is_accepted_where_a_path_is(tmp_path: Path):
    """
    Joining onto a root, joining beneath a member and handing one to ``os`` all see the
    path.
    """
    assert (
        tmp_path / ProjectLocation.PERSONAL_NOTES
        == tmp_path / ProjectLocation.PERSONAL_NOTES.value
    )
    assert (
        ProjectLocation.PERSONAL_NOTES / "a.md"
        == ProjectLocation.PERSONAL_NOTES.value / "a.md"
    )
    assert os.fspath(ProjectLocation.PERSONAL_NOTES) == str(
        ProjectLocation.PERSONAL_NOTES.value
    )


@pytest.mark.parametrize(
    "location", list(ProjectLocation), ids=lambda member: member._name_
)
def test_a_member_is_its_path(location: ProjectLocation):
    """
    A member is the path it names, so any ``Path`` method reads it directly.
    """
    assert isinstance(location, Path)
    assert location == location.value


def test_a_path_derived_from_a_member_is_a_plain_path():
    """
    Joining, taking a parent or a sibling builds a new path rather than looking up a
    member that does not exist.
    """
    derived = (
        ProjectLocation.PERSONAL_NOTES / "a.md",
        ProjectLocation.PERSONAL_NOTES.parent,
        ProjectLocation.PERSONAL_NOTES.with_name("other"),
    )

    assert [type(path) for path in derived] == [type(Path())] * len(derived)


def test_members_hash_as_their_paths():
    """
    A member and its path are one key, as two equal paths are.
    """
    assert {ProjectLocation.PERSONAL_NOTES: True}[ProjectLocation.PERSONAL_NOTES.value]


# %% the package's own files


def test_the_package_directory_is_where_the_package_is_imported_from():
    """
    Every location shipped in the package is found from this one.
    """
    assert PackageLocation.DIRECTORY.value == Path(basstler.__file__).parent


@pytest.mark.parametrize(
    "location",
    [location for location in PackageLocation if location is not PackageLocation.BOARD],
    ids=lambda member: member._name_,
)
def test_every_shipped_location_exists(location: PackageLocation):
    """
    A misspelled location would only fail at the first read of it.

    The board is left out, as scratch state a maintenance pass writes.
    """
    assert location.value.exists()


def test_the_package_directory_sits_under_the_source_trees_src_directory():
    """
    The package follows the ``src`` layout every other package in this repository uses.
    """
    assert (
        PackageLocation.DIRECTORY.value
        == PackageLocation.SOURCE_TREE / "src" / PackageLocation.DIRECTORY.value.name
    )


def test_the_dependency_declaration_is_the_source_trees_own_metadata():
    """
    ``pyproject.toml`` is read from the source tree, beside the ``src`` directory,
    rather than shipped inside the package.
    """
    assert (
        PackageLocation.DEPENDENCY_DECLARATION.value
        == PackageLocation.SOURCE_TREE / "pyproject.toml"
    )


# %% the plugin's files


def plugin_root_resolved_with(environment: dict[str, str]) -> Path:
    """
    :param environment: Variables to import the package with, on top of this process's
        own, scrubbed of every variable the shell configuration exports.
    :return: The plugin root a fresh import of the package resolves.
    """
    inherited = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(ScrubbedEnvironmentPrefix.BASSTLER)
    }
    return Path(
        subprocess.run(
            [
                sys.executable,
                "-c",
                f"from {locations.__name__} import {PluginLocation.__name__} as l; "
                f"print(l.ROOT.value)",
            ],
            capture_output=True,
            text=True,
            check=True,
            env={**inherited, **environment},
        ).stdout.strip()
    )


def test_the_plugin_is_the_checkouts_own_when_no_root_is_exported():
    """
    A module run from a source checkout, with nothing exported, runs that checkout's
    plugin.
    """
    assert plugin_root_resolved_with({}) == RepositoryLocation.PLUGIN.value


def test_the_plugin_is_the_one_the_configuration_exports(tmp_path: Path):
    """
    A module run by a hook or skill, which sourced the plugin's configuration, runs that
    plugin's scripts wherever the package itself is installed.
    """
    assert (
        plugin_root_resolved_with({BasstlerVariable.PLUGIN_ROOT: str(tmp_path)})
        == tmp_path
    )


def test_the_plugin_scripts_are_under_its_hooks_directory():
    """
    Every script the package runs is one of the plugin's hooks.
    """
    assert {
        location.parent
        for location in PluginLocation
        if location not in (PluginLocation.ROOT, PluginLocation.HOOKS)
    } == {PluginLocation.HOOKS.value}
