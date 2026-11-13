"""
The names a plan page's templates and scripts spell its attributes, states and labels
with.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from basstler.plan_site.cards import (
    DraftRecheckAttribute,
    LiveStateAttribute,
    PlanTimeAttribute,
    RefreshSource,
)
from basstler.plan_site.chip_tone import ChipTone
from basstler.plan_site.site_vocabulary import LiveStateVocabulary

# %% the vocabulary


@dataclass(frozen=True)
class PlanPageVocabulary(LiveStateVocabulary):
    """
    The enumerations a plan page's HTML and its script share, so the page the build
    writes and the page the browser updates use the same attributes, states and labels.
    """

    chip_tone: type[ChipTone] = field(default=ChipTone, init=False)
    """
    The class each chip's colour comes from.
    """

    draft_recheck_attribute: type[DraftRecheckAttribute] = field(
        default=DraftRecheckAttribute, init=False
    )
    """
    The attributes that mark a dependency chip whose draft pull request the script re-
    checks.
    """

    live_state_attribute: type[LiveStateAttribute] = field(
        default=LiveStateAttribute, init=False
    )
    """
    The attributes that mark the cards, chips and counts the script updates.
    """

    plan_time_attribute: type[PlanTimeAttribute] = field(
        default=PlanTimeAttribute, init=False
    )
    """
    The attributes that mark the page's dates.
    """

    refresh_source: type[RefreshSource] = field(default=RefreshSource, init=False)
    """
    Where the page's refresh time came from.
    """
