"""
Tests for build_dashboard.py's validation, live-state classification, drift detection,
and rendering.
"""

import pytest

from build_dashboard import (
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


def test_stacked_item_indent_style_scales_with_indent_level():
    stacked = StackedItem(
        item=Item(title="A", branch="a", track="track-1", status=ItemStatus.DONE),
        indent_level=2,
        wrap_parent=None,
    )
    assert stacked.indent_style == "margin-left: 3.5rem;"


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


# %% DashboardRenderer - kickoff command


def test_kickoff_command_set_for_a_not_started_item():
    renderer = make_renderer([item("a", "not_started")])
    renderer.render()
    assert renderer.plan.items[0].kickoff_command == "/plan-item-kickoff test-plan a"


def test_kickoff_command_none_once_an_item_has_started():
    renderer = make_renderer([item("a", "in_progress")])
    renderer.render()
    assert renderer.plan.items[0].kickoff_command is None


def test_kickoff_command_none_while_a_dependency_is_not_ready():
    items = [item("a", "not_started"), item("b", "not_started", depends_on=["a"])]
    renderer = make_renderer(items)
    renderer.render()
    assert renderer.items_by_identifier["b"].kickoff_command is None


def test_kickoff_command_set_once_every_dependency_is_ready():
    items = [item("a", "done"), item("b", "not_started", depends_on=["a"])]
    renderer = make_renderer(items)
    renderer.render()
    assert (
        renderer.items_by_identifier["b"].kickoff_command
        == "/plan-item-kickoff test-plan b"
    )


def test_kickoff_command_set_when_dependency_is_open_and_ready_for_review():
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
    assert renderer.items_by_identifier["b"].kickoff_command is not None


def test_kickoff_command_none_when_dependency_is_still_a_draft():
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
    assert renderer.items_by_identifier["b"].kickoff_command is None


def test_kickoff_command_ready_check_is_order_independent():
    # "b" depends on "a", but "a" appears later in plan.items - the
    # dependency's live_state must still be classified before "b"'s
    # kickoff command is computed.
    items = [item("b", "not_started", depends_on=["a"]), item("a", "done")]
    renderer = make_renderer(items)
    renderer.render()
    assert (
        renderer.items_by_identifier["b"].kickoff_command
        == "/plan-item-kickoff test-plan b"
    )


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
    assert 'data-kickoff-command="/plan-item-kickoff test-plan a"' in output
    assert "Start now" in output


def test_render_omits_start_now_button_for_items_already_underway():
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
            item("d", "done"),
        ],
    )
    renderer = DashboardRenderer(
        plan=plan, roadmap_text="", pull_requests_by_repository={}, tracking_url=None
    )
    output, _ = renderer.render()
    assert 'data-kickoff-command="' not in output


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
