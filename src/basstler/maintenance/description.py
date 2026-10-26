"""
A fork pull request's description: what a pass reads out of it and writes into it.
"""

from __future__ import annotations

from dataclasses import dataclass

from basstler.maintenance.constants import DescriptionPattern, MaintenanceText

# %% the description


@dataclass(frozen=True)
class PullRequestDescription:
    """
    A pull request's description, with the session link a pass reads out of it and the
    promotion section it records in it.
    """

    text: str
    """
    The description as written, empty when the pull request has none.
    """

    @property
    def session_link(self) -> str | None:
        """
        The first session link the description names, or ``None`` when it names none.
        """
        return DescriptionPattern.SESSION_LINK.first_in(self.text)

    @property
    def prose(self) -> str:
        """
        The description as its author wrote it, without the promotion section a pass
        recorded.
        """
        heading = DescriptionPattern.PROMOTION_HEADING.value.search(self.text)
        before = self.text if heading is None else self.text[: heading.start()]
        return before.rstrip()

    def with_promotion_link(self, url: str) -> str:
        """
        :param url: The link to record.
        :return: The description with *url* as its promotion section, replacing any
            section already there.
        """
        return f"{self.prose}\n\n{MaintenanceText.PROMOTION_HEADING}\n\n{url}\n"
