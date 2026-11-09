"""
Tests for plan_site/plan_page_header.py: the links at the top of a plan page.
"""

from __future__ import annotations

from basstler.plan_site.plan_page_header import PlanPageHeader

from ..constants.site import SiteSampleText

# %% breadcrumb links


def test_a_header_keeps_http_breadcrumb_links():
    header = PlanPageHeader(
        hub_url=SiteSampleText.SITE_URL, index_url=SiteSampleText.SITE_URL
    )

    assert (header.hub_url, header.index_url) == (
        SiteSampleText.SITE_URL,
        SiteSampleText.SITE_URL,
    )


def test_a_header_drops_breadcrumb_links_that_are_not_http():
    header = PlanPageHeader(hub_url="javascript:alert(1)", index_url="data:text/html,x")

    assert (header.hub_url, header.index_url) == (None, None)
