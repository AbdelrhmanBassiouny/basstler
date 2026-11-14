"""
Finding the renames a pull request makes throughout from its diff alone.
"""

from __future__ import annotations

import difflib
import tokenize

from basstler.class_property import classproperty
from basstler.review_triage.commit_tree import CommitTree
from basstler.review_triage.comparison import PythonComparison
from basstler.review_triage.pull_request import PullRequestChanges
from basstler.review_triage.python_source import PythonSource
from basstler.review_triage.rename_sources import RenameSource
from basstler.review_triage.renames import Rename, RenameCandidates, RenameDecisions

# %% detection


class RenameDetection(RenameSource):
    """
    Detects a rename as an identifier the diff consistently replaces by another, where
    the old identifier is gone from the head commit and the new one absent from the base
    commit.
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
        lines = difflib.SequenceMatcher(
            a=base.text.splitlines(), b=head.text.splitlines(), autojunk=False
        )
        for tag, base_start, base_end, head_start, head_end in lines.get_opcodes():
            if tag == "replace":
                RenameDetection.collect_tokens(
                    base.tokens_on_lines(base_start + 1, base_end + 1),
                    head.tokens_on_lines(head_start + 1, head_end + 1),
                    candidates,
                )

    @staticmethod
    def collect_tokens(
        base_tokens: tuple[tokenize.TokenInfo, ...],
        head_tokens: tuple[tokenize.TokenInfo, ...],
        candidates: RenameCandidates,
    ) -> None:
        """
        Add each identifier of a replaced block of lines that the head version puts in
        place of another to *candidates*.

        :param base_tokens: The block's significant tokens in the base version.
        :param head_tokens: Those of the lines replacing it in the head version.
        :param candidates: The substitutions found so far.
        """
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
