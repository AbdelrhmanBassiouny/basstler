"""
The stages a progress card counts its items by.
"""

from __future__ import annotations

from enum import StrEnum

# %% the stages


class ProgressStage(StrEnum):
    """
    The stages a card measures its items' progress by, earliest first; each value is the
    word a card shows and the CSS class its bar segment carries.
    """

    STARTED = "started"
    """
    Work on the item has begun.
    """

    REVIEWED = "reviewed"
    """
    The item's pull request is past its author's review.
    """

    DONE = "done"
    """
    The item is done.
    """
