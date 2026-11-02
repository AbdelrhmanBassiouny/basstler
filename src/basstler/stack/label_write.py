"""
The complete label set a pull request has to be written back with.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from basstler.stack.exceptions import ContradictoryLabelWriteError
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% label writes


@dataclass(frozen=True)
class LabelWrite:
    """
    The complete label set a pull request has to be written back with.

    GitHub's label write replaces the whole set rather than adding to it, so the labels
    a change leaves untouched still have to be sent. Computing them from the intended
    change alone is what silently strips the rest.
    """

    labels: tuple[str, ...]
    """
    Every label the pull request will carry once written, in the order it will carry
    them.
    """

    @classmethod
    def replacing(
        cls,
        current: Iterable[str],
        added: Iterable[str] = (),
        removed: Iterable[str] = (),
    ) -> LabelWrite:
        """
        Work out the full set that adding and removing labels leaves behind.

        :param current: The labels the pull request carries now.
        :param added: Labels it must carry afterwards.
        :param removed: Labels it must not carry afterwards.
        :return: The complete set to write.
        :raises ContradictoryLabelWriteError: If a label is both added and removed.
        """
        added, removed = tuple(added), tuple(removed)
        contradictory = tuple(label for label in added if label in removed)
        if contradictory:
            raise ContradictoryLabelWriteError(contradictory)
        kept = [label for label in current if label not in removed]
        return cls(tuple(kept + [label for label in added if label not in kept]))

    def print_labels(self) -> None:
        """
        Print the complete label set, one label per line.

        One per line rather than a separator-joined list, because a label may contain
        any character a separator could be.
        """
        for label in self.labels:
            logger.info(label)
