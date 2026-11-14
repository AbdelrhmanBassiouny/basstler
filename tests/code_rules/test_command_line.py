"""
Tests for the ``basstler code-rules`` commands.
"""

from __future__ import annotations

import json

import pytest

from basstler.code_rules.command_line import (
    CodeRulesExitCode,
    check,
    generate_agents_instructions,
    list_crossings,
    report_new_crossings,
)
from basstler.code_rules.instructions import AgentsInstructions
from basstler.code_rules.package_boundaries import (
    PackageBoundaryChecker,
    PackageCrossings,
)

from ..constants.paths import DocstringSnippet, ProseSnippet

# %% checking


def test_checking_fails_when_code_breaks_a_rule():
    """
    An overlong comment block breaks a checked rule.
    """
    assert check([ProseSnippet.COMMENT_BLOCKS], all_lines=True) == (
        CodeRulesExitCode.CHANGES_NEEDED
    )


def test_checking_passes_when_nothing_breaks_a_rule():
    """
    A documented module with short docstrings breaks no checked rule.
    """
    assert check([DocstringSnippet.DOCUMENTED_MODULE], all_lines=True) == (
        CodeRulesExitCode.SUCCESS
    )


# %% boundary crossings


def test_the_listing_holds_every_crossing_the_package_has(tmp_path):
    """
    The listing the command writes holds the crossings the checker finds.
    """
    listing = tmp_path / "crossings.json"

    list_crossings(listing)

    assert PackageCrossings.from_json(json.loads(listing.read_text())) == (
        PackageBoundaryChecker().package_crossings()
    )


def test_a_package_compared_with_its_own_commit_has_no_new_crossing():
    """
    Against the commit checked out, the base holds every crossing the package has.
    """
    assert report_new_crossings("HEAD") == CodeRulesExitCode.SUCCESS


# %% generating AGENTS.md


@pytest.fixture
def instructions(tmp_path, monkeypatch) -> AgentsInstructions:
    """
    :return: The ``AGENTS.md`` of an empty directory, made the working directory.
    """
    monkeypatch.chdir(tmp_path)
    return AgentsInstructions.of_repository(tmp_path)


def test_generating_writes_a_missing_file(instructions):
    """
    A missing ``AGENTS.md`` is written, and the command reports the change.
    """
    assert generate_agents_instructions() == CodeRulesExitCode.CHANGES_NEEDED
    assert instructions.is_current()


def test_generating_a_current_file_changes_nothing(instructions):
    """
    A current ``AGENTS.md`` is left as it is.
    """
    instructions.write()

    assert generate_agents_instructions() == CodeRulesExitCode.SUCCESS


def test_verifying_a_stale_file_fails_without_writing_it(instructions):
    """
    Verifying reports a stale ``AGENTS.md`` and leaves it stale.
    """
    instructions.path.write_text("stale")

    assert generate_agents_instructions(verify=True) == (
        CodeRulesExitCode.CHANGES_NEEDED
    )
    assert not instructions.is_current()
