"""
Tests for plan/check_dependency_readiness.py: classifying one item's dependencies as
ready or not-ready to build on, via the dashboard's own live-state rule.
"""

from __future__ import annotations

from typing import Any

import pytest

from basstler.dashboard.plan import Item, Plan, Track, Wave
from basstler.plan.dependencies import PlanDirectory
from basstler.plan.model import ItemStatus, ManifestKey
from basstler.pull_request_state import LiveState, PullRequestRecord, PullRequestState
from basstler.plan.check_dependency_readiness import (
    DependencyReadiness,
    ReadinessField,
    UnknownItemError,
)

from ..constants.paths import DatasetLocation
from ..fixture_plans import (
    FixturePlanId,
    ForeignItemId,
    PLAN_UNDER_TEST_ID,
    fixture_item,
    fixture_pull_request_number,
    fixture_repository,
    foreign_reference,
)


def make_plan(items: list[Item]) -> Plan:
    """
    Build one :class:`Plan` for a test, with a single wave/track and *items*
    - the shared entry point every test in this file builds a plan through.

    :param items: The plan's items.
    """
    return Plan(
        id=PLAN_UNDER_TEST_ID,
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=items,
    )


def item(
    identifier: str,
    status: ItemStatus,
    pull_request_number: int | None = None,
    depends_on: list[str] | None = None,
) -> Item:
    """
    Build one :class:`Item` for a test, filling in the boilerplate
    (``title``/``branch``/``id`` all equal to *identifier*, a fixed ``track``) every
    item in this file would otherwise repeat.
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


def reported(
    identifier: str,
    title: str | None,
    live_state: LiveState | None,
    is_ready: bool,
) -> dict[str, Any]:
    """
    The entry the readiness serializes to for one dependency with these values.
    """
    return {
        ReadinessField.IDENTIFIER: identifier,
        ReadinessField.TITLE: title,
        ReadinessField.LIVE_STATE: live_state,
        ReadinessField.IS_READY: is_ready,
    }


def test_raises_for_an_unknown_item():
    plan = make_plan([item("a", ItemStatus.NOT_STARTED)])
    with pytest.raises(UnknownItemError, match="ghost"):
        DependencyReadiness.of_item(plan, "ghost", {})


def test_empty_list_for_an_item_with_no_dependencies():
    plan = make_plan([item("a", ItemStatus.NOT_STARTED)])
    assert DependencyReadiness.of_item(plan, "a", {}) == []


def test_done_dependency_is_ready():
    plan = make_plan(
        [
            item("a", ItemStatus.DONE),
            item("b", ItemStatus.NOT_STARTED, depends_on=["a"]),
        ]
    )
    results = DependencyReadiness.of_item(plan, "b", {})
    assert [readiness.to_json() for readiness in results] == [
        reported(
            identifier="a",
            title="a",
            live_state=LiveState.NO_PULL_REQUEST,
            is_ready=True,
        )
    ]


def test_open_ready_dependency_is_ready():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state=PullRequestState.OPEN, draft=False)}
    }
    plan = make_plan(
        [
            item("a", ItemStatus.IN_PROGRESS, pull_request_number=1),
            item("b", ItemStatus.NOT_STARTED, depends_on=["a"]),
        ]
    )
    results = DependencyReadiness.of_item(plan, "b", pull_requests_by_repository)
    assert [readiness.to_json() for readiness in results] == [
        reported(
            identifier="a",
            title="a",
            live_state=LiveState.OPEN_READY,
            is_ready=True,
        )
    ]


def test_open_draft_dependency_is_not_ready():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state=PullRequestState.OPEN, draft=True)}
    }
    plan = make_plan(
        [
            item("a", ItemStatus.IN_PROGRESS, pull_request_number=1),
            item("b", ItemStatus.NOT_STARTED, depends_on=["a"]),
        ]
    )
    results = DependencyReadiness.of_item(plan, "b", pull_requests_by_repository)
    assert [readiness.to_json() for readiness in results] == [
        reported(
            identifier="a",
            title="a",
            live_state=LiveState.OPEN_DRAFT,
            is_ready=False,
        )
    ]


def test_unresolvable_dependency_identifier_is_reported_not_ready():
    plan = make_plan([item("b", ItemStatus.NOT_STARTED, depends_on=["ghost"])])
    results = DependencyReadiness.of_item(plan, "b", {})
    assert [readiness.to_json() for readiness in results] == [
        reported(identifier="ghost", title=None, live_state=None, is_ready=False)
    ]


def test_multiple_dependencies_reported_in_order():
    plan = make_plan(
        [
            item("a", ItemStatus.DONE),
            item("b", ItemStatus.NOT_STARTED),
            item("c", ItemStatus.NOT_STARTED, depends_on=["b", "a"]),
        ]
    )
    results = DependencyReadiness.of_item(plan, "c", {})
    assert [readiness.dependency.reference.text for readiness in results] == ["b", "a"]
    assert [
        readiness.dependency.is_ready_to_unblock_dependents() for readiness in results
    ] == [False, True]


# %% cross-plan references


def test_foreign_dependency_is_read_against_its_own_plans_repository():
    # The foreign pull request number exists only under other-plan's own
    # repository, so reading it against this plan's would report not_found
    # rather than open_ready.
    reference = foreign_reference(ForeignItemId.READY)
    plan = make_plan([item("b", ItemStatus.NOT_STARTED, depends_on=[reference])])
    results = DependencyReadiness.of_item(
        plan,
        "b",
        {
            fixture_repository(FixturePlanId.OTHER): {
                fixture_pull_request_number(
                    FixturePlanId.OTHER, ForeignItemId.READY
                ): PullRequestRecord(state=PullRequestState.OPEN, draft=False)
            }
        },
        PlanDirectory(DatasetLocation.PLANS),
    )
    assert [readiness.to_json() for readiness in results] == [
        reported(
            identifier=reference,
            title=fixture_item(FixturePlanId.OTHER, ForeignItemId.READY)[
                ManifestKey.TITLE.key
            ],
            live_state=LiveState.OPEN_READY,
            is_ready=True,
        )
    ]


def test_foreign_dependency_is_not_ready_without_a_plans_directory():
    # Nothing can resolve it, and an unresolvable dependency is never ready.
    reference = foreign_reference(ForeignItemId.READY)
    plan = make_plan([item("b", ItemStatus.NOT_STARTED, depends_on=[reference])])
    results = DependencyReadiness.of_item(plan, "b", {})
    assert [readiness.to_json() for readiness in results] == [
        reported(identifier=reference, title=None, live_state=None, is_ready=False)
    ]
