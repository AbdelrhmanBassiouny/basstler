"""
How a pass reads the upstream's open pull requests.
"""

from __future__ import annotations

from enum import StrEnum

from basstler.locations import ClaudeCodeVariable

# %% the route


class UpstreamReadRoute(StrEnum):
    """
    How a pass reads the upstream's open pull requests.
    """

    DIRECT = "direct"
    """
    Through the GitHub API, with the session's own credential.
    """

    ACTION = "action"
    """
    Through the fork's Action, with the runner's credential.
    """

    @classmethod
    def for_this_session(cls) -> UpstreamReadRoute:
        """
        :return: :attr:`ACTION` in a Claude Code cloud session, whose proxy refuses the
            upstream's API until the upstream is attached; :attr:`DIRECT` elsewhere.
        """
        if ClaudeCodeVariable.REMOTE.is_true():
            return cls.ACTION
        return cls.DIRECT
