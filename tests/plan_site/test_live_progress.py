"""
Tests for the hub's and repository indexes' live progress: what their cards count once
GitHub lists each repository's pull requests in the browser.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable, Mapping
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Page, Request, Route, expect

from basstler.github.client import PageParameter
from basstler.maintenance.board import PullRequestField
from basstler.plan.model import ItemStatus
from basstler.plan_site.__main__ import HubSite, SiteFile
from basstler.plan_site.hub import PlanHub, SiteAddress
from basstler.locations import SiteTemplate
from basstler.plan_site.hub_page import (
    MAXIMUM_PULL_REQUESTS_PER_PAGE,
    HubPageVocabulary,
    ProgressCard,
    ProgressCardAttribute,
    SiteSummary,
    StageShare,
)
from basstler.plan_site.live_state_display import LiveStateDisplay
from basstler.plan_site.plan import ProgressStage
from basstler.pull_request_state import LiveState, PullRequestState
from basstler.render_common import TemplatePage
from basstler.repository import PullRequestReference, Repository

from ..constants.site import SitePlan, SiteSampleText
from ..github.pull_request_api import api_pull_request
from ..recorded_pull_requests import RecordedPullRequestSource
from .first_plan import ELSEWHERE_PULL_REQUEST, OPEN_PULL_REQUEST
from .test_build_site import NOTES_REPOSITORY

MERGED_NOW = {
    PullRequestField.STATE: PullRequestState.CLOSED.value,
    PullRequestField.MERGED_AT: "2026-11-05T10:00:00Z",
}
"""
What GitHub lists for a pull request merged since the build.
"""

ListingAnswer = Callable[[int], tuple[HTTPStatus, list[dict[str, Any]]]]
"""
What GitHub answers one page of a repository's pull request listing with, given the
page's number.
"""

# %% the built site


@pytest.fixture
def hub_site(
    pull_request_source: RecordedPullRequestSource, dataset_remotes: Path
) -> HubSite:
    """
    The whole site over the dataset's notes repository.
    """
    return HubSite(
        address=SiteAddress(SiteSampleText.SITE_URL),
        pull_request_source=pull_request_source,
        hub=PlanHub(
            registry=str(NOTES_REPOSITORY),
            repositories=[str(NOTES_REPOSITORY)],
            site_url=SiteSampleText.SITE_URL.value,
        ),
        remote_root=str(dataset_remotes),
    )


@pytest.fixture
def built(hub_site: HubSite, tmp_path: Path) -> SiteSummary:
    """
    The site built into *tmp_path*, as its summary.
    """
    return hub_site.build(tmp_path)


# %% opening a page


def open_with_listings(
    page: Page, address: Path, listings: Mapping[Repository, ListingAnswer]
) -> list[Request]:
    """
    Open a built page with GitHub answering each repository's pull request listing as
    given and nothing else on the network, and wait for the live count.

    :param page: The browser page to open it in.
    :param address: The built page's file.
    :param listings: How GitHub answers each repository's listing.
    :return: Every listing request the page made, in order.
    """
    requests: list[Request] = []

    def answer(listing: ListingAnswer):
        def fulfil(route: Route) -> None:
            requests.append(route.request)
            query = parse_qs(urlsplit(route.request.url).query)
            status, pull_requests = listing(int(query[PageParameter.PAGE][0]))
            route.fulfill(
                status=status,
                headers={"Access-Control-Allow-Origin": "*"},
                content_type="application/json",
                body=json.dumps(pull_requests),
            )

        return fulfil

    page.route(SiteSampleText.SITE_URL + "**", lambda route: route.abort())
    for repository, listing in listings.items():
        page.route(listing_matcher(repository), answer(listing))
    page.goto(address.as_uri())
    page.wait_for_selector(f"[{ProgressCardAttribute.FINISHED}]", state="attached")
    return requests


def listing_path(repository: Repository) -> str:
    """:return: The address path of *repository*'s pull request listing."""
    return f"/{repository.pull_requests_path}"


def listing_matcher(repository: Repository) -> Callable[[str], bool]:
    """:return: Whether an address is a page of *repository*'s pull request listing."""
    return lambda url: urlsplit(url).path == listing_path(repository)


