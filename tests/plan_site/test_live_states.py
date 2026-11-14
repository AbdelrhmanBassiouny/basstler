"""
Tests for the plan page's live pull request states: what its script shows once GitHub
answers in the browser, and how it says when the page was last refreshed.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, Route, expect

from basstler.github.pull_request_record import (
    PullRequestField,
)
from basstler.github.pull_request_state import LiveState, PullRequestState
from basstler.github.repository import PullRequestReference
from basstler.plan.model import ItemStatus
from basstler.plan_site.__main__ import RepositorySite, SiteFile
from basstler.plan_site.cards import (
    DraftRecheckAttribute,
    LiveStateAttribute,
    PlanTimeAttribute,
    RefreshSource,
)
from basstler.plan_site.chip_tone import ChipTone
from basstler.plan.structure import Item

from ..constants.site import SitePlan, SiteSampleText
from ..github.pull_request_api import api_pull_request
from .first_plan import (
    ELSEWHERE_PULL_REQUEST,
    FIRST_PLAN,
    MERGED_PULL_REQUEST,
    OPEN_PULL_REQUEST,
)
from .test_build_site import NOTES_REPOSITORY

_, OPEN_ITEM, _ = FIRST_PLAN.items
"""
The first plan's item whose pull request is an open draft when the site is built.
"""

MERGED_NOW = {
    PullRequestField.STATE: PullRequestState.CLOSED.value,
    PullRequestField.MERGED_AT: "2026-11-05T10:00:00Z",
}
"""
What GitHub answers for a pull request merged since the build.
"""

# %% opening the page


def open_first_plan_page(
    page: Page,
    output: Path,
    answers: Mapping[PullRequestReference, tuple[HTTPStatus, dict[str, Any]]],
) -> None:
    """
    Open the first plan's built page, with GitHub answering each pull request as given
    and nothing else on the network, and wait for the re-check.

    :param page: The browser page to open it in.
    :param output: The built site's root directory.
    :param answers: The status and pull request GitHub answers each address with.
    """

    def answer(reference: PullRequestReference):
        status, pull_request = answers[reference]

        def fulfil(route: Route) -> None:
            route.fulfill(
                status=status,
                headers={"Access-Control-Allow-Origin": "*"},
                content_type="application/json",
                body=json.dumps(pull_request),
            )

        return fulfil

    page.route(SiteSampleText.SITE_URL + "**", lambda route: route.abort())
    for reference in answers:
        page.route(reference.api_url, answer(reference))
    page.goto(
        (output / str(NOTES_REPOSITORY) / SitePlan.FIRST / SiteFile.PAGE).as_uri()
    )
    page.wait_for_selector(f"[{DraftRecheckAttribute.FINISHED}]", state="attached")


def answers_with(
    open_pull_request: tuple[HTTPStatus, dict[str, Any]],
) -> dict[PullRequestReference, tuple[HTTPStatus, dict[str, Any]]]:
    """
    :param open_pull_request: What GitHub answers for the open item's pull request.
    :return: GitHub's answers, the other pull requests as they were built.
    """
    return {
        MERGED_PULL_REQUEST: (
            HTTPStatus.OK,
            api_pull_request(MERGED_PULL_REQUEST, MERGED_NOW),
        ),
        OPEN_PULL_REQUEST: open_pull_request,
        ELSEWHERE_PULL_REQUEST: (
            HTTPStatus.OK,
            api_pull_request(ELSEWHERE_PULL_REQUEST),
        ),
    }


def open_item_card(page: Page):
    """:return: The open item's card."""
    return page.locator(f"#{OPEN_ITEM.anchor}")


def open_item_chip(page: Page):
    """:return: The open item's pull request chip."""
    return open_item_card(page).locator(f"[{LiveStateAttribute.PULL_REQUEST}]")


def status_count(page: Page, status: ItemStatus):
    """:return: The page's count of *status*."""
    return page.locator(f'[{LiveStateAttribute.STATUS_COUNT}="{status.value}"]')


# %% the states GitHub answers with


def test_a_pull_request_marked_ready_shows_ready(
    site: RepositorySite, browser_page: Page, tmp_path: Path
):
    site.build(tmp_path)
    ready = api_pull_request(OPEN_PULL_REQUEST, {PullRequestField.DRAFT: False})

    open_first_plan_page(browser_page, tmp_path, answers_with((HTTPStatus.OK, ready)))

    chip = open_item_chip(browser_page)
    expect(chip).to_have_text(
        f"#{OPEN_PULL_REQUEST.number} · {LiveState.OPEN_READY.display_label}"
    )
    expect(chip).to_have_class(f"chip {ChipTone.of_live_state(LiveState.OPEN_READY)}")


