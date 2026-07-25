"""
Tests for build_dashboard.py's validation, live-state classification, drift detection,
and rendering.
"""

import pytest

from build_dashboard import (
    DashboardRenderer,
    Item,
    ItemStatus,
    LiveState,
    MAXIMUM_DEPENDENCY_STACK_LEVEL,
    Plan,
    PlanValidationError,
    PullRequestRecord,
    Track,
    ValidationProblemKind,
    Wave,
    live_state_display_label,
    validate_plan,
)


def minimal_plan(**overrides):
    plan = {
        "schema_version": 1,
        "id": "test-plan",
        "title": "Test Plan",
        "description": "A plan.",
        "default_repo": "owner/repo",
        "waves": [{"id": "wave-1", "name": "Wave 1"}],
        "tracks": [{"id": "track-1", "name": "Track 1", "wave": "wave-1"}],
        "items": [
            {
                "id": "a",
                "title": "Item A",
                "branch": "a",
                "track": "track-1",
                "status": "not_started",
            }
        ],
    }
    plan.update(overrides)
    return plan


# %% validate_plan


def test_validate_plan_accepts_a_well_formed_manifest():
    validate_plan(minimal_plan())  # must not raise


def test_validate_plan_rejects_wrong_schema_version():
    with pytest.raises(PlanValidationError) as error:
        validate_plan(minimal_plan(schema_version=2))
    assert error.value.problems[0].kind is ValidationProblemKind.INVALID_SCHEMA_VERSION


def test_validate_plan_rejects_duplicate_item_ids():
    items = [
        {
            "id": "a",
            "title": "A",
            "branch": "a",
            "track": "track-1",
            "status": "not_started",
        },
        {
            "id": "a",
            "title": "A again",
            "branch": "a2",
            "track": "track-1",
            "status": "not_started",
        },
    ]
    with pytest.raises(PlanValidationError) as error:
        validate_plan(minimal_plan(items=items))
    assert any(
        problem.kind is ValidationProblemKind.DUPLICATE_ITEM_ID
        for problem in error.value.problems
    )


def test_validate_plan_rejects_unknown_track():
    items = [
        {
            "id": "a",
            "title": "A",
            "branch": "a",
            "track": "no-such-track",
            "status": "not_started",
        }
    ]
    with pytest.raises(PlanValidationError) as error:
        validate_plan(minimal_plan(items=items))
    assert any(
        problem.kind is ValidationProblemKind.UNKNOWN_TRACK
        for problem in error.value.problems
    )


def test_validate_plan_rejects_unknown_wave():
    tracks = [{"id": "track-1", "name": "Track 1", "wave": "no-such-wave"}]
    with pytest.raises(PlanValidationError) as error:
        validate_plan(minimal_plan(tracks=tracks))
    assert any(
        problem.kind is ValidationProblemKind.UNKNOWN_WAVE
        for problem in error.value.problems
    )


def test_validate_plan_rejects_unknown_depends_on():
    items = [
        {
            "id": "a",
            "title": "A",
            "branch": "a",
            "track": "track-1",
            "status": "not_started",
            "depends_on": ["ghost"],
        }
    ]
    with pytest.raises(PlanValidationError) as error:
        validate_plan(minimal_plan(items=items))
    assert any(
        problem.kind is ValidationProblemKind.UNKNOWN_DEPENDENCY
        for problem in error.value.problems
    )


def test_validate_plan_rejects_depends_on_that_is_not_a_list():
    # A plain string is iterable char-by-char - must be rejected outright,
    # not silently misinterpreted as a list of one-character dependencies.
    items = [
        {
            "id": "a",
            "title": "A",
            "branch": "a",
            "track": "track-1",
            "status": "not_started",
            "depends_on": "b",
        }
    ]
    with pytest.raises(PlanValidationError) as error:
        validate_plan(minimal_plan(items=items))
    assert any(
        problem.kind is ValidationProblemKind.INVALID_DEPENDS_ON
        for problem in error.value.problems
    )


def test_validate_plan_rejects_unknown_status():
    items = [
        {
            "id": "a",
            "title": "A",
            "branch": "a",
            "track": "track-1",
            "status": "in-review",
        }
    ]
    with pytest.raises(PlanValidationError) as error:
        validate_plan(minimal_plan(items=items))
    assert any(
        problem.kind is ValidationProblemKind.UNKNOWN_STATUS
        for problem in error.value.problems
    )


def test_validate_plan_collects_every_problem_not_just_the_first():
    with pytest.raises(PlanValidationError) as error:
        validate_plan(minimal_plan(schema_version=2, tracks=[]))
    kinds = {problem.kind for problem in error.value.problems}
    assert ValidationProblemKind.INVALID_SCHEMA_VERSION in kinds
    assert ValidationProblemKind.UNKNOWN_TRACK in kinds


# %% ItemStatus / LiveState labels


def test_item_status_display_labels():
    assert ItemStatus.NOT_STARTED.display_label == "Not started"
    assert ItemStatus.DONE.display_label == "Done"


def test_live_state_display_label_handles_no_pr_yet():
    assert live_state_display_label(None) == "No PR yet"
    assert live_state_display_label(LiveState.MERGED) == "Merged"


# %% DashboardRenderer - live state + drift


def make_renderer(items, pr_data=None):
    plan = Plan(
        id="test-plan",
        title="Test Plan",
        description="desc",
        default_repo="owner/repo",
        waves=[],
        tracks=[],
        items=items,
    )
    return DashboardRenderer(
        plan=plan, roadmap_text="", pr_data=pr_data or {}, tracking_url=None
    )