def one_page(*pull_requests: dict[str, Any]) -> ListingAnswer:
    """
    :param pull_requests: The pull requests the listing's one page holds.
    :return: A listing answering its first page with *pull_requests*.
    """
    return lambda number: (HTTPStatus.OK, list(pull_requests) if number == 1 else [])


def refused(_: int) -> tuple[HTTPStatus, list[dict[str, Any]]]:
    """
    :return: GitHub refusing every page, as it does a private repository without a
        token.
    """
    return HTTPStatus.NOT_FOUND, []


def listings_with(open_pull_request: dict[str, Any]) -> dict[Repository, ListingAnswer]:
    """
    :param open_pull_request: What GitHub lists for the open item's pull request.
    :return: Each repository's listing, holding that pull request and the elsewhere
        item's pull request as it was built.
    """
    return {
        OPEN_PULL_REQUEST.repository: one_page(open_pull_request),
        ELSEWHERE_PULL_REQUEST.repository: refused,
    }


def progress_line(page: Page, card_selector: str):
    """:return: The progress label of the card matching *card_selector*."""
    return page.locator(card_selector).locator(f"[{ProgressCardAttribute.PROGRESS}]")


def stage_label(page: Page, card_selector: str, stage: ProgressStage):
    """:return: The *stage* share label of the card matching *card_selector*."""
    return page.locator(card_selector).locator(
        f'[{ProgressCardAttribute.STAGE_LABEL}="{stage}"]'
    )


def merged_since_build(card: ProgressCard) -> ProgressCard:
    """
    :param card: A card as built, counting the open item's draft pull request.
    :return: The same card once that pull request has merged.
    """
    return dataclasses.replace(card, done=card.done + 1, reviewed=card.reviewed + 1)


def hub_page(output: Path) -> Path:
    """:return: The built hub page."""
    return output / SiteFile.PAGE


def repository_page(output: Path) -> Path:
    """:return: The built notes repository's index."""
    return output / str(NOTES_REPOSITORY) / SiteFile.PAGE


REPOSITORY_CARD = f'.progress-card:has(h2:text-is("{NOTES_REPOSITORY}"))'
"""
The notes repository's card on the hub.
"""


# %% the counts GitHub's listing changes


def test_a_pull_request_merged_since_the_build_counts_on_the_hub(
    built: SiteSummary, browser_page: Page, tmp_path: Path
):
    merged = api_pull_request(OPEN_PULL_REQUEST, MERGED_NOW)

    open_with_listings(browser_page, hub_page(tmp_path), listings_with(merged))

    (repository,) = built.repositories
    expect(progress_line(browser_page, REPOSITORY_CARD)).to_have_text(
        merged_since_build(repository).progress_label
    )


def test_a_pull_request_merged_since_the_build_counts_on_the_repository_index(
    built: SiteSummary, browser_page: Page, tmp_path: Path
):
    merged = api_pull_request(OPEN_PULL_REQUEST, MERGED_NOW)
    (repository,) = built.repositories
    first_plan = next(plan for plan in repository.plans if plan.id == SitePlan.FIRST)

    open_with_listings(browser_page, repository_page(tmp_path), listings_with(merged))

    card = f'.progress-card:has(h2:text-is("{first_plan.title}"))'
    expected = merged_since_build(first_plan)
    expect(progress_line(browser_page, card)).to_have_text(expected.progress_label)
    reviewed = next(
        share
        for share in expected.stage_shares
        if share.stage is ProgressStage.REVIEWED
    )
    expect(stage_label(browser_page, card, ProgressStage.REVIEWED)).to_have_text(
        reviewed.label
    )


def test_a_card_whose_items_are_all_done_live_is_marked_complete(
    built: SiteSummary, browser_page: Page, tmp_path: Path
):
    merged = api_pull_request(OPEN_PULL_REQUEST, MERGED_NOW)
    elsewhere_merged = api_pull_request(ELSEWHERE_PULL_REQUEST, MERGED_NOW)
    (repository,) = built.repositories
    first_plan = next(plan for plan in repository.plans if plan.id == SitePlan.FIRST)

    open_with_listings(
        browser_page,
        repository_page(tmp_path),
        {
            OPEN_PULL_REQUEST.repository: one_page(merged),
            ELSEWHERE_PULL_REQUEST.repository: one_page(elsewhere_merged),
        },
    )

    card = browser_page.locator(f'.progress-card:has(h2:text-is("{first_plan.title}"))')
    expect(card).to_contain_class(ProgressCard.complete_css_class)


