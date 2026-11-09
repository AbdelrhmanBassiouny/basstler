"""
Tests for :mod:`basstler.plan_site.plan_page`: how the page lays out waves, tracks,
cards, links and counts.
"""

from __future__ import annotations

from basstler.plan_site.cards import TrackSection
from ..fixture_plans import ForeignItemId, foreign_reference

from basstler.maintenance.description import UpstreamPullRequestLink
from basstler.plan.model import ItemStatus
from basstler.plan_site.plan import Plan, Track, Wave
from basstler.plan_site.plan_page import PlanPage
from basstler.pull_request_state import (
    PullRequestRecord,
    PullRequestState,
)
from basstler.repository import Repository
from basstler.pull_request_state import LivePullRequests

from ..fixture_plans import (
    PLAN_UNDER_TEST_ID,
)
from .plan_page_builders import (
    STYLESHEET_URL,
    a_renderer_carding_one_item,
    item,
    make_renderer,
)

# %% waves, tracks and cards


def test_render_wires_an_item_into_its_wave_and_track_sections():
    plan = Plan(
        id=PLAN_UNDER_TEST_ID,
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[item("a", ItemStatus.NOT_STARTED)],
    )
    renderer = PlanPage(
        stylesheet_url=STYLESHEET_URL,
        plan=plan,
        roadmap_text="",
        live_pull_requests=LivePullRequests(),
    )
    output = renderer.render().html
    assert "Wave One" in output
    assert "Track One" in output
    assert 'id="wave-wave-1"' in output


def test_render_shows_placeholder_for_a_track_with_no_items():
    plan = Plan(
        id=PLAN_UNDER_TEST_ID,
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[
            Track(
                id="track-1",
                name="Empty Track",
                wave="wave-1",
                description="Nothing here yet.",
            )
        ],
        items=[],
    )
    renderer = PlanPage(
        stylesheet_url=STYLESHEET_URL,
        plan=plan,
        roadmap_text="",
        live_pull_requests=LivePullRequests(),
    )
    output = renderer.render().html
    assert "Nothing here yet." in output


def test_render_links_the_upstream_pull_request_on_the_item_card():
    link = UpstreamPullRequestLink(Repository("an-upstream-owner", "a-project"), 7)
    renderer = a_renderer_carding_one_item(
        PullRequestRecord(
            state=PullRequestState.OPEN, draft=True, upstream_link=link.url
        )
    )

    output = renderer.render().html

    assert renderer.plan.items[0].upstream_pull_request_url == link.url
    assert f'href="{link.url}"' in output


def test_render_leaves_an_item_without_an_upstream_pull_request_unlinked():
    renderer = a_renderer_carding_one_item(
        PullRequestRecord(state=PullRequestState.OPEN, draft=True)
    )

    output = renderer.render().html

    assert 'class="upstream-link"' not in output


def test_render_shows_pull_request_link_when_item_has_one():
    pull_requests_by_repository = {
        "owner/repo": {"5": PullRequestRecord(state=PullRequestState.OPEN, draft=False)}
    }
    plan = Plan(
        id=PLAN_UNDER_TEST_ID,
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[item("a", ItemStatus.IN_PROGRESS, pull_request_number=5)],
    )
    renderer = PlanPage(
        stylesheet_url=STYLESHEET_URL,
        plan=plan,
        roadmap_text="",
        live_pull_requests=LivePullRequests(pull_requests_by_repository),
    )
    output = renderer.render().html
    assert 'href="https://github.com/owner/repo/pull/5"' in output
    assert "#5" in output


def test_render_shows_ready_to_review_section_last_in_the_sidebar():
    pull_requests_by_repository = {
        "owner/repo": {"5": PullRequestRecord(state=PullRequestState.OPEN, draft=True)}
    }
    plan = Plan(
        id=PLAN_UNDER_TEST_ID,
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[
            item("a", ItemStatus.IN_PROGRESS, pull_request_number=5),
            item("b", ItemStatus.DONE),
            item("c", ItemStatus.NOT_STARTED, depends_on=["b"]),
        ],
    )
    renderer = PlanPage(
        stylesheet_url=STYLESHEET_URL,
        plan=plan,
        roadmap_text="",
        live_pull_requests=LivePullRequests(pull_requests_by_repository),
    )
    output = renderer.render().html
    assert output.index("Ready to review") > output.index("Ready to start")


