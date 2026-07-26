"""
Tests for build_dashboard.py's validation, live-state classification, drift detection,
and rendering.
"""

import pytest

from build_dashboard import (
    AVAILABLE_MODELS,
    DashboardRenderer,
    DuplicateItemId,
    InvalidDependsOn,
    InvalidSchemaVersion,
    Item,
    ItemStatus,
    LiveState,
    MAXIMUM_DEPENDENCY_STACK_LEVEL,
    Plan,
    PlanValidationError,
    PullRequestRecord,
    StackedItem,
    Track,
    UnknownDependency,
    UnknownStatus,
    UnknownTrack,
    UnknownWave,
    Wave,
    validate_plan,
)


def minimal_plan(**overrides):
    plan = {
        "schema_version": 1,
        "id": "test-plan",
        "title": "Test Plan",
        "description": "A plan.",
        "default_repository": "owner/repo",
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
    assert isinstance(error.value.problems[0], InvalidSchemaVersion)
    assert error.value.problems[0].actual_value == 2


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
    duplicate_problems = [
        p for p in error.value.problems if isinstance(p, DuplicateItemId)
    ]
    assert duplicate_problems == [DuplicateItemId(["a"])]


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
    assert any(isinstance(problem, UnknownTrack) for problem in error.value.problems)


def test_validate_plan_rejects_unknown_wave():
    tracks = [{"id": "track-1", "name": "Track 1", "wave": "no-such-wave"}]
    with pytest.raises(PlanValidationError) as error:
        validate_plan(minimal_plan(tracks=tracks))
    assert any(isinstance(problem, UnknownWave) for problem in error.value.problems)


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
        isinstance(problem, UnknownDependency) for problem in error.value.problems
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
        isinstance(problem, InvalidDependsOn) for problem in error.value.problems
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
    assert any(isinstance(problem, UnknownStatus) for problem in error.value.problems)


def test_validate_plan_collects_every_problem_not_just_the_first():
    with pytest.raises(PlanValidationError) as error:
        validate_plan(minimal_plan(schema_version=2, tracks=[]))
    problem_types = {type(problem) for problem in error.value.problems}
    assert InvalidSchemaVersion in problem_types
    assert UnknownTrack in problem_types


def test_plan_validation_error_message_joins_every_problem_description():
    with pytest.raises(PlanValidationError) as error:
        validate_plan(minimal_plan(schema_version=2))
    assert str(error.value) == "schema_version must be 1, got 2"


# %% ItemStatus / LiveState labels


def test_item_status_display_labels():
    assert ItemStatus.NOT_STARTED.display_label == "Not started"
    assert ItemStatus.DONE.display_label == "Done"


def test_live_state_display_labels_including_no_pull_request():
    assert LiveState.NO_PULL_REQUEST.display_label == "No PR yet"
    assert LiveState.MERGED.display_label == "Merged"


# %% PullRequestRecord.was_merged


def test_was_merged_true_when_github_recorded_a_merge():
    record = PullRequestRecord(state="closed", merged_at="2026-01-01")
    assert record.was_merged


def test_was_merged_true_for_an_out_of_band_merge_marked_by_label():
    # merged_at is never set for a PR merged by pushing its branch directly
    # and closing by hand - this repo's convention is a "merged" label instead.
    record = PullRequestRecord(state="closed", labels=["in-review", "merged"])
    assert record.was_merged


def test_was_merged_false_for_a_plain_closed_pr():
    record = PullRequestRecord(state="closed", labels=["in-review"])
    assert not record.was_merged


def test_was_merged_false_for_an_open_pr():
    record = PullRequestRecord(state="open")
    assert not record.was_merged


# %% Item / StackedItem - precomputed template values


def test_status_and_drift_css_class_without_drift():
    plain_item = Item(
        title="A", branch="a", track="track-1", status=ItemStatus.IN_PROGRESS
    )
    assert plain_item.status_and_drift_css_class == "status-in_progress"


def test_status_and_drift_css_class_with_drift():
    drifted_item = Item(title="A", branch="a", track="track-1", status=ItemStatus.DONE)
    drifted_item.drift_description = "marked done, but PR #1 is still open"
    assert drifted_item.status_and_drift_css_class == "status-done has-drift"


def test_is_ready_to_unblock_dependents_true_when_done():
    done_item = Item(title="A", branch="a", track="track-1", status=ItemStatus.DONE)
    assert done_item.is_ready_to_unblock_dependents()


def test_is_ready_to_unblock_dependents_true_when_open_and_ready_for_review():
    open_item = Item(
        title="A", branch="a", track="track-1", status=ItemStatus.IN_PROGRESS
    )
    open_item.live_state = LiveState.OPEN_READY
    assert open_item.is_ready_to_unblock_dependents()


def test_is_ready_to_unblock_dependents_false_while_still_a_draft():
    draft_item = Item(
        title="A", branch="a", track="track-1", status=ItemStatus.IN_PROGRESS
    )
    draft_item.live_state = LiveState.OPEN_DRAFT
    assert not draft_item.is_ready_to_unblock_dependents()


def test_is_ready_to_unblock_dependents_false_when_not_started():
    fresh_item = Item(
        title="A", branch="a", track="track-1", status=ItemStatus.NOT_STARTED
    )
    assert not fresh_item.is_ready_to_unblock_dependents()


def test_stacked_item_indent_style_exposes_both_indent_levels_as_css_variables():
    stacked = StackedItem(
        item=Item(title="A", branch="a", track="track-1", status=ItemStatus.DONE),
        indent_level=2,
        wrap_parent=None,
        indent_level_with_done_hidden=0,
        wrap_parent_with_done_hidden=None,
    )
    assert stacked.indent_style == "--indent-level: 2; --indent-level-hidden-done: 0;"


def test_plan_repository_url():
    plan = Plan(
        id="p",
        title="P",
        description="d",
        default_repository="owner/repo",
        waves=[],
        tracks=[],
        items=[],
    )
    assert plan.repository_url == "https://github.com/owner/repo"


def test_plan_from_mapping_reads_optional_wave_description():
    plan = Plan.from_mapping(
        minimal_plan(waves=[{"id": "wave-1", "name": "Wave 1", "description": "why"}])
    )
    assert plan.waves[0].description == "why"


def test_plan_from_mapping_defaults_missing_wave_description_to_none():
    plan = Plan.from_mapping(minimal_plan())
    assert plan.waves[0].description is None


# %% DashboardRenderer - live state + drift


def make_renderer(items, pull_requests_by_repository=None):
    plan = Plan(
        id="test-plan",
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[],
        tracks=[],
        items=items,
    )
    return DashboardRenderer(
        plan=plan,
        roadmap_text="",
        pull_requests_by_repository=pull_requests_by_repository or {},
        tracking_url=None,
    )


def item(identifier, status, pull_request_number=None, depends_on=None):
    return Item(
        title=identifier,
        branch=identifier,
        track="track-1",
        status=ItemStatus(status),
        id=identifier,
        pull_request_number=pull_request_number,
        depends_on=depends_on or [],
    )


def test_item_with_no_pr_has_no_pull_request_live_state_and_no_drift():
    renderer = make_renderer([item("a", "not_started")])
    output, summary = renderer.render()
    assert renderer.plan.items[0].live_state is LiveState.NO_PULL_REQUEST
    assert summary.drift_items == []


def test_merged_pr_marks_not_started_item_as_drifted():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state="closed", merged_at="2026-01-01")}
    }
    renderer = make_renderer(
        [item("a", "not_started", pull_request_number=1)],
        pull_requests_by_repository=pull_requests_by_repository,
    )
    _, summary = renderer.render()
    assert summary.drift_items == ["a"]
    assert renderer.plan.items[0].live_state is LiveState.MERGED


