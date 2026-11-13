"""
Tests for :mod:`basstler.plan_site.plan_page`: the walkthrough's sample plan renders as
the walkthrough describes.
"""

from __future__ import annotations

import json

import yaml

from basstler.plan.model import ItemStatus
from basstler.plan.validation import PlanValidator
from basstler.plan_site.plan import Plan
from basstler.plan_site.plan_page import PlanPage, RenderedPlanPage
from basstler.pull_request_state import (
    PullRequestRecord,
)
from basstler.pull_request_state import LivePullRequests

from .plan_page_builders import (
    EXAMPLE_DIRECTORY,
    STYLESHEET_URL,
)

# %% example-walkthrough.md's committed sample plan


def _render_example_plan() -> RenderedPlanPage:
    plan_mapping = yaml.safe_load((EXAMPLE_DIRECTORY / "plan.yaml").read_text())
    PlanValidator(plan_mapping).validate()
    plan = Plan.from_mapping(plan_mapping)
    pull_requests_by_repository = PullRequestRecord.parse_by_repository(
        json.loads((EXAMPLE_DIRECTORY / "pr_data.json").read_text())
    )
    renderer = PlanPage(
        stylesheet_url=STYLESHEET_URL,
        plan=plan,
        roadmap_text=(EXAMPLE_DIRECTORY / "roadmap.md").read_text(),
        live_pull_requests=LivePullRequests(pull_requests_by_repository),
    )
    return renderer.render()


def test_example_plan_passes_the_same_validation_plan_create_must_satisfy():
    plan_mapping = yaml.safe_load((EXAMPLE_DIRECTORY / "plan.yaml").read_text())
    PlanValidator(plan_mapping).validate()  # raises PlanValidationError on any problem


def test_example_plan_renders_the_counts_and_sections_the_walkthrough_describes():
    """Locks example-walkthrough.md's screenshots and prose to the actual
    schema/logic - a future change to either would fail this test instead of
    silently leaving the doc showing stale numbers."""
    summary = _render_example_plan().overview
    assert summary.status_counts[ItemStatus.NOT_STARTED] == 1
    assert summary.status_counts[ItemStatus.IN_PROGRESS] == 2
    assert summary.status_counts[ItemStatus.BLOCKED] == 1
    assert summary.status_counts[ItemStatus.DONE] == 2
    assert summary.drift_items == ["Dead-letter queue for exhausted retries"]
    assert summary.ready_to_start == ["Retry metrics"]
    assert summary.blocker_maybe_cleared == [
        "Load-test the retry path under failure injection"
    ]
    assert summary.ready_to_review == [
        "Circuit breaker around the retry loop",
        "Feature flag for the new retry behavior",
    ]
