"""
Tests for the plan page's re-check of blocking draft pull requests: what the build
renders for it, and what the page's script does with GitHub's answer.
"""

from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Locator, Page, Route, expect

from basstler.dashboard.cards import DraftRecheckAttribute, StartNowAction
from basstler.dashboard.plan import Plan
from basstler.maintenance.board import PullRequestField
from basstler.plan_site.__main__ import PlanSource, RepositorySite, SiteFile
from basstler.pull_request_state import PullRequestRecord, PullRequestState

from ..constants.site import SitePlan, SiteSampleText
from ..recorded_pull_requests import RecordedPullRequestSource
from .test_build_site import (
    NOTES_REPOSITORY,
    OPEN_PULL_REQUEST,
    api_pull_request,
    page_of,
)

SECOND_PLAN = Plan.from_mapping(
    PlanSource.from_directory(SitePlan.SECOND.directory).manifest
)
"""
The plan whose one not-started item depends on the first plan's draft pull request.
"""

(HELD_BACK_ITEM,) = SECOND_PLAN.items
"""
That item.
"""


def start_action_of_held_back_item() -> StartNowAction:
    """
    :return: The action the held-back item starts with once its dependency is ready.
    """
    return StartNowAction(
        label="Start now",
        plan_id=SECOND_PLAN.id,
        item_identifier=HELD_BACK_ITEM.identifier,
    )


# %% what the build renders


def test_a_chip_waiting_on_a_draft_names_that_pull_request_s_api_address(
    site: RepositorySite, tmp_path: Path
):
    site.build(tmp_path)
    assert (
        f'{DraftRecheckAttribute.PULL_REQUEST}="{OPEN_PULL_REQUEST.api_url}"'
        in page_of(tmp_path, SitePlan.SECOND)
    )


def test_a_chip_on_a_dependency_ready_for_review_names_no_pull_request(
    site: RepositorySite,
    pull_request_source: RecordedPullRequestSource,
    tmp_path: Path,
):
    pull_request_source.records[OPEN_PULL_REQUEST] = PullRequestRecord(
        state=PullRequestState.OPEN, draft=False
    )
    site.build(tmp_path)
    assert f'{DraftRecheckAttribute.PULL_REQUEST}="' not in page_of(
        tmp_path, SitePlan.SECOND
    )


def test_an_item_held_back_only_by_a_draft_carries_its_start_action_hidden(
    site: RepositorySite, tmp_path: Path
):
    site.build(tmp_path)
    page = page_of(tmp_path, SitePlan.SECOND)
    assert f"hidden {DraftRecheckAttribute.START_ACTION}>" in page
    assert start_action_of_held_back_item().command in page


def test_an_item_held_back_by_a_dependency_without_a_draft_carries_no_start_action(
    site: RepositorySite,
    pull_request_source: RecordedPullRequestSource,
    tmp_path: Path,
):
    del pull_request_source.records[OPEN_PULL_REQUEST]
    site.build(tmp_path)
    assert start_action_of_held_back_item().command not in page_of(
        tmp_path, SitePlan.SECOND
    )


# %% what the page does with GitHub's answer


def open_second_plan_page(
    page: Page, output: Path, status: HTTPStatus, pull_request: dict[str, Any]
) -> None:
    """
    Open the second plan's built page, with GitHub answering the draft pull request's
    address as given and nothing else on the network, and wait for the re-check.

    :param page: The browser page to open it in.
    :param output: The built site's root directory.
    :param status: The status GitHub answers with.
    :param pull_request: The pull request GitHub answers with.
    """

    def answer_for_github(route: Route) -> None:
        route.fulfill(
            status=status,
            headers={"Access-Control-Allow-Origin": "*"},
            content_type="application/json",
            body=json.dumps(pull_request),
        )

    page.route(SiteSampleText.SITE_URL + "**", lambda route: route.abort())
    page.route(OPEN_PULL_REQUEST.api_url, answer_for_github)
    page.goto(
        (output / str(NOTES_REPOSITORY) / SitePlan.SECOND / SiteFile.PAGE).as_uri()
    )
    page.wait_for_selector(f"[{DraftRecheckAttribute.FINISHED}]", state="attached")


def held_back_chip(page: Page) -> Locator:
    """
    :param page: The opened plan page.
    :return: The held-back item's dependency chip.
    """
    return page.locator(
        f"#{HELD_BACK_ITEM.anchor} [{DraftRecheckAttribute.PULL_REQUEST}]"
    )


def held_back_start_action(page: Page) -> Locator:
    """
    :param page: The opened plan page.
    :return: The held-back item's hidden start action.
    """
    return page.locator(
        f"#{HELD_BACK_ITEM.anchor} [{DraftRecheckAttribute.START_ACTION}]"
    )


@pytest.mark.parametrize(
    "now",
    [
        {PullRequestField.DRAFT: False},
        {
            PullRequestField.STATE: PullRequestState.CLOSED.value,
            PullRequestField.MERGED_AT: "2026-11-01T00:00:00Z",
        },
    ],
    ids=["ready-for-review", "merged"],
)
def test_a_dependency_no_longer_draft_makes_its_dependent_startable(
    site: RepositorySite,
    browser_page: Page,
    tmp_path: Path,
    now: dict[PullRequestField, Any],
):
    site.build(tmp_path)
    open_second_plan_page(
        browser_page, tmp_path, HTTPStatus.OK, api_pull_request(OPEN_PULL_REQUEST, now)
    )
    expect(held_back_chip(browser_page)).to_have_class("chip")
    expect(held_back_start_action(browser_page)).to_be_visible()


def test_a_dependency_still_draft_keeps_its_dependent_held_back(
    site: RepositorySite, browser_page: Page, tmp_path: Path
):
    site.build(tmp_path)
    still_draft = api_pull_request(OPEN_PULL_REQUEST, {PullRequestField.DRAFT: True})
    open_second_plan_page(browser_page, tmp_path, HTTPStatus.OK, still_draft)
    expect(held_back_chip(browser_page)).to_have_class("chip chip-unmet")
    expect(held_back_start_action(browser_page)).to_be_hidden()


def test_a_pull_request_github_does_not_show_keeps_its_dependent_held_back(
    site: RepositorySite, browser_page: Page, tmp_path: Path
):
    site.build(tmp_path)
    open_second_plan_page(browser_page, tmp_path, HTTPStatus.NOT_FOUND, {})
    expect(held_back_chip(browser_page)).to_have_class("chip chip-unmet")
    expect(held_back_start_action(browser_page)).to_be_hidden()
