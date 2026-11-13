"""
Finding the renames a pull request makes throughout from its diff alone.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from enum import IntEnum

from basstler.class_property import classproperty
from basstler.maintenance.git_commands import GitCommandRunner
from basstler.review_triage.comparison import PythonComparison
from basstler.review_triage.pull_request import PullRequestChanges
from basstler.review_triage.python_source import PythonSource
from basstler.review_triage.rename_sources import RenameSource
from basstler.review_triage.renames import Rename, RenameCandidates, RenameDecisions

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


class RenameDetection(RenameSource):
    """
    Detects a rename as an identifier the diff consistently replaces by another, where
    the old identifier is gone from the head commit and the new one absent from the
    base commit.
    """

    @classproperty
    def label(cls) -> str:
        return "diff"

    def decisions(self, changes: PullRequestChanges) -> RenameDecisions:
        candidates = RenameCandidates()
        for change in changes.files:
            if PythonComparison().applies_to(change):
                self.collect(
                    PythonSource(change.base_text),
                    PythonSource(change.head_text),
                    candidates,
                )
        base = CommitTree(changes.commits.git, changes.commits.base_commit)
        head = CommitTree(changes.commits.git, changes.commits.head_commit)
        return RenameDecisions(
            tuple(
                Rename(old, new, self.label)
                for old, new in sorted(candidates.consistent().items())
                if not head.mentions(old) and not base.mentions(new)
            )
        )

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
