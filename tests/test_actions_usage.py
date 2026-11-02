"""
The Actions usage monitor: the last 24 hours of runs and jobs per workflow, compared
with the daily ceilings the budget sets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from typing import Any

import pytest

from basstler.actions_budget import ActionsBudget, WorkflowLimits
from basstler.actions_usage import (
    UsageLevel,
    UsageReport,
    WorkflowCommand,
    WorkflowUsage,
)
from basstler.repository import Repository
from basstler.upstream_reviews.clients import RestClient

# %% a client that answers from a table

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
REPOSITORY = Repository(owner="owner", name="project")
TESTS_WORKFLOW = "tests.yml"
RELEASE_WORKFLOW = "release.yml"


@dataclass
class CannedResponseClient(RestClient):
    """
    A client that answers a REST path from a table instead of calling GitHub.
    """

    runs_by_workflow: dict[str, int]
    """
    How many runs each workflow had in the window.
    """

    jobs_per_run: int = 2
    """
    How many jobs every run had.
    """

    requested_paths: list[str] = field(default_factory=list)
    """
    Every path asked for, oldest first.
    """

    def get(self, path: str) -> Any:
        self.requested_paths.append(path)
        return {"total_count": self.jobs_per_run}

    def get_pages(self, path: str) -> list[Any]:
        self.requested_paths.append(path)
        runs = [
            {
                "id": len(self.runs_by_workflow) * 100 + number,
                "path": f".github/workflows/{name}",
            }
            for name, count in self.runs_by_workflow.items()
            for number in range(count)
        ]
        return [{"workflow_runs": runs[:2]}, {"workflow_runs": runs[2:]}]


def measure(
    runs_by_workflow: dict[str, int], budget: ActionsBudget, jobs_per_run: int = 2
) -> UsageReport:
    """
    :param runs_by_workflow: How many runs each workflow had in the window.
    :param budget: The budget the usage is compared with.
    :param jobs_per_run: How many jobs every run had.
    :return: The report measured through a canned client.
    """
    return UsageReport.measure(
        CannedResponseClient(runs_by_workflow, jobs_per_run), REPOSITORY, budget, NOW
    )


# %% counting the window


def test_counts_runs_and_jobs_per_workflow_across_pages() -> None:
    report = measure({TESTS_WORKFLOW: 3, RELEASE_WORKFLOW: 1}, ActionsBudget())

    assert report.usages == (
        WorkflowUsage(workflow=TESTS_WORKFLOW, runs=3, jobs=6, limits=WorkflowLimits()),
        WorkflowUsage(
            workflow=RELEASE_WORKFLOW, runs=1, jobs=2, limits=WorkflowLimits()
        ),
    )


def test_asks_only_for_runs_created_in_the_last_day() -> None:
    client = CannedResponseClient({TESTS_WORKFLOW: 1})

    UsageReport.measure(client, REPOSITORY, ActionsBudget(), NOW)

    window_start = (NOW - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert client.requested_paths[0].startswith(f"{REPOSITORY.api_path}/actions/runs?")
    assert window_start in client.requested_paths[0].replace("%3A", ":")


# %% comparing with the ceilings


@pytest.mark.parametrize(
    ("runs", "level"),
    [
        (7, UsageLevel.WITHIN_BUDGET),
        (8, UsageLevel.APPROACHING_CEILING),
        (9, UsageLevel.APPROACHING_CEILING),
        (10, UsageLevel.OVER_CEILING),
        (25, UsageLevel.OVER_CEILING),
    ],
)
def test_level_follows_the_runs_against_the_ceiling(
    runs: int, level: UsageLevel
) -> None:
    budget = ActionsBudget(defaults=WorkflowLimits(runs_per_day=10))

    report = measure({TESTS_WORKFLOW: runs}, budget)

    assert report.usages[0].level == level


def test_level_follows_the_jobs_when_they_are_the_nearer_ceiling() -> None:
    budget = ActionsBudget(defaults=WorkflowLimits(runs_per_day=100, jobs_per_day=10))

    report = measure({TESTS_WORKFLOW: 5}, budget, jobs_per_run=2)

    assert report.usages[0].level == UsageLevel.OVER_CEILING


def test_a_workflow_without_ceilings_is_never_flagged() -> None:
    report = measure({TESTS_WORKFLOW: 10_000}, ActionsBudget())

    assert report.usages[0].level == UsageLevel.WITHIN_BUDGET


def test_an_override_sets_its_own_ceiling() -> None:
    budget = ActionsBudget(
        defaults=WorkflowLimits(runs_per_day=100),
        overrides={TESTS_WORKFLOW: WorkflowLimits(runs_per_day=2)},
    )

    report = measure({TESTS_WORKFLOW: 2, RELEASE_WORKFLOW: 2}, budget)

    assert [usage.level for usage in report.usages] == [
        UsageLevel.OVER_CEILING,
        UsageLevel.WITHIN_BUDGET,
    ]


# %% what the report says


def test_report_is_over_budget_when_any_workflow_is() -> None:
    budget = ActionsBudget(defaults=WorkflowLimits(runs_per_day=2))

    assert measure({TESTS_WORKFLOW: 2}, budget).is_over_budget
    assert not measure({TESTS_WORKFLOW: 1}, budget).is_over_budget


def test_warnings_name_only_the_workflows_that_are_flagged() -> None:
    budget = ActionsBudget(defaults=WorkflowLimits(runs_per_day=10))

    report = measure({TESTS_WORKFLOW: 9, RELEASE_WORKFLOW: 1}, budget)

    assert [usage.workflow for usage in report.flagged] == [TESTS_WORKFLOW]


def test_flagged_usage_states_the_counts_and_the_ceiling() -> None:
    budget = ActionsBudget(defaults=WorkflowLimits(runs_per_day=10))

    usage = measure({TESTS_WORKFLOW: 9}, budget).usages[0]

    assert usage.summary() == (
        f"{TESTS_WORKFLOW}: {UsageLevel.APPROACHING_CEILING}: 9 of 10 runs and 18 jobs"
        " in the last 24 hours"
    )


def test_annotation_is_a_workflow_warning_only_when_flagged() -> None:
    budget = ActionsBudget(defaults=WorkflowLimits(runs_per_day=10))

    report = measure({TESTS_WORKFLOW: 9, RELEASE_WORKFLOW: 1}, budget)

    flagged, quiet = report.usages
    assert flagged.annotation() == f"{WorkflowCommand.WARNING}{flagged.summary()}"
    assert quiet.annotation() == quiet.summary()


def test_markdown_lists_every_workflow_with_its_counts_and_level() -> None:
    budget = ActionsBudget(defaults=WorkflowLimits(runs_per_day=10))

    markdown = measure({TESTS_WORKFLOW: 9}, budget).markdown()

    assert markdown.splitlines()[2] == (
        f"| {TESTS_WORKFLOW} | 9 | 18 | {UsageLevel.APPROACHING_CEILING} |"
    )


# %% whether there is anything to measure


def test_a_budget_has_daily_ceilings_when_any_limits_set_one() -> None:
    assert not ActionsBudget().has_daily_ceilings
    assert ActionsBudget(defaults=WorkflowLimits(jobs_per_day=5)).has_daily_ceilings
    assert ActionsBudget(
        overrides={TESTS_WORKFLOW: WorkflowLimits(runs_per_day=5)}
    ).has_daily_ceilings
