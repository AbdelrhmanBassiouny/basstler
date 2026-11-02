"""
How the chips on an item card are coloured.
"""

from __future__ import annotations

from enum import StrEnum

from basstler.plan.model import ItemStatus
from basstler.pull_request_state import LiveState
from basstler.upstream_reviews.vocabulary import RollupState

# %% chip colours


class ChipTone(StrEnum):
    """
    How a chip on an item card is coloured, by what its state means for the work; each
    value is the CSS class the stylesheet colours it by.
    """

    GOOD = "chip-good"
    """
    Landed or passing.
    """

    WARNING = "chip-warn"
    """
    Waiting on something that has not finished yet.
    """

    BAD = "chip-bad"
    """
    Failed, blocked, or closed without landing.
    """

    ACTIVE = "chip-info"
    """
    Being worked on.
    """

    READY = "chip-accent"
    """
    Ready for its reviewer.
    """

    IDLE = "chip-idle"
    """
    Not started, set aside, or with nothing to report.
    """

    @classmethod
    def of_status(cls, status: ItemStatus) -> ChipTone:
        """
        :param status: An item's status in its plan.
        :return: The tone its status chip carries.
        """
        match status:
            case ItemStatus.DONE:
                return cls.GOOD
            case ItemStatus.IN_PROGRESS:
                return cls.ACTIVE
            case ItemStatus.BLOCKED:
                return cls.BAD
            case ItemStatus.NOT_STARTED | ItemStatus.DEFERRED:
                return cls.IDLE

    @classmethod
    def of_live_state(cls, live_state: LiveState) -> ChipTone:
        """
        :param live_state: The live state of an item's pull request.
        :return: The tone its pull request chip carries.
        """
        match live_state:
            case LiveState.MERGED:
                return cls.GOOD
            case LiveState.OPEN_READY:
                return cls.READY
            case LiveState.OPEN_DRAFT:
                return cls.ACTIVE
            case LiveState.CLOSED_UNMERGED | LiveState.NOT_FOUND:
                return cls.BAD
            case LiveState.NO_PULL_REQUEST:
                return cls.IDLE

    @classmethod
    def of_check_state(cls, check_state: RollupState) -> ChipTone:
        """
        :param check_state: The verdict over a pull request's checks.
        :return: The tone its CI chip carries.
        """
        if check_state.failed:
            return cls.BAD
        match check_state:
            case RollupState.SUCCESS:
                return cls.GOOD
            case RollupState.PENDING | RollupState.EXPECTED:
                return cls.WARNING
            case _:
                return cls.IDLE