def test_closed_pr_with_merged_label_is_merged_not_closed_unmerged():
    # merged_at is unset here on purpose - this is the out-of-band-merge case
    # PullRequestRecord.was_merged exists for.
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state="closed", labels=["merged"])}
    }
    renderer = make_renderer(
        [item("a", "in_progress", pull_request_number=1)],
        pull_requests_by_repository=pull_requests_by_repository,
    )
    _, summary = renderer.render()
    assert renderer.plan.items[0].live_state is LiveState.MERGED
    assert summary.drift_items == ["a"]


def test_open_pr_marks_done_item_as_drifted():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state="open", draft=False)}
    }
    renderer = make_renderer(
        [item("a", "done", pull_request_number=1)],
        pull_requests_by_repository=pull_requests_by_repository,
    )
    _, summary = renderer.render()
    assert summary.drift_items == ["a"]


def test_pr_missing_from_live_data_is_not_found_and_drifted():
    renderer = make_renderer([item("a", "not_started", pull_request_number=999)])
    _, summary = renderer.render()
    assert renderer.plan.items[0].live_state is LiveState.NOT_FOUND
    assert summary.drift_items == ["a"]


def test_matching_status_and_live_state_is_not_drifted():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state="open", draft=True)}
    }
    renderer = make_renderer(
        [item("a", "in_progress", pull_request_number=1)],
        pull_requests_by_repository=pull_requests_by_repository,
    )
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


