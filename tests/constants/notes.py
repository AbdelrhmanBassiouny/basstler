"""
Branch names and CLAUDE.local.md sections the personal-notes suites share.
"""

from __future__ import annotations

import re
from enum import StrEnum

from basstler.setup_steps import PersonalNotesSetting


class ScratchBranch(StrEnum):
    """
    The branches a scratch repository is given besides a stack's own.
    """

    PERSONAL_NOTES = PersonalNotesSetting.BRANCH.default
    """
    The personal-notes branch name the hooks resolve to by default.
    """

    WORK = "some-work-branch"
    """
    The throwaway branch a scratch repository is left checked out on.
    """


class ClaudeLocalSection(StrEnum):
    """
    The marked sections the shell hooks write into, and read back out of,
    :attr:`PersonalNotesPath.LOCAL_INSTRUCTIONS`.
    """

    PULL_REQUEST_PROGRESS = "PR-PROGRESS"
    """
    The current branch's pull request progress notes.
    """

    PLAN_ITEM = "PLAN-ITEM"
    """
    The plan item the current branch is tracked by.
    """

    PLAN_MANIFEST = "PLAN-MANIFEST"
    """
    A plan's manifest, as edited for :file:`save-plan.sh`.
    """

    PLAN_ROADMAP = "PLAN-ROADMAP"
    """
    A plan's roadmap, as edited for :file:`save-plan.sh`.
    """

    def around(self, content: str, label: str | None = None) -> str:
        """
        :param content: The section's content, ending in a newline.
        :param label: What the opening marker names after its colon, if anything.
        :return: *content* between this section's markers.
        """
        opening = self if label is None else f"{self}: {label}"
        return f"<!-- BEGIN-{opening} -->\n{content}<!-- END-{self} -->\n"

    def within(self, text: str) -> str:
        """
        :param text: A document holding this section once.
        :return: The section's content, without its markers.
        """
        pattern = rf"<!-- BEGIN-{self}(?:: [^>]*)? -->\n(.*?)<!-- END-{self} -->"
        return re.search(pattern, text, re.DOTALL).group(1)


class ProgressBranch(StrEnum):
    """
    The branches progress notes are kept for in the pruning suites, each standing for
    one state its pull request can be in. The ones with a pull request are those
    :attr:`DatasetLocation.PULL_REQUESTS_BY_BRANCH` records.
    """

    OPEN = "open-work"
    """
    Its pull request is open.
    """

    REOPENED = "reopened-work"
    """
    One pull request of it was closed, and a later one is open.
    """

    MERGED = "merged-work"
    """
    Its pull request merged.
    """

    DELETED = "claude/deleted-work"
    """
    Its pull request merged and the branch was deleted.
    """

    UNOPENED = "unopened-work"
    """
    It has no pull request yet.
    """
