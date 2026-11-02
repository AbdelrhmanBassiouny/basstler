"""
The Actions usage monitor: how many runs and jobs each workflow took in the last 24
hours, compared with the daily ceilings of the repository's budget.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, UTC
from enum import StrEnum
from pathlib import PurePosixPath
from urllib.parse import quote

from basstler.actions_budget import ActionsBudget, WorkflowLimits
from basstler.environment import GitHubActionsVariable
from basstler.repository import Repository
from basstler.github.client import GitHubReader, GitHubRestClient

# %% vocabulary

RUNS_PER_PAGE = 100
"""
The most runs GitHub returns in one page.
"""

WINDOW = timedelta(days=1)
"""
How far back runs are counted: the period the daily ceilings are for.
"""


class UsageLevel(StrEnum):
    """
    How near a workflow's usage is to its ceilings, from the lowest to the highest.
    """

    WITHIN_BUDGET = "within budget"
    APPROACHING_CEILING = "approaching its ceiling"
    OVER_CEILING = "over its ceiling"

    @property
    def severity(self) -> int:
        """
        The position among the levels, which orders them.
        """
        return list(type(self)).index(self)


class UsageOutputKey(StrEnum):
    """
    The ``$GITHUB_OUTPUT`` keys the report sets.
    """

    OVER_BUDGET = "over_budget"
    """
    ``true`` when any workflow is over a ceiling.
    """


class WorkflowCommand(StrEnum):
    """
    The workflow commands the report prints.
    """

    WARNING = "::warning::"


# %% what one workflow used


@dataclass(frozen=True)
class WorkflowUsage:
    """
    One workflow's runs and jobs in the window, with the limits they are compared with.
    """

    workflow: str
    """
    The workflow's file name.
    """

    runs: int
    """
    The runs created in the window.
    """

    jobs: int
    """
    The jobs of those runs.
    """

    limits: WorkflowLimits
    """
    The limits the workflow is held to.
    """

    warning_fraction: float = 0.8
    """
    The share of a ceiling at which usage is flagged as approaching it.
    """

    @property
    def level(self) -> UsageLevel:
        """
        The highest level either count reaches against its ceiling; counts with no
        ceiling are within budget.
        """
        return max(
            (
                self._level_of(self.runs, self.limits.runs_per_day),
                self._level_of(self.jobs, self.limits.jobs_per_day),
            ),
            key=lambda level: level.severity,
        )

    def _level_of(self, count: int, ceiling: int | None) -> UsageLevel:
        """
        :param count: A count in the window.
        :param ceiling: Its daily ceiling, or ``None`` for no ceiling.
        :return: How near the count is to the ceiling.
        """
        if ceiling is None or count < ceiling * self.warning_fraction:
            return UsageLevel.WITHIN_BUDGET
        if count < ceiling:
            return UsageLevel.APPROACHING_CEILING
        return UsageLevel.OVER_CEILING

    def summary(self) -> str:
        """
        :return: One line naming the workflow, its level and its counts against the
            ceilings.
        """
        runs = self._counted(self.runs, self.limits.runs_per_day, "runs")
        jobs = self._counted(self.jobs, self.limits.jobs_per_day, "jobs")
        return f"{self.workflow}: {self.level}: {runs} and {jobs} in the last 24 hours"

    def annotation(self) -> str:
        """
        :return: The summary, as a workflow warning when the workflow is approaching or
            over a ceiling.
        """
        if self.level == UsageLevel.WITHIN_BUDGET:
            return self.summary()
        return f"{WorkflowCommand.WARNING}{self.summary()}"

    @staticmethod
    def _counted(count: int, ceiling: int | None, noun: str) -> str:
        """
        :param count: A count in the window.
        :param ceiling: Its daily ceiling, or ``None`` for no ceiling.
        :param noun: What is counted.
        :return: The count, with its ceiling when it has one.
        """
        if ceiling is None:
            return f"{count} {noun}"
        return f"{count} of {ceiling} {noun}"


# %% the report


@dataclass(frozen=True)
class UsageReport:
    """
    Every workflow's usage in the window.
    """

    usages: tuple[WorkflowUsage, ...]
    """
    The usage of each workflow that ran, in the order its first run was listed.
    """

    @classmethod
    def measure(
        cls,
        client: GitHubReader,
        repository: Repository,
        budget: ActionsBudget,
        now: datetime,
    ) -> UsageReport:
        """
        :param client: Where the runs and jobs are read from.
        :param repository: The repository whose runs are counted.
        :param budget: The budget whose ceilings the counts are compared with.
        :param now: The end of the window.
        :return: The usage of every workflow that ran in the window.
        """
        since = (now - WINDOW).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        query = quote(f">={since}", safe="")
        pages = client.get_pages(
            f"{repository.api_path}/actions/runs"
            f"?created={query}&per_page={RUNS_PER_PAGE}"
        )
        runs_by_workflow: dict[str, int] = {}
        jobs_by_workflow: dict[str, int] = {}
        for page in pages:
            for run in page["workflow_runs"]:
                workflow = PurePosixPath(run["path"].split("@")[0]).name
                job_count = client.get(
                    f"{repository.api_path}/actions/runs/{run['id']}/jobs?per_page=1"
                )["total_count"]
                runs_by_workflow[workflow] = runs_by_workflow.get(workflow, 0) + 1
                jobs_by_workflow[workflow] = (
                    jobs_by_workflow.get(workflow, 0) + job_count
                )
        return cls(
            usages=tuple(
                WorkflowUsage(
                    workflow=workflow,
                    runs=runs,
                    jobs=jobs_by_workflow[workflow],
                    limits=budget.limits_of(workflow),
                )
                for workflow, runs in runs_by_workflow.items()
            )
        )

    @property
    def flagged(self) -> tuple[WorkflowUsage, ...]:
        """
        The workflows approaching or over a ceiling.
        """
        return tuple(
            usage for usage in self.usages if usage.level != UsageLevel.WITHIN_BUDGET
        )

    @property
    def is_over_budget(self) -> bool:
        """
        Whether any workflow is over a ceiling.
        """
        return any(usage.level == UsageLevel.OVER_CEILING for usage in self.usages)

    def markdown(self) -> str:
        """
        :return: The report as a Markdown table, for a job summary.
        """
        rows = "\n".join(
            f"| {usage.workflow} | {usage.runs} | {usage.jobs} | {usage.level} |"
            for usage in self.usages
        )
        return (
            f"| Workflow | Runs | Jobs | Level |\n| --- | --- | --- | --- |\n{rows}\n"
        )


# %% the command


def main() -> None:
    """
    Print the last 24 hours of Actions usage against the repository's budget.
    """
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("--repository", required=True, type=Repository.parse)
    parser.add_argument(
        "--flagged-only",
        action="store_true",
        help="Print only the workflows approaching or over a ceiling.",
    )
    parser.add_argument(
        "--github-actions",
        action="store_true",
        help="Annotate the flagged workflows, write the job summary and the output.",
    )
    arguments = parser.parse_args()
    budget = ActionsBudget.load()
    if not budget.has_daily_ceilings:
        return
    report = UsageReport.measure(
        GitHubRestClient(),
        arguments.repository,
        budget,
        datetime.now(UTC),
    )
    for usage in report.flagged if arguments.flagged_only else report.usages:
        sys.stdout.write(
            f"{usage.annotation() if arguments.github_actions else usage.summary()}\n"
        )
    if not arguments.github_actions:
        return
    summary_path = GitHubActionsVariable.STEP_SUMMARY.read()
    if summary_path:
        with open(summary_path, "a") as summary:
            summary.write(report.markdown())
    output_path = GitHubActionsVariable.OUTPUT.read()
    if output_path:
        with open(output_path, "a") as output:
            output.write(
                f"{UsageOutputKey.OVER_BUDGET}={str(report.is_over_budget).lower()}\n"
            )


if __name__ == "__main__":
    main()
