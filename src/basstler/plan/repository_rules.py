"""
The rules every plan of a repository follows, kept on the repository's notes branch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pydantic
import yaml
from pydantic.dataclasses import dataclass

from basstler.plan.exceptions import UnknownRepositoryRuleError

# %% rules


@dataclass(
    frozen=True,
    kw_only=True,
    config=pydantic.ConfigDict(validate_by_name=True, validate_by_alias=True),
)
class RepositoryRule:
    """
    One rule every plan of the repository follows.
    """

    identifier: str = pydantic.Field(alias="id")
    """
    The rule's short name, unique among the repository's rules.
    """

    text: str
    """
    What the rule says.
    """

    def to_mapping(self) -> dict[str, str]:
        """
        :return: The rule as the file and the brief spell it.
        """
        return {"id": self.identifier, "text": self.text}


@dataclass(frozen=True)
class RepositoryRules:
    """
    The rules of one repository, in the order its owner wrote them.
    """

    rules: list[RepositoryRule] = pydantic.Field(default_factory=list)
    """
    The rules, each with an id no other holds.
    """

    @pydantic.field_validator("rules")
    @classmethod
    def refuse_repeated_identifier(
        cls, rules: list[RepositoryRule]
    ) -> list[RepositoryRule]:
        """
        :param rules: The rules as read.
        :raises ValueError: If two rules share an id.
        :return: The same rules.
        """
        identifiers = [rule.identifier for rule in rules]
        repeated = sorted({i for i in identifiers if identifiers.count(i) > 1})
        if repeated:
            raise ValueError(f"rule ids used more than once: {', '.join(repeated)}")
        return rules

    @classmethod
    def from_text(cls, text: str) -> RepositoryRules:
        """
        :param text: The rules file's content; empty when the repository has none.
        :raises pydantic.ValidationError: If the file does not hold valid rules.
        :return: The rules it holds.
        """
        document: dict[str, Any] = yaml.safe_load(text) or {}
        return pydantic.TypeAdapter(cls).validate_python(document)

    @classmethod
    def from_file(cls, path: Path) -> RepositoryRules:
        """
        :param path: Where the rules file is, or would be.
        :raises pydantic.ValidationError: If the file does not hold valid rules.
        :return: The rules it holds; none if there is no such file.
        """
        return cls.from_text(path.read_text() if path.exists() else "")

    @property
    def identifiers(self) -> tuple[str, ...]:
        """
        The rules' ids, in order.
        """
        return tuple(rule.identifier for rule in self.rules)

    def render(self) -> str:
        """
        :return: The rules file's content.
        """
        return yaml.safe_dump(
            {"rules": [rule.to_mapping() for rule in self.rules]},
            sort_keys=False,
            allow_unicode=True,
            width=92,
        )

    def with_rule(self, rule: RepositoryRule) -> RepositoryRules:
        """
        :param rule: The rule to add, or to put in place of the one with its id.
        :return: These rules with it, keeping the replaced rule's position.
        """
        if rule.identifier not in self.identifiers:
            return RepositoryRules([*self.rules, rule])
        return RepositoryRules(
            [
                rule if held.identifier == rule.identifier else held
                for held in self.rules
            ]
        )

    def without(self, identifier: str) -> RepositoryRules:
        """
        :param identifier: The id of the rule to drop.
        :raises UnknownRepositoryRuleError: If no rule has that id.
        :return: These rules without it.
        """
        if identifier not in self.identifiers:
            raise UnknownRepositoryRuleError(identifier, self.identifiers)
        return RepositoryRules(
            [rule for rule in self.rules if rule.identifier != identifier]
        )
