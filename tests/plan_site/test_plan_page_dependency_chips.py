"""
Tests for :mod:`basstler.plan_site.plan_page`: the dependency chips on an item card.
"""

from __future__ import annotations

from basstler.github.pull_request_state import LivePullRequests
from basstler.plan.model import ItemStatus
from basstler.plan.structure import Item, Plan, Track, Wave
from basstler.plan_site.plan_page import PlanPage

from ..fixture_plans import (
    PLAN_UNDER_TEST_ID,
)
from .plan_page_builders import (
    STYLESHEET_URL,
    item,
    make_renderer,
)

# %% dependency chips


def test_render_shows_dependency_chip_with_dependency_title_as_tooltip():
    plan = Plan(
        id=PLAN_UNDER_TEST_ID,
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[
            Item(
                title="Item A",
                branch="a",
                track="track-1",
                status=ItemStatus.DONE,
                id="a",
            ),
            Item(
                title="Item B",
                branch="b",
                track="track-1",
                status=ItemStatus.NOT_STARTED,
                id="b",
                depends_on=["a"],
            ),
        ],
    )
    renderer = PlanPage(
        stylesheet_url=STYLESHEET_URL,
        plan=plan,
        roadmap_text="",
        live_pull_requests=LivePullRequests(),
    )
    output = renderer.render().html
    assert 'title="Item A"' in output


def test_dependency_chip_falls_back_to_the_raw_identifier_when_unresolved():
    """
    An unresolved dependency's chip shows the entry's own text.
    """
    renderer = make_renderer([item("a", ItemStatus.NOT_STARTED, depends_on=["ghost"])])
    page = renderer.render()
    chip = page.cards_by_identifier["a"].dependency_chips[0]
    assert chip.dependency.reference.text == "ghost"
    assert chip.tooltip == "ghost"


def test_dependency_chip_is_not_ready_when_the_dependency_has_not_started():
    """
    A dependency that has not started is not ready.
    """
    renderer = make_renderer(
        [
            item("a", ItemStatus.NOT_STARTED),
            item("b", ItemStatus.NOT_STARTED, depends_on=["a"]),
        ]
    )
    page = renderer.render()
    chip = page.cards_by_identifier["b"].dependency_chips[0]
    assert chip.dependency.is_ready_to_unblock_dependents() is False


def test_dependency_chip_is_ready_when_the_dependency_is_done():
    """
    A done dependency is ready.
    """
    renderer = make_renderer(
        [
            item("a", ItemStatus.DONE),
            item("b", ItemStatus.NOT_STARTED, depends_on=["a"]),
        ]
    )
    page = renderer.render()
    chip = page.cards_by_identifier["b"].dependency_chips[0]
    assert chip.dependency.is_ready_to_unblock_dependents() is True


def test_dependency_chip_is_not_ready_when_unresolved():
    """
    An unresolved dependency is never ready.
    """
    renderer = make_renderer([item("a", ItemStatus.NOT_STARTED, depends_on=["ghost"])])
    page = renderer.render()
    chip = page.cards_by_identifier["a"].dependency_chips[0]
    assert chip.dependency.is_ready_to_unblock_dependents() is False


def test_render_marks_an_unmet_dependency_chip_with_the_chip_unmet_class():
    """
    A chip whose dependency is not ready renders with the unmet class.
    """
    plan = Plan(
        id=PLAN_UNDER_TEST_ID,
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[
            item("a", ItemStatus.NOT_STARTED),
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
    assert 'class="chip chip-unmet"' in output


def test_render_does_not_mark_a_ready_dependency_chip_as_unmet():
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
    assert 'class="chip"' in output
    assert 'class="chip chip-unmet"' not in output
