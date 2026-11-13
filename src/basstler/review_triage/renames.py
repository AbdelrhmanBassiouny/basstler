"""
The identifiers a pull request renames throughout, and their application to code and
prose.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import cached_property

# %% one rename


@dataclass(frozen=True)
class Rename:
    """
    One identifier replaced by another wherever it occurs.
    """

    old: str
    """
    The identifier the base commit uses.
    """

    new: str
    """
    The identifier the head commit uses in its place.
    """

    found_by: str
    """
    The label of the rename source that found it.
    """


@dataclass(frozen=True)
class RenameDecisions:
    """
    What one rename source decides: renames it accepts and old identifiers it rejects.
    """

    accepted: tuple[Rename, ...] = ()
    """
    The renames the source finds.
    """

    rejected: frozenset[str] = frozenset()
    """
    Old identifiers whose rename, found by an earlier source, is not a rename.
    """


# %% every rename of a pull request

DOTTED_NAME_SEPARATOR = "."
"""
What separates the components of a dotted module or attribute path.
"""


@dataclass(frozen=True)
class RenameMap:
    """
    The renames applied together, each identifier mapped to at most one replacement.
    """

    renames: tuple[Rename, ...] = ()
    """
    The renames, ordered by their old identifier.
    """

    @classmethod
    def of(cls, decisions: Iterable[RenameDecisions]) -> RenameMap:
        """
        :param decisions: The decisions of each rename source, a later source's
            outranking an earlier one's.
        :return: The renames left once every decision is applied.
        """
        renames: dict[str, Rename] = {}
        for decision in decisions:
            for old in decision.rejected:
                renames.pop(old, None)
            renames |= {rename.old: rename for rename in decision.accepted}
        return cls(tuple(renames[old] for old in sorted(renames)))

    @cached_property
    def replacements(self) -> dict[str, str]:
        """
        The new identifier of each old one.
        """
        return {rename.old: rename.new for rename in self.renames}

    @cached_property
    def word_pattern(self) -> re.Pattern[str] | None:
        """
        Matches any old identifier as a whole word, ``None`` when there are no renames.
        """
        if not self.renames:
            return None
        alternatives = sorted(self.replacements, key=len, reverse=True)
        return re.compile(r"\b(?:" + "|".join(map(re.escape, alternatives)) + r")\b")

    def renamed_identifier(self, identifier: str) -> str:
        """
        :param identifier: A name, or a dotted path of names.
        :return: It with every component that is renamed replaced.
        """
        return DOTTED_NAME_SEPARATOR.join(
            self.replacements.get(component, component)
            for component in identifier.split(DOTTED_NAME_SEPARATOR)
        )

    def renamed_prose(self, text: str) -> str:
        """
        :param text: Prose, such as a docstring or a comment.
        :return: It with every old identifier occurring as a whole word replaced.
        """
        if self.word_pattern is None:
            return text
        return self.word_pattern.sub(
            lambda match: self.replacements[match.group()], text
        )


# %% candidate renames found in a diff


@dataclass
class RenameCandidates:
    """
    Identifier substitutions seen in a pull request's diff, kept only while every one
    of them replaces an identifier by the same new identifier.
    """

    replacements: dict[str, set[str]] = field(default_factory=dict)
    """
    Every new identifier each old identifier was seen replaced by.
    """

    def add(self, old: str, new: str) -> None:
        """
        Record that *old* was replaced by *new* at one place.

        :param old: The identifier in the base version.
        :param new: The identifier in its place in the head version.
        """
        self.replacements.setdefault(old, set()).add(new)

    def consistent(self) -> dict[str, str]:
        """
        :return: The replacement of each old identifier only ever replaced by one.
        """
        return {
            old: next(iter(news))
            for old, news in self.replacements.items()
            if len(news) == 1
        }
