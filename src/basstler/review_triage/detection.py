"""
Finding the renames a pull request makes throughout from its diff alone.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable
from dataclasses import dataclass
from enum import IntEnum

from basstler.maintenance.git_commands import GitCommandRunner
from basstler.review_triage.comparison import FileChange, PythonComparison
from basstler.review_triage.python_source import PythonSource
from basstler.review_triage.renames import RenameCandidates

# %% the tree search


class GitGrepExitCode(IntEnum):
    """
    What ``git grep`` exits with.
    """

    MATCH = 0
    """
    At least one line matched.
    """

    NO_MATCH = 1
    """
    Nothing matched.
    """


@dataclass(frozen=True)
class CommitTree:
    """
    The files of one commit, searched for identifiers.
    """

    git: GitCommandRunner
    """
    The checkout holding the commit.
    """

    commit: str
    """
    The commit searched.
    """

    def mentions(self, identifier: str) -> bool:
        """
        :param identifier: A name.
        :return: Whether any file of the commit holds it as a whole word.
        :raises GitCommandFailed: If the search itself fails.
        """
        search = self.git.attempt(
            "grep",
            "--quiet",
            "--word-regexp",
            "--fixed-strings",
            "-e",
            identifier,
            self.commit,
        )
        if search.exit_status == GitGrepExitCode.NO_MATCH:
            return False
        return search.raise_if_failed().succeeded


# %% detection


@dataclass(frozen=True)
class RenameDetection:
    """
    Detects a rename as an identifier the diff consistently replaces by another, where
    the old identifier is gone from the head commit and the new one absent from the
    base commit.
    """

    base: CommitTree
    """
    The commit the pull request starts from.
    """

    head: CommitTree
    """
    The commit the pull request ends at.
    """

    def detected(self, changes: Iterable[FileChange]) -> dict[str, str]:
        """
        :param changes: The files the pull request changes.
        :return: The new identifier of each old identifier the pull request renames.
        """
        candidates = RenameCandidates()
        for change in changes:
            if (
                change.is_binary
                or change.base_text is None
                or change.head_text is None
                or change.path.suffix not in PythonComparison.suffixes
            ):
                continue
            self.collect(
                PythonSource(change.base_text),
                PythonSource(change.head_text),
                candidates,
            )
        return {
            old: new
            for old, new in sorted(candidates.consistent().items())
            if not self.head.mentions(old) and not self.base.mentions(new)
        }

    @staticmethod
    def collect(
        base: PythonSource, head: PythonSource, candidates: RenameCandidates
    ) -> None:
        """
        Add each identifier the head version puts in place of another to *candidates*.

        :param base: The file's base version.
        :param head: The file's head version.
        :param candidates: The substitutions found so far.
        """
        base_tokens = base.significant_tokens
        head_tokens = head.significant_tokens
        matcher = difflib.SequenceMatcher(
            a=[token.string for token in base_tokens],
            b=[token.string for token in head_tokens],
            autojunk=False,
        )
        for tag, base_start, base_end, head_start, head_end in matcher.get_opcodes():
            if tag != "replace" or base_end - base_start != head_end - head_start:
                continue
            for base_token, head_token in zip(
                base_tokens[base_start:base_end],
                head_tokens[head_start:head_end],
                strict=True,
            ):
                if PythonSource.is_identifier(
                    base_token
                ) and PythonSource.is_identifier(head_token):
                    candidates.add(base_token.string, head_token.string)