def test_blocked_item_with_every_dependency_done_is_recheck_not_ready_to_start():
    # A blocked item is still blocked even once its dependencies clear -
    # it belongs in "blocker may be cleared" (actionable: resolve it), never
    # in "ready to start" (that implies starting fresh, which is wrong for
    # an item that already has real state).
    items = [item("a", "done"), item("b", "blocked", depends_on=["a"])]
    renderer = make_renderer(items)
    _, summary = renderer.render()
    assert summary.blocker_maybe_cleared == ["b"]
    assert summary.ready_to_start == []


def test_item_becomes_ready_to_start_once_dependency_is_open_and_ready_for_review():
    # Stacking a branch on a same-track dependency that's already open and
    # out of draft is this repo's normal workflow - waiting for a full merge
    # first would be stricter than how the stack is actually built.
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state="open", draft=False)}
    }
    items = [
        item("a", "in_progress", pull_request_number=1),
        item("b", "not_started", depends_on=["a"]),
    ]
    renderer = make_renderer(
        items, pull_requests_by_repository=pull_requests_by_repository
    )
    _, summary = renderer.render()
    assert summary.ready_to_start == ["b"]


def test_item_not_ready_to_start_while_dependency_is_still_a_draft():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state="open", draft=True)}
    }
    items = [
        item("a", "in_progress", pull_request_number=1),
        item("b", "not_started", depends_on=["a"]),
    ]
    renderer = make_renderer(
        items, pull_requests_by_repository=pull_requests_by_repository
    )
    _, summary = renderer.render()
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


# %% DashboardRenderer - ready-to-review


def test_needs_review_true_for_an_open_draft_pull_request():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state="open", draft=True)}
    }
    renderer = make_renderer(
        [item("a", "in_progress", pull_request_number=1)],
        pull_requests_by_repository=pull_requests_by_repository,
    )
    renderer.render()
    assert renderer.plan.items[0].needs_review


def test_needs_review_false_once_marked_ready_for_review():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state="open", draft=False)}
    }
    renderer = make_renderer(
        [item("a", "in_progress", pull_request_number=1)],
        pull_requests_by_repository=pull_requests_by_repository,
    )
    renderer.render()
    assert not renderer.plan.items[0].needs_review


def test_needs_review_false_with_no_pull_request():
    renderer = make_renderer([item("a", "not_started")])
    renderer.render()
    assert not renderer.plan.items[0].needs_review


