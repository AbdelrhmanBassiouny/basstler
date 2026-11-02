"""
Tests for the rules and the ``AGENTS.md`` generated from them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from basstler import locations
from basstler.code_rules import rules
from basstler.code_rules.commands import CodeRulesCommand
from basstler.code_rules.instructions import AgentsInstructions
from basstler.code_rules.rule import CodeReference, Section
from basstler.code_rules.rule_module import RuleModule
from basstler.code_rules.rules.code_quality import DocumentationRules
from basstler.exceptions import DataclassException

from ..constants.paths import RepositoryLocation, RuleSectionsFile
from ..dataset.code_rules.rule_sections import (
    DesignPrinciplesRules,
    ErrorsRules,
    ReleasesThroughCIRules,
    VerificationRules,
)

# %% sections


@pytest.fixture
def repository_sections() -> list[type[Section]]:
    """
    :return: The repository's top-level sections.
    """
    return RuleModule(rules).sections


def test_the_file_lists_the_rules_of_its_sections_under_their_headings(tmp_path):
    """
    Rules are listed under their sections' headings, details nested below their rule,
    and a checked rule names the command that checks it.
    """
    instructions = AgentsInstructions(
        tmp_path, [DesignPrinciplesRules, VerificationRules]
    )

    assert instructions.text == RuleSectionsFile.EXPECTED_TEXT.read_text().format(
        source_path=DesignPrinciplesRules.source_path,
        generate_command=CodeRulesCommand.AGENTS_MD.invocation,
        check_command=CodeRulesCommand.CHECK.invocation,
    )


def test_a_section_is_nested_in_the_section_its_parent_returns():
    """
    A section's parent is the section its :attr:`Section.parent` override returns.
    """
    assert ErrorsRules.parent is DesignPrinciplesRules


def test_the_subsections_of_a_section_are_the_sections_nested_in_it():
    """
    A section's subsections are the sections naming it as their parent.
    """
    assert DesignPrinciplesRules.subsections == [ErrorsRules]


def test_a_title_names_the_topic_keeping_acronyms_in_capitals():
    """
    A section's title is its name in words, without the ``Rules`` suffix.
    """
    assert ReleasesThroughCIRules.title == "Releases through CI"


def test_no_two_sibling_sections_share_a_title(repository_sections):
    """
    Every heading is unique among its siblings.
    """
    sibling_titles = [[section.title for section in repository_sections]]
    sibling_titles += [
        [subsection.title for subsection in section.subsections]
        for top_level_section in repository_sections
        for section in top_level_section.descendants
    ]

    assert all(len(titles) == len(set(titles)) for titles in sibling_titles)


def test_the_checkers_are_those_of_the_checked_rules():
    """
    The checkers the repository's rules declare, in the order the rules are listed.
    """
    assert RuleModule(rules).checkers == (
        DocumentationRules.DOCUMENT_EVERYTHING.checker,
        DocumentationRules.SHORT_DOCSTRINGS.checker,
    )


def test_the_repository_agents_file_is_generated_from_its_rules():
    """
    The committed ``AGENTS.md`` is what the rules generate.
    """
    assert AgentsInstructions.of_repository(RepositoryLocation.ROOT).is_current()


# %% code named by rules


def test_a_class_is_named_by_its_import_path():
    """
    A class is named by the module defining it and its qualified name.
    """
    assert CodeReference(DataclassException).path == (
        f"`{DataclassException.__module__}.{DataclassException.__qualname__}`"
    )


def test_a_module_is_named_by_its_import_path():
    """
    A module is named by its own name.
    """
    assert CodeReference(locations).path == f"`{locations.__name__}`"


def test_an_object_is_named_by_the_module_it_is_imported_from():
    """
    An object re-exported by another module is named by that module.
    """
    assert CodeReference(pytest.raises, pytest).path == (
        f"`{pytest.__name__}.{pytest.raises.__qualname__}`"
    )


# %% writing the file


def test_writing_replaces_the_file_with_the_rules(tmp_path: Path):
    """
    Writing makes a stale ``AGENTS.md`` current.
    """
    instructions = AgentsInstructions.of_repository(tmp_path)
    instructions.path.write_text("stale")

    instructions.write()

    assert instructions.is_current()
