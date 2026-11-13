"""
The links and dates at the top of a plan page.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from basstler.plan_site.hub import PlanHistory
from basstler.render_common import sanitize_http_url

# %% the page header


@dataclass(kw_only=True)
class PlanPageHeader:
    """
    Where a plan page sits on the site, where its plan is discussed, and when the plan
    and the page last changed.
    """

    tracking_url: str | None = None
    """
    The tracking issue's or pull request's ``html_url``, if the plan has one.
    """

    hub_url: str | None = None
    """
    The plan hub's URL, the first link of the page's breadcrumb.
    """

    index_url: str | None = None
    """
    The repository's own index page, the breadcrumb's second link.
    """

    history: PlanHistory | None = None
    """
    When the plan was created and last changed, ``None`` when its history is unknown.
    """

    built_at: datetime | None = None
    """
    When the site was built, which the page shows as its refresh time until the browser
    reads GitHub itself; ``None`` to leave it out.
    """

    def __post_init__(self) -> None:
        """
        Drop a breadcrumb link that is not an http(s) address.
        """
        self.hub_url = sanitize_http_url(self.hub_url)
        self.index_url = sanitize_http_url(self.index_url)
