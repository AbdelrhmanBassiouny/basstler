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
    A pull request's description, with the session link and the promotion section a pass
    reads and records in it.
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
    def promotion_link(self) -> str | None:
        """
        The upstream create-link a pass recorded under the promotion heading, or
        ``None`` when the description has no such section.
        """
        _, heading, recorded = self.text.partition(MaintenanceText.PROMOTION_HEADING)
        words = recorded.split()
        return words[0] if heading and words else None

    @property
    def summary(self) -> str:
        """
        The first paragraph ahead of the promotion section, which prefills the upstream
        pull request; empty when there is none.
        """
        before, _, _ = self.text.partition(MaintenanceText.PROMOTION_HEADING)
        paragraphs = [block.strip() for block in before.split("\n\n") if block.strip()]
        return paragraphs[0] if paragraphs else ""

    def with_promotion_link(self, url: str) -> str:
        """
        :param url: The link to record.
        :return: The description with *url* as its promotion section, replacing any
            section already there.
        """
        before, _, _ = self.text.partition(MaintenanceText.PROMOTION_HEADING)
        return f"{before.rstrip()}\n\n{MaintenanceText.PROMOTION_HEADING}\n\n{url}\n"
