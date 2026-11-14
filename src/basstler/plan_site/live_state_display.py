"""
How the site's scripts show and count a pull request's live state once GitHub answers.
"""

from __future__ import annotations

from dataclasses import dataclass

from basstler.github.pull_request_state import LiveState
from basstler.plan.model import ItemStatus
from basstler.plan_site.chip_tone import ChipTone
from basstler.plan.structure import Item, ProgressStage

# %% what a chip shows


@dataclass(frozen=True)
class ChipDisplay:
    """
    What a chip shows.
    """

    label: str
    """
    The chip's text.
    """

    tone: ChipTone
    """
    The chip's colour.
    """


@dataclass(frozen=True)
class DoneStatusDisplay(ChipDisplay):
    """
    How an item card shows it is done: its status chip, and what the card carries.
    """

    status: ItemStatus
    """
    The status the card is marked with.
    """

    css_class: str
    """
    The CSS class the card carries.
    """


# %% the script's display data


@dataclass(frozen=True)
class LiveStateDisplay:
    """
    The labels, tones, classes and stages the site's scripts give a chip or card, the
    same ones the build renders them with.
    """

    @property
    def state_chips(self) -> dict[LiveState, ChipDisplay]:
        """
        :return: Each live state's chip.
        """
        return {
            state: ChipDisplay(
                label=state.display_label, tone=ChipTone.of_live_state(state)
            )
            for state in LiveState
        }

    @property
    def done_status(self) -> DoneStatusDisplay:
        """
        :return: How a card shows it is done.
        """
        return DoneStatusDisplay(
            label=ItemStatus.DONE.value.capitalize(),
            tone=ChipTone.of_status(ItemStatus.DONE),
            status=ItemStatus.DONE,
            css_class=Item.status_css_class(ItemStatus.DONE),
        )

    @property
    def reached_stages(self) -> dict[ItemStatus, dict[LiveState, list[ProgressStage]]]:
        """
        :return: The stages an item reaches, by its status and then its live state.
        """
        reached: dict[ItemStatus, dict[LiveState, list[ProgressStage]]] = {}
        for status in ItemStatus:
            reached[status] = {}
            for state in LiveState:
                item = Item(title="", branch=None, track="", status=status)
                item.live_state = state
                reached[status][state] = item.reached_stages
        return reached

    @property
    def chip_tones(self) -> list[ChipTone]:
        """
        :return: Every chip tone's class, which the script removes before setting one.
        """
        return list(ChipTone)
