"""
The maintenance executor's hand-maintained values.

Everything here is a decision somebody made and may change again - the heading a promotion
link is written under, the label marking it sent. They are gathered in one module, each
in the enum of the values it is one of, so changing one is an edit rather than a search
through whichever module happens to read it.

Values a program derives for itself belong beside the code that derives them, not here.
"""

from __future__ import annotations

import re
from enum import Enum, IntEnum, StrEnum


class GitHubClient(StrEnum):
    """
    The executables the tooling reaches the GitHub API through, each named as it is on
    ``PATH``.
    """

    COMMAND_LINE = "gh"
    """
    GitHub's own command-line client, preferred where it is installed.
    """

    CURL = "curl"
    """
    The plain HTTP client the shell hooks fall back to, with a token, where there is no
    ``gh``.
    """


class DescriptionPattern(Enum):
    """
    What the tooling looks for in a pull request description.
    """

    SESSION_LINK = re.compile(r"https://claude\.ai/code/session_[A-Za-z0-9_-]+")
    """
    The session link a pull request description carries, which is the only channel for
    telling a branch's owner that their branch needs them.
    """

    def first_in(self, text: str | None) -> str | None:
        """
        :param text: The text to search, which may be absent.
        :return: The first match, or ``None`` if the text holds none.
        """
        if not text:
            return None
        found = self.value.search(text)
        return found.group(0) if found else None


class RetargetRefusal(IntEnum):
    """
    The two ways GitHub can refuse a base-branch retarget that a caller cannot act on
    but must fall back from. Any other status is a genuine failure.
    """

    CREDENTIAL_REFUSED = 403
    """
    This credential is refused the write.
    """

    STACK_MEMBER = 422
    """
    The pull request is a member of a GitHub Stack, which must be moved through native
    Stack mechanics instead of a plain base change.
    """


class RoutineText(StrEnum):
    """
    Text the routine writes onto GitHub, and later finds again by.
    """

    NEEDS_RESOLUTION_COMMENT_PREFIX = "🔴 ROUTINE - NEEDS RESOLUTION:"
    """
    Opens a comment reporting anything a branch's owner alone can resolve - a restack
    conflict or a pending reparent - so every one of them can be found at a glance.
    """

    PROMOTION_HEADING = "## Promote"
    """
    Heading the compare-and-create link is written under, in the fork pull request's own
    description - the summary that carried it is delivered once and then gone, and the
    description is still there a week later.
    """


class MergeableState(StrEnum):
    """
    The values GitHub reports as a pull request's ``mergeable_state``.

    Only :attr:`DIRTY` means a branch genuinely conflicts with its base; every other one
    means there are no conflicts, whatever else may be true of it.
    """

    DIRTY = "dirty"
    """
    The branch conflicts with its base.
    """

    CLEAN = "clean"
    """
    Mergeable, with every required check passing.
    """

    UNSTABLE = "unstable"
    """
    Mergeable, with a check that is not required failing.
    """

    BLOCKED = "blocked"
    """
    Mergeable once a required review or check passes.
    """

    BEHIND = "behind"
    """
    Mergeable once brought up to date with its base.
    """

    HAS_HOOKS = "has_hooks"
    """
    Mergeable, with pre-receive hooks configured.
    """

    DRAFT = "draft"
    """
    A draft, which cannot be merged until it is marked ready.
    """

    UNKNOWN = "unknown"
    """
    Not yet computed by GitHub.
    """
