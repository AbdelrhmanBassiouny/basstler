"""
Build the plan pages the plan page suites render.
"""

from __future__ import annotations

from collections.abc import Callable

from basstler.plan.dependencies import (
    PlanDirectory,
)
from basstler.plan.model import ItemStatus
from basstler.plan_site.plan import Item, Plan, Track, Wave
from basstler.plan_site.plan_page import PlanPage
from basstler.pull_request_state import (
    PullRequestRecord,
    PullRequestsByRepository,
    PullRequestState,
)

from ..constants.paths import DatasetLocation, RepositoryLocation, SkillDirectory
from ..fixture_plans import (
    PLAN_UNDER_TEST_ID,
    FixturePlanId,
    ForeignItemId,
    fixture_pull_request_number,
    fixture_repository,
)

# %% builders


STYLESHEET_URL = "https://example.org/site.css"
"""
The stylesheet address every page under test links.
"""

EXAMPLE_DIRECTORY = RepositoryLocation.PLUGIN / SkillDirectory.PLAN_CREATE / "example"
"""
The committed sample plan example-walkthrough.md describes.
"""


def make_renderer(
    items: list[Item],
    pull_requests_by_repository: PullRequestsByRepository | None = None,
    plan_directory: PlanDirectory | None = None,
    locate_plan_page: Callable[[str], str] | None = None,
) -> PlanPage:
    """
    Build one :class:`PlanPage` over an otherwise-empty test plan holding *items*.

    :param items: The plan's items.
    :param pull_requests_by_repository: Live pull request state, or ``{}`` if omitted.
    :param plan_directory: The plans a cross-plan reference resolves against, or
        ``None`` for a plan whose dependencies are all its own.
    :param locate_plan_page: Where another plan's page is published, or ``None`` when
        plan pages have no known address.
    """
    plan = Plan(
        id=PLAN_UNDER_TEST_ID,
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[],
        tracks=[],
        items=items,
    )
    return PlanPage(
        stylesheet_url=STYLESHEET_URL,
        plan=plan,
        roadmap_text="",
        pull_requests_by_repository=pull_requests_by_repository or {},
        tracking_url=None,
        plan_directory=plan_directory,
        locate_plan_page=locate_plan_page,
    )


def item(
    identifier: str,
    status: ItemStatus,
    pull_request_number: int | None = None,
    depends_on: list[str] | None = None,
) -> Item:
    """
    Build one :class:`Item` whose title, branch and id are all *identifier*, on one
    fixed track.
    """
    return Item(
        title=identifier,
        branch=identifier,
        track="track-1",
        status=status,
        id=identifier,
        pull_request_number=pull_request_number,
        depends_on=depends_on or [],
    )


def a_renderer_carding_one_item(record: PullRequestRecord) -> PlanPage:
    """
    :param record: The live state of the item's pull request.
    :return: A renderer over a plan whose one item is shown as a card in its track.
    """
    plan = Plan(
        id=PLAN_UNDER_TEST_ID,
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[item("a", ItemStatus.IN_PROGRESS, pull_request_number=1)],
    )
    return PlanPage(
        stylesheet_url=STYLESHEET_URL,
        plan=plan,
        roadmap_text="",
        pull_requests_by_repository={"owner/repo": {"1": record}},
        tracking_url=None,
    )


FOREIGN_PULL_REQUESTS: PullRequestsByRepository = {
    fixture_repository(FixturePlanId.OTHER): {
        fixture_pull_request_number(
            FixturePlanId.OTHER, ForeignItemId.READY
        ): PullRequestRecord(state=PullRequestState.OPEN, draft=False),
        fixture_pull_request_number(
            FixturePlanId.OTHER, ForeignItemId.DRAFT
        ): PullRequestRecord(state=PullRequestState.OPEN, draft=True),
    }
}
"""
Live state for the fixture plan's own pull requests, keyed by that plan's
``default_repository`` rather than the rendered plan's.
"""


def make_renderer_over_plan_directory(
    items: list[Item],
    pull_requests_by_repository: PullRequestsByRepository | None = None,
    locate_plan_page: Callable[[str], str] | None = None,
) -> PlanPage:
    """
    Build a renderer whose cross-plan references resolve against the fixture plans
    directory.

    :param items: The rendered plan's items.
    :param pull_requests_by_repository: Live pull request state, or ``{}`` if omitted.
    :param locate_plan_page: Where another plan's page is published, or ``None`` when
        plan pages have no known address.
    """
    return make_renderer(
        items,
        pull_requests_by_repository,
        plan_directory=PlanDirectory(DatasetLocation.PLANS),
        locate_plan_page=locate_plan_page,
    )


def site_plan_url(plan_id: str) -> str:
    """
    Where a test's site publishes one plan's page.

    :param plan_id: The plan's own id.
    """
    return f"https://plans.example/owner/repo/{plan_id}/"


def renderer_with_cards(
    items: list[Item], locate_plan_page: Callable[[str], str] | None = None
) -> PlanPage:
    """
    Build a renderer over the fixture plans directory whose plan has the one track
    :func:`item` places every item on, so each item renders as a card.

    :param items: The rendered plan's items.
    :param locate_plan_page: Where another plan's page is published, or ``None``
        when plan pages have no known address.
    """
    plan = Plan(
        id=PLAN_UNDER_TEST_ID,
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=items,
    )
    return PlanPage(
        stylesheet_url=STYLESHEET_URL,
        plan=plan,
        roadmap_text="",
        pull_requests_by_repository={},
        tracking_url=None,
        plan_directory=PlanDirectory(DatasetLocation.PLANS),
        locate_plan_page=locate_plan_page,
    )