def test_a_listing_github_refuses_keeps_the_built_counts(
    built: SiteSummary, browser_page: Page, tmp_path: Path
):
    open_with_listings(
        browser_page,
        hub_page(tmp_path),
        {
            OPEN_PULL_REQUEST.repository: refused,
            ELSEWHERE_PULL_REQUEST.repository: refused,
        },
    )

    (repository,) = built.repositories
    expect(progress_line(browser_page, REPOSITORY_CARD)).to_have_text(
        repository.progress_label
    )


# %% how few requests the page makes


def test_each_repository_is_listed_with_one_request(
    built: SiteSummary, browser_page: Page, tmp_path: Path
):
    draft = api_pull_request(OPEN_PULL_REQUEST, {PullRequestField.DRAFT: True})

    requests = open_with_listings(
        browser_page, hub_page(tmp_path), listings_with(draft)
    )

    listed = sorted(urlsplit(request.url).path for request in requests)
    assert listed == sorted(
        listing_path(repository)
        for repository in (
            OPEN_PULL_REQUEST.repository,
            ELSEWHERE_PULL_REQUEST.repository,
        )
    )


def test_a_pull_request_on_a_later_page_is_read_from_it(
    built: SiteSummary, browser_page: Page, tmp_path: Path
):
    newer = [
        api_pull_request(PullRequestReference(OPEN_PULL_REQUEST.repository, number))
        for number in range(
            OPEN_PULL_REQUEST.number + MAXIMUM_PULL_REQUESTS_PER_PAGE,
            OPEN_PULL_REQUEST.number,
            -1,
        )
    ]
    merged = api_pull_request(OPEN_PULL_REQUEST, MERGED_NOW)
    pages = {1: newer, 2: [merged]}

    open_with_listings(
        browser_page,
        hub_page(tmp_path),
        {
            OPEN_PULL_REQUEST.repository: lambda number: (
                HTTPStatus.OK,
                pages.get(number, []),
            ),
            ELSEWHERE_PULL_REQUEST.repository: refused,
        },
    )

    (repository,) = built.repositories
    expect(progress_line(browser_page, REPOSITORY_CARD)).to_have_text(
        merged_since_build(repository).progress_label
    )


# %% the stages an item reaches


def test_an_item_not_started_without_a_pull_request_reaches_no_stage():
    stages = LiveStateDisplay().reached_stages
    assert stages[ItemStatus.NOT_STARTED][LiveState.NO_PULL_REQUEST] == []


def test_an_item_with_a_draft_pull_request_is_only_started():
    stages = LiveStateDisplay().reached_stages
    assert stages[ItemStatus.IN_PROGRESS][LiveState.OPEN_DRAFT] == [
        ProgressStage.STARTED
    ]


def test_an_item_whose_pull_request_merged_reaches_every_stage():
    stages = LiveStateDisplay().reached_stages
    assert stages[ItemStatus.IN_PROGRESS][LiveState.MERGED] == list(ProgressStage)


# %% how the script writes a share


@pytest.mark.parametrize(
    "percentage",
    [12.5, 13.5, 12.25, 12.35, 4.45, 100 / 3, 0.0, 100.0],
    ids=lambda percentage: f"{percentage:g}",
)
@pytest.mark.parametrize(
    "decimal_places",
    [StageShare.label_decimal_places, StageShare.width_decimal_places],
    ids=["label", "width"],
)
def test_the_script_writes_a_share_as_the_build_does(
    browser_page: Page, percentage: float, decimal_places: int
):
    script = TemplatePage.render_named_template(
        SiteTemplate.LIVE_PROGRESS_SCRIPT.name, vocabulary=HubPageVocabulary()
    )
    browser_page.add_script_tag(content=script)

    written = browser_page.evaluate(
        "([value, places]) => siteFormatHalfToEven(value, places)",
        [percentage, decimal_places],
    )

    assert written == f"{percentage:.{decimal_places}f}"
