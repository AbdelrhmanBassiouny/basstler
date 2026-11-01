"""
Tests that the manifest-staleness rule reaches every skill it binds.

The rule lives in one document, referenced by each skill rather than restated in it, so
what needs guarding is the reference: a skill that writes plan data without citing the
rule is exactly the drift the document exists to end.

Which skills are bound is *derived* from what they do - a skill that runs a plan-writing
script is bound by that fact - rather than listed here, so a skill added later is
covered without this file being edited.
"""

from __future__ import annotations

import re
import subprocess
from enum import StrEnum
from pathlib import Path

import pytest

from basstler.locations import PluginLocation
from basstler.shell_configuration import ShellConfigurationFunction

from ..constants.paths import RepositoryLocation, SkillDirectory, SkillFile

# %% shell constants


class ShellConstant(StrEnum):
    """
    The constants of the plugin's shell configuration the rule is reached through.
    """

    BLOCKER_OWNER = "MAINTENANCE_BLOCKER_OWNER"
    """
    Who stack maintenance writes its blockers under, which the writer and the clearer of
    one have to agree on exactly.
    """

    def value_in_configuration(self) -> str:
        """
        :return: This constant's value, as sourcing the plugin's shell configuration sets
            it.
        """
        configuration = (
            RepositoryLocation.HOOKS
            / PluginLocation.PERSONAL_NOTES_CONFIGURATION_SCRIPT.name
        )
        result = subprocess.run(
            ["bash", "-c", f'source "{configuration}"; printf "%s" "${{{self}}}"'],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout


class PlanWritingScript(StrEnum):
    """
    The constants naming a script that writes plan data, so a skill invoking one is
    writing plan state and is bound by the rule.
    """

    ITEM_BOOTSTRAP = "PLAN_ITEM_BOOTSTRAP_MODULE"
    """
    The module that records, updates, blocks and unblocks items.
    """

    SAVE_PLAN = "SAVE_PLAN_SCRIPT"
    """
    The hook that saves an edited manifest.
    """

    WRITE_PERSONAL_NOTES_FILE = "WRITE_PERSONAL_NOTES_FILE_SCRIPT"
    """
    How the dashboard refresh pushes its own manifest corrections, which is a plan-data
    write like any other.
    """


# %% reading the documents


def staleness_document() -> str:
    """
    :return: The rule document itself.
    """
    return (
        RepositoryLocation.PLUGIN / SkillDirectory.MANIFEST_STALENESS_DOCUMENT
    ).read_text()


def linked_documents(skill: Path) -> set[Path]:
    """
    :return: Every file the skill's instructions link to with a relative Markdown link,
        resolved against the skill's own directory.
    """
    return {
        (skill.parent / target).resolve()
        for target in re.findall(r"\]\(([^)#\s]+)\)", skill.read_text())
    }


def skills_writing_plan_data() -> list[Path]:
    """
    :return: Every skill's instructions that run a script which writes plan data, in a
        stable order.
    """
    return sorted(
        instructions
        for instructions in (RepositoryLocation.PLUGIN / SkillDirectory.DIRECTORY).glob(
            f"*/{SkillFile.INSTRUCTIONS}"
        )
        if any(script in instructions.read_text() for script in PlanWritingScript)
    )


# %% the rule's reach


@pytest.mark.parametrize(
    "skill", skills_writing_plan_data(), ids=lambda skill: skill.parent.name
)
def test_a_skill_that_writes_plan_data_cites_the_staleness_rule(skill: Path):
    document = RepositoryLocation.PLUGIN / SkillDirectory.MANIFEST_STALENESS_DOCUMENT

    assert document.resolve() in linked_documents(skill)


def test_the_rule_names_the_blocker_owner_through_its_constant():
    """
    A blocker written under one name and cleared under another would accumulate forever,
    so the document cites the one constant rather than spelling the name out.
    """
    assert ShellConstant.BLOCKER_OWNER.value_in_configuration() != ""
    assert ShellConstant.BLOCKER_OWNER in staleness_document()


def test_the_rule_links_the_plan_site_page_instead_of_a_republish():
    """
    Every manifest write is a push the plan site rebuilds from, so what the rule leaves
    to the session is the page's address, read through the one function that builds it.
    """
    assert ShellConfigurationFunction.PLAN_SITE_PAGE_URL in staleness_document()


def test_the_rule_names_no_plan_of_its_own():
    document = staleness_document()
    placeholders = set(re.findall(r"<([a-z-]+)>", document))

    assert "plan-id" in placeholders
    assert not re.search(r"plans/(?!<)[a-z][a-z0-9-]*/", document)