def test_needs_review_false_for_a_deferred_item_with_an_open_draft_pull_request():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state="open", draft=True)}
    }
    renderer = make_renderer(
        [item("a", "deferred", pull_request_number=1)],
        pull_requests_by_repository=pull_requests_by_repository,
    )
    renderer.render()
    assert not renderer.plan.items[0].needs_review


def test_has_open_pull_request_true_for_draft_and_ready():
    draft_item = item("a", "in_progress", pull_request_number=1)
    draft_item.live_state = LiveState.OPEN_DRAFT
    ready_item = item("b", "in_progress", pull_request_number=2)
    ready_item.live_state = LiveState.OPEN_READY
    assert draft_item.has_open_pull_request
    assert ready_item.has_open_pull_request


def test_has_open_pull_request_false_when_merged_or_absent():
    merged_item = item("a", "done", pull_request_number=1)
    merged_item.live_state = LiveState.MERGED
    no_pr_item = item("b", "not_started")
    assert not merged_item.has_open_pull_request
    assert not no_pr_item.has_open_pull_request


def test_item_with_no_dependency_and_draft_pr_is_ready_to_review():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state="open", draft=True)}
    }
    renderer = make_renderer(
        [item("a", "in_progress", pull_request_number=1)],
        pull_requests_by_repository=pull_requests_by_repository,
    )
    _, summary = renderer.render()
    assert summary.ready_to_review == ["a"]


def test_blocked_item_with_draft_pr_is_not_ready_to_review():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state="open", draft=True)}
    }
    renderer = make_renderer(
        [item("a", "blocked", pull_request_number=1)],
        pull_requests_by_repository=pull_requests_by_repository,
    )
    _, summary = renderer.render()
    assert summary.ready_to_review == []


def test_deferred_item_with_draft_pr_is_not_ready_to_review():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state="open", draft=True)}
    }
    renderer = make_renderer(
        [item("a", "deferred", pull_request_number=1)],
        pull_requests_by_repository=pull_requests_by_repository,
    )
    _, summary = renderer.render()
    assert summary.ready_to_review == []


def test_item_not_ready_to_review_while_dependency_has_no_pull_request():
    pull_requests_by_repository = {
        "owner/repo": {"2": PullRequestRecord(state="open", draft=True)}
    }
    items = [
        item("a", "not_started"),
        item("b", "in_progress", pull_request_number=2, depends_on=["a"]),
    ]
    renderer = make_renderer(
        items, pull_requests_by_repository=pull_requests_by_repository
    )
    _, summary = renderer.render()
    assert summary.ready_to_review == []


def test_item_ready_to_review_once_dependency_has_an_open_pull_request():
    # The dependency need not itself be past review - it just needs a PR
    # open, so a whole reviewable stack can surface before its base merges.
    pull_requests_by_repository = {
        "owner/repo": {
            "1": PullRequestRecord(state="open", draft=True),
            "2": PullRequestRecord(state="open", draft=True),
        }
    }
    items = [
        item("a", "in_progress", pull_request_number=1),
        item("b", "in_progress", pull_request_number=2, depends_on=["a"]),
    ]
    renderer = make_renderer(
        items, pull_requests_by_repository=pull_requests_by_repository
    )
    _, summary = renderer.render()
    assert summary.ready_to_review == ["a", "b"]


# %% DashboardRenderer - item action button


def test_action_is_start_now_for_a_not_started_item():
    renderer = make_renderer([item("a", "not_started")])
    renderer.render()
    action = renderer.plan.items[0].action
    assert action.label == "Start now"
    assert action.command == "/plan-item-kickoff test-plan a"


def test_action_none_for_a_not_started_item_while_a_dependency_is_not_ready():
    items = [item("a", "not_started"), item("b", "not_started", depends_on=["a"])]
    renderer = make_renderer(items)
    renderer.render()
    assert renderer.items_by_identifier["b"].action is None


