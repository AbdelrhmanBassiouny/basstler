"""
Tests for :mod:`basstler.plan_site.item_classifier`: an item on a repository the build
cannot read.
"""

from __future__ import annotations

from http import HTTPStatus

import pytest

from basstler.plan_site.__main__ import PlanSource
from basstler.plan_site.item_classifier import READ_ACCESS_STATUSES, ItemClassifier
from basstler.plan_site.plan import Item, Plan
from basstler.plan_site.plan_page import PlanPage
from basstler.plan_site.workflows import PlanSiteSecret
from basstler.pull_request_state import LivePullRequests, LiveState

from ..constants.site import SitePlan, SiteSampleText
from ..github.pull_request_api import refusal
from .first_plan import ELSEWHERE_PULL_REQUEST

# %% the warning an item on an unreadable repository shows


@pytest.mark.parametrize("status", sorted(READ_ACCESS_STATUSES))
def test_an_access_warning_for_a_repository_not_granted_names_the_read_token(
    status: HTTPStatus,
):
    warning = ItemClassifier.access_warning_of(
        ELSEWHERE_PULL_REQUEST.repository,
        refusal(ELSEWHERE_PULL_REQUEST.repository, status),
    )
    assert PlanSiteSecret.private_repository_correction in warning


def test_an_access_warning_for_another_failure_gives_that_failure_s_own_fix():
    failure = refusal(ELSEWHERE_PULL_REQUEST.repository, HTTPStatus.UNAUTHORIZED)
    warning = ItemClassifier.access_warning_of(
        ELSEWHERE_PULL_REQUEST.repository, failure
    )
    assert warning.endswith(failure.suggest_correction())


def test_an_access_warning_for_another_failure_does_not_name_the_read_token():
    warning = ItemClassifier.access_warning_of(
        ELSEWHERE_PULL_REQUEST.repository,
        refusal(ELSEWHERE_PULL_REQUEST.repository, HTTPStatus.UNAUTHORIZED),
    )
    assert PlanSiteSecret.private_repository_correction not in warning


def test_an_access_warning_says_why_the_repository_cannot_be_read():
    failure = refusal(ELSEWHERE_PULL_REQUEST.repository, HTTPStatus.NOT_FOUND)
    warning = ItemClassifier.access_warning_of(
        ELSEWHERE_PULL_REQUEST.repository, failure
    )
    assert failure.error_message() in warning


# %% classifying an item on an unreadable repository


def item_on_an_unreadable_repository() -> Item:
    """
    :return: The first plan's item on a repository other than its default, after its
        page is rendered with that repository unreadable.
    """
    plan = Plan.from_mapping(
        PlanSource.from_directory(SitePlan.FIRST.directory).manifest
    )
    PlanPage(
        stylesheet_url=SiteSampleText.SITE_URL,
        plan=plan,
        roadmap_text="",
        live_pull_requests=LivePullRequests(
            read_failures={
                ELSEWHERE_PULL_REQUEST.repository: refusal(
                    ELSEWHERE_PULL_REQUEST.repository, HTTPStatus.NOT_FOUND
                )
            }
        ),
    ).render()
    return next(item for item in plan.items if item.repository is not None)


def test_an_item_on_a_repository_the_build_cannot_read_is_classified_so():
    assert (
        item_on_an_unreadable_repository().live_state is LiveState.REPOSITORY_UNREADABLE
    )


def test_an_item_on_a_repository_the_build_cannot_read_is_not_reported_as_drift():
    assert item_on_an_unreadable_repository().drift_description is None
