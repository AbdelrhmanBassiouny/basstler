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
    One identifier, or one dotted module path, replaced by another wherever it occurs.
    """

    old: str
    """
    The identifier the base commit uses, dotted when it names a module.
    """

    new: str
    """
    The identifier the head commit uses in its place.
    """

    found_by: str
    """
    The label of the rename source that found it.
    """

    is_file_path: bool = False
    """
    Whether both sides are file paths, which never occur inside code.
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
    def identifier_renames(self) -> tuple[Rename, ...]:
        """
        The renames of identifiers and module paths, those of file paths left out.
        """
        return tuple(rename for rename in self.renames if not rename.is_file_path)

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
        alternatives = [
            self.whole_word_pattern(rename)
            for rename in sorted(
                self.renames, key=lambda rename: len(rename.old), reverse=True
            )
        ]
        return re.compile("|".join(alternatives))

    @staticmethod
    def whole_word_pattern(rename: Rename) -> str:
        """
        :param rename: A rename.
        :return: What matches its old side only where it stands whole; a file path
            never as the end of a longer path.
        """
        if not rename.is_file_path:
            return rf"\b{re.escape(rename.old)}\b"
        return rf"(?<![\w/.-]){re.escape(rename.old)}(?![\w/-])"

    @cached_property
    def renamed_modules(self) -> tuple[str, ...]:
        """
        The old dotted module paths, longest first.
        """
        return tuple(
            sorted(
                (
                    rename.old
                    for rename in self.renames
                    if DOTTED_NAME_SEPARATOR in rename.old and not rename.is_file_path
                ),
                key=len,
                reverse=True,
            )
        )

    def renamed_identifier(self, identifier: str) -> str:
        """
        :param identifier: A name, or a dotted path of names.
        :return: It with its longest renamed module prefix replaced, then every
            other component that is renamed.
        """
        prefix = ""
        for module in self.renamed_modules:
            if identifier == module or identifier.startswith(
                module + DOTTED_NAME_SEPARATOR
            ):
                prefix = self.replacements[module]
                identifier = identifier.removeprefix(module)
                break
        return prefix + DOTTED_NAME_SEPARATOR.join(
            self.replacements.get(component, component)
            for component in identifier.split(DOTTED_NAME_SEPARATOR)
        )

    def original_identifier(self, identifier: str) -> str:
        """
        :param identifier: A name the head commit uses.
        :return: The name the base commit used in its place.
        """
        return next(
            (rename.old for rename in self.renames if rename.new == identifier),
            identifier,
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
