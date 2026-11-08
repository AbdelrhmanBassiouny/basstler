"""
One run of a GitHub Actions workflow, and the jobs it ran.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from pydantic import Field

from basstler.class_property import classproperty
from basstler.github.client import GitHubWrite, HttpMethod
from basstler.locations import WorkflowLocation
from basstler.repository import Repository
from basstler.github.states import CheckOutcome, ConclusionOutcome
from basstler.json_model import JSONModel, ValidatedJSONModel

# %% a run


class WorkflowRun(ValidatedJSONModel):
    """
    One run of a workflow.
    """

    identifier: Annotated[int, Field(alias="id")]
    """
    The run's own number, which its page is addressed by.
    """

    commit: Annotated[str, Field(alias="head_sha")]
    """
    The commit it ran on.
    """

    outcome: Annotated[ConclusionOutcome, Field(alias="conclusion")]
    """
    How it ended, :attr:`CheckOutcome.PENDING` while it runs.
    """

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


# %% starting a run


class WorkflowDispatch(GitHubWrite):
    """
    A request to run a workflow.
    """

    repository: Annotated[Repository, Field(exclude=True)]
    """
    The repository the workflow belongs to.
    """

    workflow: Annotated[WorkflowLocation, Field(exclude=True)]
    """
    The workflow to run.
    """

    branch: Annotated[str, Field(alias="ref")]
    """
    The branch the workflow runs on.
    """

    @classproperty
    def method(cls) -> HttpMethod:
        return HttpMethod.POST

    @property
    def path(self) -> str:
        return self.repository.workflow_dispatch_path(self.workflow)
