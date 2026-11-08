"""
One run of a GitHub Actions workflow, and the jobs it ran.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from basstler.class_property import classproperty
from basstler.repository import Repository
from basstler.upstream_reviews.vocabulary import CheckOutcome, JSONModel

# %% a run


@dataclass(frozen=True)
class WorkflowRun(JSONModel):
    """
    One run of a workflow.
    """

    identifier: int
    """
    The run's own number, which its page is addressed by.
    """

    commit: str
    """
    The commit it ran on.
    """

    outcome: CheckOutcome
    """
    How it ended, :attr:`CheckOutcome.PENDING` while it runs.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> WorkflowRun:
        return cls(
            data["id"],
            data["head_sha"],
            CheckOutcome.from_conclusion(data["conclusion"]),
        )

    @property
    def failed(self) -> bool:
        """:return: Whether it ended without succeeding."""
        return self.outcome not in {CheckOutcome.SUCCESS, CheckOutcome.PENDING}


# %% the jobs it ran


@dataclass(frozen=True)
class RunJob(JSONModel):
    """
    One job of a workflow run.
    """

    name: str
    """
    The job's name, as the run lists it.
    """

    outcome: CheckOutcome
    """
    How it ended, :attr:`CheckOutcome.PENDING` while it runs.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RunJob:
        return cls(data["name"], CheckOutcome.from_conclusion(data["conclusion"]))


@dataclass(frozen=True)
class RunJobPage(JSONModel):
    """
    The jobs one workflow run lists, as many as one page holds.
    """

    jobs: list[RunJob]
    """
    The jobs, in the order the run lists them.
    """

    @classproperty
    def maximum_jobs_per_page(cls) -> int:
        """
        The most jobs GitHub lists on one page.
        """
        return 100

    @classmethod
    def path(cls, repository: Repository, run: int) -> str:
        """
        :param repository: The repository the run ran in.
        :param run: The run's own number.
        :return: The REST path listing its jobs.
        """
        return (
            f"{repository.workflow_run_path(run)}/jobs"
            f"?per_page={cls.maximum_jobs_per_page}"
        )

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RunJobPage:
        return cls([RunJob.from_json(job) for job in data["jobs"]])