def test_render_hides_done_items_by_default_with_a_sidebar_toggle():
    plan = Plan(
        id=PLAN_UNDER_TEST_ID,
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[item("a", ItemStatus.DONE)],
    )
    renderer = PlanPage(
        stylesheet_url=STYLESHEET_URL,
        plan=plan,
        roadmap_text="",
        live_pull_requests=LivePullRequests(),
    )
    output = renderer.render().html
    assert 'id="plan-page"' in output
    assert 'class="page hide-done"' in output
    assert 'id="show-done-toggle"' in output


# %% sidebar next-step links


def test_render_gives_each_item_card_a_stable_id_anchor():
    plan = Plan(
        id=PLAN_UNDER_TEST_ID,
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[item("a", ItemStatus.NOT_STARTED)],
    )
    renderer = PlanPage(
        stylesheet_url=STYLESHEET_URL,
        plan=plan,
        roadmap_text="",
        live_pull_requests=LivePullRequests(),
    )
    output = renderer.render().html
    assert 'id="item-a"' in output


def test_render_links_a_ready_to_start_sidebar_entry_to_its_item_card():
    plan = Plan(
        id=PLAN_UNDER_TEST_ID,
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[
            item("a", ItemStatus.DONE),
            item("b", ItemStatus.NOT_STARTED, depends_on=["a"]),
        ],
    )
    renderer = PlanPage(
        stylesheet_url=STYLESHEET_URL,
        plan=plan,
        roadmap_text="",
        live_pull_requests=LivePullRequests(),
    )
    output = renderer.render().html
    assert 'href="#item-b"' in output
    assert 'data-item-identifier="b"' in output
    assert 'onclick="planPageHighlightItem(event, this)"' in output


def test_render_links_a_drift_sidebar_entry_to_its_item_card():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state=PullRequestState.OPEN, draft=False)}
    }
    plan = Plan(
        id=PLAN_UNDER_TEST_ID,
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[item("a", ItemStatus.DONE, pull_request_number=1)],
    )
    renderer = PlanPage(
        stylesheet_url=STYLESHEET_URL,
        plan=plan,
        roadmap_text="",
        live_pull_requests=LivePullRequests(pull_requests_by_repository),
    )
    output = renderer.render().html
    assert 'href="#item-a"' in output
    assert 'data-item-identifier="a"' in output


# %% status counts


def test_status_counts_cover_every_status_even_when_zero():
    renderer = make_renderer([item("a", ItemStatus.DONE)])
    summary = renderer.render().overview
    assert summary.status_counts[ItemStatus.DONE] == 1
    assert summary.status_counts[ItemStatus.BLOCKED] == 0


# %% track order


def test_track_lists_each_item_after_the_same_track_item_it_depends_on():
    first = item("a", ItemStatus.NOT_STARTED)
    last = item("b", ItemStatus.NOT_STARTED, depends_on=["c"])
    middle = item("c", ItemStatus.NOT_STARTED, depends_on=["a"])
    track = Track(id="track-1", name="Track One", wave="wave-1")

    section = TrackSection.of_track(track, [last, first, middle])

    assert section.items == [first, middle, last]


def test_an_item_depending_only_on_another_plan_starts_its_own_chain():
    foreign_dependent = item(
        "a",
        ItemStatus.NOT_STARTED,
        depends_on=[foreign_reference(ForeignItemId.READY)],
    )
    track = Track(id="track-1", name="Track One", wave="wave-1")

    section = TrackSection.of_track(track, [foreign_dependent])

    assert section.items == [foreign_dependent]
