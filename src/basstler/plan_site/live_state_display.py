"""
How the plan page's script shows a pull request's live state once GitHub answers.
"""

from __future__ import annotations

from dataclasses import dataclass

from basstler.plan.model import ItemStatus
from basstler.plan_site.chip_tone import ChipTone
from basstler.plan_site.plan import Item
from basstler.pull_request_state import LiveState

# %% the script's display data


@dataclass(frozen=True)
class LiveStateDisplay:
    """
    The labels, tones and classes the plan page's script gives a chip or card, the same
    ones the build renders them with.
    """

    @property
    def state_chips(self) -> dict[str, dict[str, str]]:
        """
        :return: Each live state's chip label and tone, keyed by the state's name.
        """
        return {
            state.name: {
                "label": state.display_label,
                "tone": ChipTone.of_live_state(state).value,
            }
            for state in LiveState
        }

    @property
    def done_status(self) -> dict[str, str]:
        """
        :return: How a card shows it is done: its status, chip label, tone and class.
        """
        return {
            "status": ItemStatus.DONE.value,
            "label": ItemStatus.DONE.value.capitalize(),
            "tone": ChipTone.of_status(ItemStatus.DONE).value,
            "css_class": Item.status_css_class(ItemStatus.DONE),
        }

    @property
    def chip_tones(self) -> list[str]:
        """
        :return: Every chip tone's class, which the script removes before setting one.
        """
        return [tone.value for tone in ChipTone]
