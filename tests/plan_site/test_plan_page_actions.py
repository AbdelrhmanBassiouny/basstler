"""
Tests for :mod:`basstler.plan_site.plan_page`: which action button each item gets, and
how the page renders it.
"""

from __future__ import annotations

from basstler.plan.model import ItemStatus
from basstler.plan_site.cards import ModelOption
from basstler.plan_site.plan import Plan, Track, Wave
from basstler.plan_site.plan_page import PlanPage
from basstler.pull_request_state import (
    PullRequestRecord,
    PullRequestState,
)

from ..fixture_plans import (
    PLAN_UNDER_TEST_ID,
)
from .plan_page_builders import (
    STYLESHEET_URL,
    item,
    make_renderer,
)

# %% the action each item gets


def test_action_is_start_now_for_a_not_started_item():
    renderer = make_renderer([item("a", ItemStatus.NOT_STARTED)])
    renderer.render()
    action = renderer.plan.items[0].action
    assert action.label == "Start now"
    assert action.command == "/plan-item-kickoff test-plan a"


def test_action_none_for_a_not_started_item_while_a_dependency_is_not_ready():
    items = [
        item("a", ItemStatus.NOT_STARTED),
        item("b", ItemStatus.NOT_STARTED, depends_on=["a"]),
    ]
    renderer = make_renderer(items)
    renderer.render()
    assert renderer.plan.items_by_identifier["b"].action is None


def test_action_set_once_every_dependency_is_ready():
    items = [
        item("a", ItemStatus.DONE),
        item("b", ItemStatus.NOT_STARTED, depends_on=["a"]),
    ]
    renderer = make_renderer(items)
    renderer.render()
    assert (
        renderer.plan.items_by_identifier["b"].action.command
        == "/plan-item-kickoff test-plan b"
    )


def test_action_set_when_dependency_is_open_and_ready_for_review():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state=PullRequestState.OPEN, draft=False)}
    }
    items = [
        item("a", ItemStatus.IN_PROGRESS, pull_request_number=1),
        item("b", ItemStatus.NOT_STARTED, depends_on=["a"]),
    ]
    renderer = make_renderer(
        items, pull_requests_by_repository=pull_requests_by_repository
    )
    renderer.render()
    assert renderer.plan.items_by_identifier["b"].action is not None


def test_action_none_for_a_not_started_item_when_dependency_is_still_a_draft():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state=PullRequestState.OPEN, draft=True)}
    }
    items = [
        item("a", ItemStatus.IN_PROGRESS, pull_request_number=1),
        item("b", ItemStatus.NOT_STARTED, depends_on=["a"]),
    ]
    renderer = make_renderer(
        items, pull_requests_by_repository=pull_requests_by_repository
    )
    renderer.render()
    assert renderer.plan.items_by_identifier["b"].action is None


def test_action_ready_check_is_order_independent():
    # "b" depends on "a", but "a" appears later in plan.items - the
    # dependency's live_state must still be classified before "b"'s
    # action is computed.
    items = [
        item("b", ItemStatus.NOT_STARTED, depends_on=["a"]),
        item("a", ItemStatus.DONE),
    ]
    renderer = make_renderer(items)
    renderer.render()
    assert (
        renderer.plan.items_by_identifier["b"].action.command
        == "/plan-item-kickoff test-plan b"
    )


def test_action_none_for_a_done_item():
    renderer = make_renderer([item("a", ItemStatus.DONE)])
    renderer.render()
    assert renderer.plan.items[0].action is None


def test_action_is_resolve_for_a_blocked_item():
    renderer = make_renderer([item("a", ItemStatus.BLOCKED)])
    renderer.render()
    action = renderer.plan.items[0].action
    assert action.label == "Resolve"
    assert action.command == "/plan-item-resolve test-plan a"


def test_action_is_resume_for_an_in_progress_item():
    renderer = make_renderer([item("a", ItemStatus.IN_PROGRESS)])
    renderer.render()
    action = renderer.plan.items[0].action
    assert action.label == "Resume"
    assert action.command == "/plan-item-resolve test-plan a"


def test_action_is_reconsider_for_a_deferred_item():
    renderer = make_renderer([item("a", ItemStatus.DEFERRED)])
    renderer.render()
    action = renderer.plan.items[0].action
    assert action.label == "Reconsider"
    assert action.command == "/plan-item-resolve test-plan a"


# %% rendered action buttons


def test_render_shows_start_now_button_for_a_not_started_item():
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
        pull_requests_by_repository={},
        tracking_url=None,
    )
    output = renderer.render().html
    assert 'data-action-command="/plan-item-kickoff test-plan a"' in output
    assert "Start now" in output


def test_render_shows_resolve_resume_reconsider_buttons_for_underway_items():
    plan = Plan(
        id=PLAN_UNDER_TEST_ID,
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[
            item("a", ItemStatus.IN_PROGRESS),
            item("b", ItemStatus.BLOCKED),
            item("c", ItemStatus.DEFERRED),
        ],
    )
    renderer = PlanPage(
        stylesheet_url=STYLESHEET_URL,
        plan=plan,
        roadmap_text="",
        pull_requests_by_repository={},
        tracking_url=None,
    )
    output = renderer.render().html
    assert 'data-action-command="/plan-item-resolve test-plan a"' in output
    assert 'data-action-command="/plan-item-resolve test-plan b"' in output
    assert 'data-action-command="/plan-item-resolve test-plan c"' in output
    assert "Resume" in output
    assert "Resolve" in output
    assert "Reconsider" in output


def test_render_omits_action_button_for_a_done_item():
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
        pull_requests_by_repository={},
        tracking_url=None,
    )
    output = renderer.render().html
    assert 'data-action-command="' not in output


def test_render_offers_every_model_option_in_each_action_buttons_dropdown():
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
        pull_requests_by_repository={},
        tracking_url=None,
    )
    output = renderer.render().html
    for model in ModelOption:
        assert f'data-value="{model.value}"' in output
        assert f">{model.label}</li>" in output
    assert 'class="model-picker-toggle"' in output
    assert 'class="model-select"' not in output
