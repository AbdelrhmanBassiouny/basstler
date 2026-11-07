"""
Tests for finding the names a document cites that this release no longer ships.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import basstler.plan.manifest_tools
import basstler.plan.size_limits
from basstler.document_references import (
    PACKAGE_NAME,
    CitedNames,
    RetiredSkill,
    ShippedModules,
)

from .constants.paths import DatasetLocation, RepositoryLocation, SkillDirectory

# %% personal notes written against another release


def test_notes_naming_moved_modules_and_a_retired_skill_report_each_of_them():
    notes = DatasetLocation.NOTES_CITING_RETIRED_NAMES.read_text()

    stale = CitedNames.in_text(notes).stale(ShippedModules.installed())

    assert [reference.cited for reference in stale] == [
        RetiredSkill.PLAN_DASHBOARD.invoked_as,
        f"{PACKAGE_NAME}.no_such_module",
        f"{PACKAGE_NAME}.plan_manifest_tools",
        f"{PACKAGE_NAME}.plan_size_limits",
    ]


def test_a_retired_skill_is_reported_with_what_replaced_it():
    notes = DatasetLocation.NOTES_CITING_RETIRED_NAMES.read_text()

    stale = CitedNames.in_text(notes).stale(ShippedModules.installed())

    assert stale[0].replacement == RetiredSkill.PLAN_DASHBOARD.value.replacement


def test_the_next_major_release_no_longer_reports_a_retired_skill():
    notes = CitedNames.in_text(DatasetLocation.NOTES_CITING_RETIRED_NAMES.read_text())
    installed = ShippedModules.installed()
    next_major = replace(
        installed, major_version=RetiredSkill.PLAN_DASHBOARD.value.major_version + 1
    )

    reported = [reference.cited for reference in notes.stale(next_major)]

    assert reported == [
        reference.cited
        for reference in notes.stale(installed)
        if reference.cited != RetiredSkill.PLAN_DASHBOARD.invoked_as
    ]


@pytest.mark.parametrize(
    ("cited", "moved_to"),
    [
        ("plan_manifest_tools", basstler.plan.manifest_tools.__name__),
        ("plan_size_limits", basstler.plan.size_limits.__name__),
    ],
)
def test_a_module_moved_into_a_subpackage_is_found_where_it_moved(
    cited: str, moved_to: str
):
    assert ShippedModules.installed().replacement_for(cited) == moved_to


def test_a_module_nothing_replaces_has_no_replacement():
    assert ShippedModules.installed().replacement_for("no_such_module") is None


def test_notes_naming_only_shipped_names_report_nothing():
    notes = DatasetLocation.NOTES_CITING_SHIPPED_NAMES.read_text()

    assert CitedNames.in_text(notes).stale(ShippedModules.installed()) == []


# %% this repository's own documents


def plugin_documents() -> list[Path]:
    """
    :return: Every document and script the plugin ships, which sessions read or run.
    """
    return sorted(
        path
        for pattern in ("*.md", "*.sh")
        for path in RepositoryLocation.PLUGIN.value.rglob(pattern)
    )


@pytest.mark.parametrize(
    "document",
    plugin_documents(),
    ids=lambda path: str(path.relative_to(RepositoryLocation.PLUGIN.value)),
)
def test_no_plugin_document_cites_a_name_this_release_does_not_ship(document: Path):
    cited = CitedNames.in_text(document.read_text())

    assert cited.stale(ShippedModules.installed()) == []


@pytest.mark.parametrize("skill", list(RetiredSkill))
def test_a_retired_skill_is_not_shipped(skill: RetiredSkill):
    skill_directory = (
        RepositoryLocation.PLUGIN.value
        / SkillDirectory.DIRECTORY
        / skill.invoked_as.removeprefix("/")
    )

    assert not skill_directory.exists()


@pytest.mark.parametrize("skill", list(RetiredSkill))
def test_a_retired_skill_is_removed_once_its_major_release_is_superseded(
    skill: RetiredSkill,
):
    assert skill.value.major_version == ShippedModules.installed().major_version
