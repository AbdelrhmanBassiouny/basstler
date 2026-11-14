"""
The Claude models a plan item can recommend.
"""

from __future__ import annotations

from enum import StrEnum


class ModelAlias(StrEnum):
    """
    A Claude Code model alias, which always resolves to the newest model of its family.
    """

    OPUS = "opus"
    """
    The most capable family.
    """

    SONNET = "sonnet"
    """
    The balanced family.
    """

    HAIKU = "haiku"
    """
    The fastest family.
    """

    @property
    def label(self) -> str:
        """
        The alias as a model picker shows it.
        """
        return self.value.capitalize()