def item(identifier, status, pr=None, depends_on=None):
    return Item(
        title=identifier,
        branch=identifier,
        track="track-1",
        status=ItemStatus(status),
        id=identifier,
        pr=pr,
        depends_on=depends_on or [],
    )


def test_item_with_no_pr_has_no_live_state_and_no_drift():
    renderer = make_renderer([item("a", "not_started")])
    output, summary = renderer.render()
    assert renderer.plan.items[0].live_state is None
    assert summary.drift_items == []


def test_merged_pr_marks_not_started_item_as_drifted():
    pr_data = {
        "owner/repo": {"1": PullRequestRecord(state="closed", merged_at="2026-01-01")}
    }
    renderer = make_renderer([item("a", "not_started", pr=1)], pr_data=pr_data)
    _, summary = renderer.render()
    assert summary.drift_items == ["a"]
    assert renderer.plan.items[0].live_state is LiveState.MERGED


def test_open_pr_marks_done_item_as_drifted():
    pr_data = {"owner/repo": {"1": PullRequestRecord(state="open", draft=False)}}
    renderer = make_renderer([item("a", "done", pr=1)], pr_data=pr_data)
    _, summary = renderer.render()
    assert summary.drift_items == ["a"]


def test_pr_missing_from_live_data_is_not_found_and_drifted():
    renderer = make_renderer([item("a", "not_started", pr=999)], pr_data={})
    _, summary = renderer.render()
    assert renderer.plan.items[0].live_state is LiveState.NOT_FOUND
    assert summary.drift_items == ["a"]


def test_matching_status_and_live_state_is_not_drifted():
    pr_data = {"owner/repo": {"1": PullRequestRecord(state="open", draft=True)}}
    renderer = make_renderer([item("a", "in_progress", pr=1)], pr_data=pr_data)
    _, summary = renderer.render()
    assert summary.drift_items == []


# %% DashboardRenderer - ready-to-start / blocker-maybe-cleared


def test_item_becomes_ready_to_start_once_all_dependencies_are_done():
    items = [item("a", "done"), item("b", "not_started", depends_on=["a"])]
    renderer = make_renderer(items)
    _, summary = renderer.render()
    assert summary.ready_to_start == ["b"]


def test_blocked_item_with_partial_dependencies_done_is_recheck_candidate():
    items = [
        item("a", "done"),
        item("b", "not_started"),
        item("c", "blocked", depends_on=["a", "b"]),
    ]
    renderer = make_renderer(items)
    _, summary = renderer.render()
    assert summary.blocker_maybe_cleared == ["c"]
    assert summary.ready_to_start == []


def test_not_started_item_with_partial_dependencies_is_neither_list():
    items = [
        item("a", "done"),
        item("b", "not_started"),
        item("c", "not_started", depends_on=["a", "b"]),
    ]
    renderer = make_renderer(items)
    _, summary = renderer.render()
    assert summary.ready_to_start == []
    assert summary.blocker_maybe_cleared == []


# %% DashboardRenderer - dependency stacking / wrap-around


def test_track_stack_wraps_past_the_maximum_level():
    # A chain one longer than the cap: item N depends on item N-1.
    chain_length = MAXIMUM_DEPENDENCY_STACK_LEVEL + 2
    items = [item("item-0", "not_started")]
    for index in range(1, chain_length):
        items.append(
            item(f"item-{index}", "not_started", depends_on=[f"item-{index - 1}"])
        )
    renderer = make_renderer(items)
    assert "continues from" in renderer._render_track_stack(items)


def test_track_stack_does_not_wrap_within_the_maximum_level():
    items = [item("item-0", "not_started")]
    for index in range(1, MAXIMUM_DEPENDENCY_STACK_LEVEL):
        items.append(
            item(f"item-{index}", "not_started", depends_on=[f"item-{index - 1}"])
        )
    renderer = make_renderer(items)
    assert "continues from" not in renderer._render_track_stack(items)


# %% end-to-end wave/track/item wiring


def test_render_wires_an_item_into_its_wave_and_track_sections():
    plan = Plan(
        id="test-plan",
        title="Test Plan",
        description="desc",
        default_repo="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[item("a", "not_started")],
    )
    renderer = DashboardRenderer(
        plan=plan, roadmap_text="", pr_data={}, tracking_url=None
    )
    output, _ = renderer.render()
    assert "Wave One" in output
    assert "Track One" in output
    assert 'id="wave-wave-1"' in output


def test_render_shows_placeholder_for_a_track_with_no_items():
    plan = Plan(
        id="test-plan",
        title="Test Plan",
        description="desc",
        default_repo="owner/repo",
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
    renderer = DashboardRenderer(
        plan=plan, roadmap_text="", pr_data={}, tracking_url=None
    )
    output, _ = renderer.render()
    assert "Nothing here yet." in output


# %% status counts


def test_status_counts_cover_every_status_even_when_zero():
    renderer = make_renderer([item("a", "done")])
    _, summary = renderer.render()
    assert summary.status_counts[ItemStatus.DONE] == 1
    assert summary.status_counts[ItemStatus.BLOCKED] == 0


def test_summary_to_json_dict_uses_plain_string_status_keys():
    renderer = make_renderer([item("a", "done")])
    _, summary = renderer.render()
    json_dict = summary.to_json_dict()
    assert json_dict["counts"]["done"] == 1
    assert json_dict["drift_count"] == 0
