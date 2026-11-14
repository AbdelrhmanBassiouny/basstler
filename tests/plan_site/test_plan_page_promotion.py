"""
Tests for the promotion button of an item's card: when it links to the upstream's
prefilled pull request form, and when it is disabled and why.
"""

from __future__ import annotations

from datetime import datetime
from html import escape

import pytest

from basstler.github.states import CombinedCheckState
from basstler.maintenance.promotion import PromotionSummary
from basstler.plan.model import ItemStatus
from basstler.plan_site.plan import Item, Plan, Track, Wave
from basstler.plan_site.plan_page import PlanPage
from basstler.github.pull_request_state import (
    ForkLineage,
    LivePullRequests,
    PullRequestRecord,
    PullRequestState,
)
from basstler.github.repository import Repository
from basstler.stack.promotability import PromotionBlocker
from basstler.stack.promotion_link import PromotionLink, PromotionTarget

from ..constants.stack import StackLabel
from ..fixture_plans import PLAN_UNDER_TEST_ID
from .plan_page_builders import STYLESHEET_URL, item

# %% a fork with one item


FORK = Repository("a-fork-owner", "a-fork")
"""
The repository the plan's pull requests are in, a fork.
"""

LINEAGE = ForkLineage(
    upstream_repository=Repository("an-upstream-owner", "a-project"),
    upstream_default_branch="trunk",
    fork_default_branch="main",
)
"""
What :data:`FORK` was forked from.
"""

PARENT_BRANCH = "a-parent"
"""
A branch a pull request is stacked on.
"""


def a_ready_record(**changes) -> PullRequestRecord:
    """
    :param changes: The fields to set besides the defaults.
    :return: An open pull request out of draft on the fork's default branch, with
        passing checks.
    """
    fields = {
        "state": PullRequestState.OPEN,
        "draft": False,
        "base": LINEAGE.fork_default_branch,
        "title": "A title",
        "check_state": CombinedCheckState.SUCCESS,
    }
    return PullRequestRecord(**{**fields, **changes})


def a_page(
    record: PullRequestRecord,
    items: list[Item] | None = None,
    lineages: dict[str, ForkLineage] | None = None,
) -> PlanPage:
    """
    :param record: The live state of pull request 1, the plan's first item's.
    :param items: The plan's items, the first being the item under test.
    :param lineages: What each repository was forked from, or the fork's if omitted.
    :return: The page of a plan whose first item has pull request 1 in the fork.
    """
    plan = Plan(
        id=PLAN_UNDER_TEST_ID,
        title="Test Plan",
        description="desc",
        default_repository=str(FORK),
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=items or [item("a", ItemStatus.IN_PROGRESS, pull_request_number=1)],
    )
    return PlanPage(
        stylesheet_url=STYLESHEET_URL,
        plan=plan,
        roadmap_text="",
        live_pull_requests=LivePullRequests(
            {str(FORK): {"1": record}},
            fork_lineages={str(FORK): LINEAGE} if lineages is None else lineages,
        ),
    )


def promotion_of_first_item(page: PlanPage):
    """
    :param page: A page not yet rendered.
    :return: The first item's promotion button, once the page is rendered.
    """
    page.render()
    return page.plan.items[0].promotion


# %% a promotable item


def test_a_promotable_item_links_to_the_prefilled_upstream_form():
    page = a_page(a_ready_record())
    promotion = promotion_of_first_item(page)
    assert (
        promotion.url
        == PromotionLink.for_target(
            PromotionTarget(
                upstream_repository=LINEAGE.upstream_repository,
                upstream_base=LINEAGE.upstream_default_branch,
                fork_owner=FORK.owner,
            ),
            "a",
            "A title",
            PromotionSummary().upstream_description(FORK.pull_request_url(1)),
        ).url
    )
    assert promotion.blockers == []


def test_the_link_opens_in_a_new_tab():
    page = a_page(a_ready_record())
    html = page.render().html
    url = promotion_of_first_item(page).url
    assert f'href="{escape(url)}" target="_blank" rel="noopener"' in html


def test_the_button_is_labelled_contribute():
    promotion = promotion_of_first_item(a_page(a_ready_record()))
    assert promotion.label == "Contribute"


def test_the_link_names_the_upstream_repository_on_hover():
    page = a_page(a_ready_record())
    assert (
        f'title="Open a pull request on {LINEAGE.upstream_repository}"'
        in page.render().html
    )


def test_a_pull_request_stacked_on_a_merged_item_is_promotable():
    items = [
        item("a", ItemStatus.IN_PROGRESS, pull_request_number=1),
        item("parent", ItemStatus.DONE, pull_request_number=2),
    ]
    items[1].branch = PARENT_BRANCH
    page = a_page(a_ready_record(base=PARENT_BRANCH), items)
    page.live_pull_requests.pull_requests_by_repository[str(FORK)]["2"] = (
        a_ready_record(state=PullRequestState.CLOSED, merged_at=datetime(2026, 1, 1))
    )
    assert promotion_of_first_item(page).blockers == []


# %% a disabled button


@pytest.mark.parametrize(
    ("record", "blocker"),
    [
        (a_ready_record(draft=True), PromotionBlocker.DRAFT),
        (
            a_ready_record(check_state=CombinedCheckState.FAILURE),
            PromotionBlocker.CHECKS_FAILED,
        ),
        (
            a_ready_record(labels=[StackLabel.NEEDS_RESOLUTION.value]),
            PromotionBlocker.WITHHELD,
        ),
        (
            a_ready_record(upstream_link="https://example.org/pull/1"),
            PromotionBlocker.IN_REVIEW,
        ),
        (a_ready_record(base=PARENT_BRANCH), PromotionBlocker.PARENT_NOT_LANDED),
    ],
)
def test_a_pull_request_that_may_not_be_promoted_gets_a_disabled_button(
    record, blocker
):
    page = a_page(record)
    promotion = promotion_of_first_item(page)
    assert promotion.url is None
    assert promotion.blockers == [blocker]
    assert f'title="{escape(blocker.value)}"' in page.render().html


# %% no button


def test_a_pull_request_in_a_repository_that_is_not_a_fork_gets_no_button():
    assert promotion_of_first_item(a_page(a_ready_record(), lineages={})) is None


def test_an_item_without_a_pull_request_gets_no_button():
    page = a_page(a_ready_record(), [item("a", ItemStatus.NOT_STARTED)])
    assert promotion_of_first_item(page) is None
