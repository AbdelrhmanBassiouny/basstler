"""
Tests for basstler.plan.repository_rules: the rules every plan of a repository follows.
"""

from __future__ import annotations

import pydantic
import pytest

from basstler.plan.repository_rules import (
    RepositoryRule,
    RepositoryRules,
    UnknownRepositoryRuleError,
)

from ..constants.paths import DatasetLocation

# %% rules

FIRST_RULE = RepositoryRule(
    identifier="reliable",
    text="A failure is reported where the user sees it, never silent.",
)
"""
The first rule of the dataset's rules file.
"""

SECOND_RULE = RepositoryRule(
    identifier="deterministic", text="The same inputs give the same result."
)
"""
The second rule of the dataset's rules file.
"""


@pytest.fixture
def rules() -> RepositoryRules:
    """
    :return: The rules the dataset's file holds.
    """
    return RepositoryRules.from_text(DatasetLocation.REPOSITORY_RULES.read_text())


# %% reading


class TestReadingRules:
    def test_the_file_is_read_in_order(self, rules: RepositoryRules):
        assert rules.rules == [FIRST_RULE, SECOND_RULE]

    def test_no_file_means_no_rules(self):
        assert RepositoryRules.from_text("") == RepositoryRules()

    def test_two_rules_with_one_id_are_refused(self):
        with pytest.raises(pydantic.ValidationError):
            RepositoryRules.from_text(
                DatasetLocation.REPOSITORY_RULES_DUPLICATE_IDENTIFIER.read_text()
            )

    def test_rendered_rules_read_back_the_same(self, rules: RepositoryRules):
        assert RepositoryRules.from_text(rules.render()) == rules


# %% editing


class TestEditingRules:
    def test_a_new_rule_is_appended(self, rules: RepositoryRules):
        added = RepositoryRule(identifier="secure", text="Least privilege.")

        assert rules.with_rule(added).rules == [FIRST_RULE, SECOND_RULE, added]

    def test_a_rule_with_a_known_id_is_replaced_in_place(self, rules: RepositoryRules):
        reworded = RepositoryRule(identifier=FIRST_RULE.identifier, text="Reworded.")

        assert rules.with_rule(reworded).rules == [reworded, SECOND_RULE]

    def test_a_removed_rule_is_gone(self, rules: RepositoryRules):
        assert rules.without(FIRST_RULE.identifier).rules == [SECOND_RULE]

    def test_removing_an_unknown_rule_is_refused(self, rules: RepositoryRules):
        with pytest.raises(UnknownRepositoryRuleError):
            rules.without("missing")