def test_action_set_once_every_dependency_is_ready():
    items = [item("a", "done"), item("b", "not_started", depends_on=["a"])]
    renderer = make_renderer(items)
    renderer.render()
    assert (
        renderer.items_by_identifier["b"].action.command
        == "/plan-item-kickoff test-plan b"
    )


def test_action_set_when_dependency_is_open_and_ready_for_review():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state="open", draft=False)}
    }
    items = [
        item("a", "in_progress", pull_request_number=1),
        item("b", "not_started", depends_on=["a"]),
    ]
    renderer = make_renderer(
        items, pull_requests_by_repository=pull_requests_by_repository
    )
    renderer.render()
    assert renderer.items_by_identifier["b"].action is not None


def test_action_none_for_a_not_started_item_when_dependency_is_still_a_draft():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state="open", draft=True)}
    }
    items = [
        item("a", "in_progress", pull_request_number=1),
        item("b", "not_started", depends_on=["a"]),
    ]
    renderer = make_renderer(
        items, pull_requests_by_repository=pull_requests_by_repository
    )
    renderer.render()
    assert renderer.items_by_identifier["b"].action is None


def test_action_ready_check_is_order_independent():
    # "b" depends on "a", but "a" appears later in plan.items - the
    # dependency's live_state must still be classified before "b"'s
    # action is computed.
    items = [item("b", "not_started", depends_on=["a"]), item("a", "done")]
    renderer = make_renderer(items)
    renderer.render()
    assert (
        renderer.items_by_identifier["b"].action.command
        == "/plan-item-kickoff test-plan b"
    )


def test_action_none_for_a_done_item():
    renderer = make_renderer([item("a", "done")])
    renderer.render()
    assert renderer.plan.items[0].action is None


def test_action_is_resolve_for_a_blocked_item():
    renderer = make_renderer([item("a", "blocked")])
    renderer.render()
    action = renderer.plan.items[0].action
    assert action.label == "Resolve"
    assert action.command == "/plan-item-resolve test-plan a"


def test_action_is_resume_for_an_in_progress_item():
    renderer = make_renderer([item("a", "in_progress")])
    renderer.render()
    action = renderer.plan.items[0].action
    assert action.label == "Resume"
    assert action.command == "/plan-item-resolve test-plan a"


def test_action_is_reconsider_for_a_deferred_item():
    renderer = make_renderer([item("a", "deferred")])
    renderer.render()
    action = renderer.plan.items[0].action
    assert action.label == "Reconsider"
    assert action.command == "/plan-item-resolve test-plan a"


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
    stacked_items = renderer._build_track_stack(items)
    assert [stacked.indent_level for stacked in stacked_items] == [0, 1, 2, 3, 4, 0]
    assert stacked_items[-1].wrap_parent.identifier == "item-4"


def test_track_stack_does_not_wrap_within_the_maximum_level():
    items = [item("item-0", "not_started")]
    for index in range(1, MAXIMUM_DEPENDENCY_STACK_LEVEL):
        items.append(
            item(f"item-{index}", "not_started", depends_on=[f"item-{index - 1}"])
        )
    renderer = make_renderer(items)
    stacked_items = renderer._build_track_stack(items)
    assert all(stacked.wrap_parent is None for stacked in stacked_items)


# %% DashboardRenderer - dependency stacking / hidden-done dedent


def test_hidden_done_indent_dedents_a_dependent_of_a_done_item_to_zero():
    items = [item("a", "done"), item("b", "not_started", depends_on=["a"])]
    renderer = make_renderer(items)
    stacked_items = renderer._build_track_stack(items)
    stacked_b = next(s for s in stacked_items if s.item.identifier == "b")
    assert stacked_b.indent_level == 1
    assert stacked_b.indent_level_with_done_hidden == 0
    assert stacked_b.wrap_parent_with_done_hidden is None