def test_a_pull_request_merged_since_the_build_marks_its_item_done(
    site: RepositorySite, browser_page: Page, tmp_path: Path
):
    site.build(tmp_path)
    merged = api_pull_request(OPEN_PULL_REQUEST, MERGED_NOW)
    built = Path(tmp_path / str(NOTES_REPOSITORY) / SitePlan.FIRST / SiteFile.PAGE)
    browser_page.goto(built.as_uri())
    done_before = int(status_count(browser_page, ItemStatus.DONE).inner_text())

    open_first_plan_page(browser_page, tmp_path, answers_with((HTTPStatus.OK, merged)))

    expect(open_item_chip(browser_page)).to_have_text(
        f"#{OPEN_PULL_REQUEST.number} · {LiveState.MERGED.display_label}"
    )
    expect(open_item_card(browser_page)).to_have_class(
        f"item {Item.status_css_class(ItemStatus.DONE)}"
    )
    expect(status_count(browser_page, ItemStatus.DONE)).to_have_text(
        str(done_before + 1)
    )


def test_a_pull_request_closed_unmerged_shows_closed(
    site: RepositorySite, browser_page: Page, tmp_path: Path
):
    site.build(tmp_path)
    closed = api_pull_request(
        OPEN_PULL_REQUEST, {PullRequestField.STATE: PullRequestState.CLOSED.value}
    )

    open_first_plan_page(browser_page, tmp_path, answers_with((HTTPStatus.OK, closed)))

    expect(open_item_chip(browser_page)).to_have_text(
        f"#{OPEN_PULL_REQUEST.number} · {LiveState.CLOSED_UNMERGED.display_label}"
    )


# %% when the page was last refreshed


def test_a_page_github_answered_in_full_says_it_is_live(
    site: RepositorySite, browser_page: Page, tmp_path: Path
):
    site.build(tmp_path)
    draft = api_pull_request(OPEN_PULL_REQUEST, {PullRequestField.DRAFT: True})
    opened_at = datetime(2031, 2, 3, 4, 5, 6, tzinfo=UTC)
    browser_page.clock.set_fixed_time(opened_at)

    open_first_plan_page(browser_page, tmp_path, answers_with((HTTPStatus.OK, draft)))

    expect(browser_page.locator(f"[{PlanTimeAttribute.REFRESH_SOURCE}]")).to_have_text(
        RefreshSource.LIVE
    )
    refreshed = browser_page.locator(f"[{PlanTimeAttribute.REFRESHED}]")
    assert datetime.fromisoformat(refreshed.get_attribute("datetime")) == opened_at


def test_a_page_github_refused_says_it_shows_the_build(
    site: RepositorySite, browser_page: Page, tmp_path: Path
):
    site.build(tmp_path)

    open_first_plan_page(
        browser_page, tmp_path, answers_with((HTTPStatus.FORBIDDEN, {}))
    )

    expect(browser_page.locator(f"[{PlanTimeAttribute.REFRESH_SOURCE}]")).to_have_text(
        RefreshSource.REFUSED
    )
    expect(browser_page.locator(f"[{PlanTimeAttribute.REFRESHED}]")).to_have_attribute(
        "datetime", site.built_at.isoformat()
    )


def test_a_pull_request_github_does_not_show_keeps_its_built_state(
    site: RepositorySite, browser_page: Page, tmp_path: Path
):
    """
    GitHub answers a private repository's pull request with 404 to a viewer without a
    token, so a 404 says nothing about the pull request.
    """
    site.build(tmp_path)
    built = (tmp_path / str(NOTES_REPOSITORY) / SitePlan.FIRST / SiteFile.PAGE).as_uri()
    browser_page.goto(built)
    built_text = open_item_chip(browser_page).inner_text()

    open_first_plan_page(
        browser_page, tmp_path, answers_with((HTTPStatus.NOT_FOUND, {}))
    )

    expect(open_item_chip(browser_page)).to_have_text(built_text)
    expect(browser_page.locator(f"[{PlanTimeAttribute.REFRESH_SOURCE}]")).to_have_text(
        RefreshSource.REFUSED
    )
