"""
Tests for basstler.plan.repository_rules_command: editing a repository's rules on its
notes branch.
"""

from __future__ import annotations

from pathlib import PurePosixPath

import pydantic
import pytest

from basstler.locations import ProjectLocation
from basstler.plan.repository_rules import RepositoryRule, RepositoryRules
from basstler.plan.repository_rules_command import (
    RepositoryRulesExitCode,
    import_rules,
    remove_rule,
    set_rule,
    show_rules,
)

from ..constants.paths import DatasetLocation
from ..scratch_repository import ScratchRepository
from ..personal_notes.test_branch import published_file

# %% the notes branch

RULES_FILE = PurePosixPath(ProjectLocation.PLAN_RULES)
"""
Where the rules file sits on the notes branch.
"""

STARTING_RULES = RepositoryRules.from_yaml(DatasetLocation.REPOSITORY_RULES.read_text())
"""
The rules the notes branch starts with.
"""


@pytest.fixture
def rules_repository(
    scratch_repository: ScratchRepository, monkeypatch: pytest.MonkeyPatch
) -> ScratchRepository:
    """
    :return: A scratch repository, entered, whose notes branch carries the starting
        rules.
    """
    scratch_repository.write("README.md", "scratch repo\n")
    scratch_repository.commit_everything("initial commit")
    scratch_repository.publish_notes_branch(
        {RULES_FILE: DatasetLocation.REPOSITORY_RULES.read_text()}
    )
    scratch_repository.resolve_notes_remote_to()
    monkeypatch.chdir(scratch_repository.project_root)
    return scratch_repository


def published_rules(repository: ScratchRepository) -> RepositoryRules:
    """
    :return: The rules the notes remote carries now.
    """
    return RepositoryRules.from_yaml(published_file(repository, RULES_FILE) or "")


# %% editing


class TestEditingRulesOnTheNotesBranch:
    """
    Each editing command pushes the rules it leaves to the notes remote.
    """

    def test_a_new_rule_is_pushed(self, rules_repository: ScratchRepository):
        added = RepositoryRule(identifier="secure", text="Least privilege.")

        status = set_rule(added.identifier, added.text)

        assert (status, published_rules(rules_repository)) == (
            RepositoryRulesExitCode.SUCCESS,
            STARTING_RULES.with_rule(added),
        )

    def test_a_removed_rule_is_pushed(self, rules_repository: ScratchRepository):
        gone = STARTING_RULES.rules[0]

        status = remove_rule(gone.identifier)

        assert (status, published_rules(rules_repository)) == (
            RepositoryRulesExitCode.SUCCESS,
            STARTING_RULES.without(gone.identifier),
        )

    def test_removing_an_unknown_rule_changes_nothing(
        self, rules_repository: ScratchRepository
    ):
        status = remove_rule("missing")

        assert (status, published_rules(rules_repository)) == (
            RepositoryRulesExitCode.UNKNOWN_RULE,
            STARTING_RULES,
        )

    def test_imported_rules_are_pushed(self, rules_repository: ScratchRepository):
        """
        Every rule of the imported file is set on the notes remote.
        """
        imported = RepositoryRules.from_file(DatasetLocation.REPOSITORY_RULES_IMPORT)

        status = import_rules(DatasetLocation.REPOSITORY_RULES_IMPORT)

        assert (status, published_rules(rules_repository)) == (
            RepositoryRulesExitCode.SUCCESS,
            STARTING_RULES.with_rules(imported),
        )

    def test_an_invalid_import_changes_nothing(
        self, rules_repository: ScratchRepository
    ):
        """
        A file that does not hold valid rules is refused before anything is pushed.
        """
        with pytest.raises(pydantic.ValidationError):
            import_rules(DatasetLocation.REPOSITORY_RULES_DUPLICATE_IDENTIFIER)

        assert published_rules(rules_repository) == STARTING_RULES


# %% showing


def test_the_rules_are_printed_as_the_file_renders_them(
    rules_repository: ScratchRepository, capsys: pytest.CaptureFixture[str]
):
    show_rules()

    assert capsys.readouterr().out.strip() == STARTING_RULES.render().strip()