def test_hidden_done_indent_unaffected_when_dependency_is_not_done():
    items = [item("a", "in_progress"), item("b", "not_started", depends_on=["a"])]
    renderer = make_renderer(items)
    stacked_items = renderer._build_track_stack(items)
    stacked_b = next(s for s in stacked_items if s.item.identifier == "b")
    assert stacked_b.indent_level == 1
    assert stacked_b.indent_level_with_done_hidden == 1


def test_hidden_done_indent_only_dedents_the_immediate_done_dependency():
    # c depends on b (in progress), b depends on a (done). Hiding a only
    # removes b's own dependency on it - c still indents under the still-
    # visible b, one level, not zero.
    items = [
        item("a", "done"),
        item("b", "in_progress", depends_on=["a"]),
        item("c", "not_started", depends_on=["b"]),
    ]
    renderer = make_renderer(items)
    stacked_items = renderer._build_track_stack(items)
    stacked_b = next(s for s in stacked_items if s.item.identifier == "b")
    stacked_c = next(s for s in stacked_items if s.item.identifier == "c")
    assert stacked_b.indent_level_with_done_hidden == 0
    assert stacked_c.indent_level_with_done_hidden == 1


def test_hidden_done_indent_skips_a_chain_of_done_dependencies():
    items = [
        item("a", "done"),
        item("b", "done", depends_on=["a"]),
        item("c", "not_started", depends_on=["b"]),
    ]
    renderer = make_renderer(items)
    stacked_items = renderer._build_track_stack(items)
    stacked_c = next(s for s in stacked_items if s.item.identifier == "c")
    assert stacked_c.indent_level == 2
    assert stacked_c.indent_level_with_done_hidden == 0


def test_hidden_done_wrap_parent_is_never_a_done_item():
    # A chain of dependencies just long enough to wrap once the two done
    # items at its base are hidden: after hiding, c is the effective root
    # (level 0), d=1, e=2, f=3, g=4, h wraps back to 0 continuing from g -
    # never from a done item, even though the full (unhidden) chain would
    # wrap earlier and reference a different, done, parent.
    items = [
        item("a", "done"),
        item("b", "done", depends_on=["a"]),
        item("c", "not_started", depends_on=["b"]),
        item("d", "not_started", depends_on=["c"]),
        item("e", "not_started", depends_on=["d"]),
        item("f", "not_started", depends_on=["e"]),
        item("g", "not_started", depends_on=["f"]),
        item("h", "not_started", depends_on=["g"]),
    ]
    renderer = make_renderer(items)
    stacked_items = renderer._build_track_stack(items)
    stacked_h = next(s for s in stacked_items if s.item.identifier == "h")
    assert stacked_h.indent_level_with_done_hidden == 0
    assert stacked_h.wrap_parent_with_done_hidden.identifier == "g"


# %% end-to-end wave/track/item wiring


def test_render_wires_an_item_into_its_wave_and_track_sections():
    plan = Plan(
        id="test-plan",
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[item("a", "not_started")],
    )
    renderer = DashboardRenderer(
        plan=plan, roadmap_text="", pull_requests_by_repository={}, tracking_url=None
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
    renderer = DashboardRenderer(
        plan=plan, roadmap_text="", pull_requests_by_repository={}, tracking_url=None
    )
    output, _ = renderer.render()
    assert "Nothing here yet." in output


def test_render_shows_pull_request_link_when_item_has_one():
    pull_requests_by_repository = {
        "owner/repo": {"5": PullRequestRecord(state="open", draft=False)}
    }
    plan = Plan(
        id="test-plan",
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[item("a", "in_progress", pull_request_number=5)],
    )
    renderer = DashboardRenderer(
        plan=plan,
        roadmap_text="",
        pull_requests_by_repository=pull_requests_by_repository,
        tracking_url=None,
    )
    output, _ = renderer.render()
    assert 'href="https://github.com/owner/repo/pull/5"' in output
    assert "#5" in output


def test_render_shows_start_now_button_for_a_not_started_item():
    plan = Plan(
        id="test-plan",
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[item("a", "not_started")],
    )
    renderer = DashboardRenderer(
        plan=plan, roadmap_text="", pull_requests_by_repository={}, tracking_url=None
    )
    output, _ = renderer.render()
    assert 'data-action-command="/plan-item-kickoff test-plan a"' in output
    assert "Start now" in output


def test_render_shows_resolve_resume_reconsider_buttons_for_underway_items():
    plan = Plan(
        id="test-plan",
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[
            item("a", "in_progress"),
            item("b", "blocked"),
            item("c", "deferred"),
        ],
    )
    renderer = DashboardRenderer(
        plan=plan, roadmap_text="", pull_requests_by_repository={}, tracking_url=None
    )
    output, _ = renderer.render()
    assert 'data-action-command="/plan-item-resolve test-plan a"' in output
    assert 'data-action-command="/plan-item-resolve test-plan b"' in output
    assert 'data-action-command="/plan-item-resolve test-plan c"' in output
    assert "Resume" in output
    assert "Resolve" in output
    assert "Reconsider" in output


def test_render_shows_review_button_for_an_item_with_a_draft_pull_request():
    pull_requests_by_repository = {
        "owner/repo": {"5": PullRequestRecord(state="open", draft=True)}
    }
    plan = Plan(
        id="test-plan",
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[item("a", "in_progress", pull_request_number=5)],
    )
    renderer = DashboardRenderer(
        plan=plan,
        roadmap_text="",
        pull_requests_by_repository=pull_requests_by_repository,
        tracking_url=None,
    )
    output, _ = renderer.render()
    assert 'class="review-button" href="https://github.com/owner/repo/pull/5"' in output
    assert "Review" in output


def test_render_omits_review_button_once_pull_request_is_ready_for_review():
    pull_requests_by_repository = {
        "owner/repo": {"5": PullRequestRecord(state="open", draft=False)}
    }
    plan = Plan(
        id="test-plan",
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[item("a", "in_progress", pull_request_number=5)],
    )
    renderer = DashboardRenderer(
        plan=plan,
        roadmap_text="",
        pull_requests_by_repository=pull_requests_by_repository,
        tracking_url=None,
    )
    output, _ = renderer.render()
    assert 'class="review-button"' not in output


def test_render_omits_review_button_for_a_deferred_item_with_a_draft_pull_request():
    pull_requests_by_repository = {
        "owner/repo": {"5": PullRequestRecord(state="open", draft=True)}
    }
    plan = Plan(
        id="test-plan",
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[item("a", "deferred", pull_request_number=5)],
    )
    renderer = DashboardRenderer(
        plan=plan,
        roadmap_text="",
        pull_requests_by_repository=pull_requests_by_repository,
        tracking_url=None,
    )
    output, _ = renderer.render()
    assert 'class="review-button"' not in output


def test_render_shows_ready_to_review_sidebar_section():
    pull_requests_by_repository = {
        "owner/repo": {"5": PullRequestRecord(state="open", draft=True)}
    }
    plan = Plan(
        id="test-plan",
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[item("a", "in_progress", pull_request_number=5)],
    )
    renderer = DashboardRenderer(
        plan=plan,
        roadmap_text="",
        pull_requests_by_repository=pull_requests_by_repository,
        tracking_url=None,
    )
    output, _ = renderer.render()
    assert "Ready to review (1)" in output
    assert (
        'class="next-review-link" href="https://github.com/owner/repo/pull/5"' in output
    )


def test_render_shows_ready_to_review_section_last_in_the_sidebar():
    pull_requests_by_repository = {
        "owner/repo": {"5": PullRequestRecord(state="open", draft=True)}
    }
    plan = Plan(
        id="test-plan",
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[
            item("a", "in_progress", pull_request_number=5),
            item("b", "done"),
            item("c", "not_started", depends_on=["b"]),
        ],
    )
    renderer = DashboardRenderer(
        plan=plan,
        roadmap_text="",
        pull_requests_by_repository=pull_requests_by_repository,
        tracking_url=None,
    )
    output, _ = renderer.render()
    assert output.index("Ready to review") > output.index("Ready to start")


def test_render_omits_action_button_for_a_done_item():
    plan = Plan(
        id="test-plan",
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[item("a", "done")],
    )
    renderer = DashboardRenderer(
        plan=plan, roadmap_text="", pull_requests_by_repository={}, tracking_url=None
    )
    output, _ = renderer.render()
    assert 'data-action-command="' not in output


def test_render_hides_done_items_by_default_with_a_sidebar_toggle():
    plan = Plan(
        id="test-plan",
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[item("a", "done")],
    )
    renderer = DashboardRenderer(
        plan=plan, roadmap_text="", pull_requests_by_repository={}, tracking_url=None
    )
    output, _ = renderer.render()
    assert 'id="plan-dashboard-page"' in output
    assert 'class="page hide-done"' in output
    assert 'id="show-done-toggle"' in output


def test_render_offers_every_model_option_in_each_action_buttons_dropdown():
    plan = Plan(
        id="test-plan",
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[item("a", "not_started")],
    )
    renderer = DashboardRenderer(
        plan=plan, roadmap_text="", pull_requests_by_repository={}, tracking_url=None
    )
    output, _ = renderer.render()
    for model in AVAILABLE_MODELS:
        assert f'data-value="{model.value}"' in output
        assert f">{model.label}</li>" in output
    assert 'class="model-picker-toggle"' in output
    assert 'class="model-select"' not in output


def test_render_exposes_both_indent_levels_as_css_variables_on_the_item():
    plan = Plan(
        id="test-plan",
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[item("a", "done"), item("b", "not_started", depends_on=["a"])],
    )
    renderer = DashboardRenderer(
        plan=plan, roadmap_text="", pull_requests_by_repository={}, tracking_url=None
    )
    output, _ = renderer.render()
    assert "--indent-level: 1; --indent-level-hidden-done: 0;" in output


def test_render_shows_dependency_chip_with_dependency_title_as_tooltip():
    plan = Plan(
        id="test-plan",
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
    renderer = DashboardRenderer(
        plan=plan, roadmap_text="", pull_requests_by_repository={}, tracking_url=None
    )
    output, _ = renderer.render()
    assert 'title="Item A"' in output


# %% sidebar next-step links


def test_render_gives_each_item_card_a_stable_id_anchor():
    plan = Plan(
        id="test-plan",
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[item("a", "not_started")],
    )
    renderer = DashboardRenderer(
        plan=plan, roadmap_text="", pull_requests_by_repository={}, tracking_url=None
    )
    output, _ = renderer.render()
    assert 'id="item-a"' in output


def test_render_links_a_ready_to_start_sidebar_entry_to_its_item_card():
    plan = Plan(
        id="test-plan",
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[item("a", "done"), item("b", "not_started", depends_on=["a"])],
    )
    renderer = DashboardRenderer(
        plan=plan, roadmap_text="", pull_requests_by_repository={}, tracking_url=None
    )
    output, _ = renderer.render()
    assert 'href="#item-b"' in output
    assert 'data-item-identifier="b"' in output
    assert 'onclick="planDashboardHighlightItem(event, this)"' in output


def test_render_links_a_drift_sidebar_entry_to_its_item_card():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state="open", draft=False)}
    }
    plan = Plan(
        id="test-plan",
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=[item("a", "done", pull_request_number=1)],
    )
    renderer = DashboardRenderer(
        plan=plan,
        roadmap_text="",
        pull_requests_by_repository=pull_requests_by_repository,
        tracking_url=None,
    )
    output, _ = renderer.render()
    assert 'href="#item-a"' in output
    assert 'data-item-identifier="a"' in output


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
