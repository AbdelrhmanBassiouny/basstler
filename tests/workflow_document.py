"""
A GitHub Actions workflow document, parsed into the parts the suites assert on.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

# %% vocabulary


class WorkflowKey(StrEnum):
    """
    The keys of a workflow document the suites read.
    """

    JOBS = "jobs"
    """
    The jobs, by identifier.
    """

    STEPS = "steps"
    """
    A job's steps, in order.
    """

    NAME = "name"
    """
    A step's display name.
    """

    RUN = "run"
    """
    A step's shell script.
    """

    USES = "uses"
    """
    The reusable workflow a job calls, as ``<repository>/<path>@<branch or tag>``.
    """

    WITH = "with"
    """
    The inputs a job hands the workflow it calls.
    """

    TYPES = "types"
    """
    The activity types an event is narrowed to.
    """


class WorkflowEvent(StrEnum):
    """
    The events a workflow can be started by that the suites name.
    """

    PULL_REQUEST = "pull_request"
    """
    Activity on a pull request of the repository.
    """

    WORKFLOW_DISPATCH = "workflow_dispatch"
    """
    A run started by hand or through the API.
    """


class PullRequestActivity(StrEnum):
    """
    The activity types a :attr:`WorkflowEvent.PULL_REQUEST` trigger can be narrowed to
    that the suites name.

    .. note:: These are events on a pull request, not the states it can be in.
    """

    OPENED = "opened"
    """
    The pull request was opened.
    """

    READY_FOR_REVIEW = "ready_for_review"
    """
    The pull request left draft.
    """

    CLOSED = "closed"
    """
    The pull request was merged or closed.
    """


class WorkflowInput(StrEnum):
    """
    The inputs this repository's reusable workflows take that the suites read.
    """

    BASSTLER_BRANCH_OR_TAG = "basstler_branch_or_tag"
    """
    The basstler branch or tag the called workflow installs the package at.
    """


# %% the document


@dataclass(frozen=True)
class WorkflowStep:
    """
    One step of a job.
    """

    name: str | None
    """
    Its display name, if it has one.
    """

    script: str | None
    """
    The shell it runs, if it runs one rather than an action.
    """

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> WorkflowStep:
        """
        :param data: The step as the document writes it.
        :return: The parsed step.
        """
        return cls(name=data.get(WorkflowKey.NAME), script=data.get(WorkflowKey.RUN))


@dataclass(frozen=True)
class ReusableWorkflowCall:
    """
    The reusable workflow a job calls.
    """

    workflow: str
    """
    The workflow called, as ``<repository>/<path>``.
    """

    branch_or_tag: str
    """
    The branch or tag it is called at.
    """

    @classmethod
    def parse(cls, uses: str) -> ReusableWorkflowCall:
        """
        :param uses: The job's ``uses`` value.
        :return: The parsed call.
        """
        workflow, branch_or_tag = uses.rsplit("@", 1)
        return cls(workflow=workflow, branch_or_tag=branch_or_tag)


@dataclass(frozen=True)
class WorkflowJob:
    """
    One job of a workflow: steps it runs, or a reusable workflow it calls.
    """

    steps: tuple[WorkflowStep, ...]
    """
    The steps it runs, in order.
    """

    call: ReusableWorkflowCall | None
    """
    The reusable workflow it calls, if it calls one.
    """

    inputs: dict[str, Any]
    """
    The inputs it hands the workflow it calls.
    """

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> WorkflowJob:
        """
        :param data: The job as the document writes it.
        :return: The parsed job.
        """
        uses = data.get(WorkflowKey.USES)
        return cls(
            steps=tuple(
                WorkflowStep.from_mapping(step)
                for step in data.get(WorkflowKey.STEPS, [])
            ),
            call=ReusableWorkflowCall.parse(uses) if uses is not None else None,
            inputs=data.get(WorkflowKey.WITH, {}),
        )

    def script_of(self, step_name: str) -> str:
        """
        :param step_name: The display name of one of its steps.
        :return: The shell that step runs.
        """
        return next(step.script for step in self.steps if step.name == step_name)


@dataclass(frozen=True)
class WorkflowDocument:
    """
    A workflow file, parsed.
    """

    triggers: dict[str, tuple[str, ...]]
    """
    Every event that starts it, each with the activity types it is narrowed to - none
    when it is not narrowed.
    """

    jobs: dict[str, WorkflowJob]
    """
    Its jobs, by identifier.
    """

    @classmethod
    def read(cls, path: Path) -> WorkflowDocument:
        """
        :param path: The workflow file.
        :return: The parsed document.
        """
        data = yaml.safe_load(path.read_text())
        # YAML 1.1 reads the bare key ``on`` as ``True``.
        events = data[True]
        return cls(
            triggers={
                event: tuple((narrowing or {}).get(WorkflowKey.TYPES, ()))
                for event, narrowing in events.items()
            },
            jobs={
                identifier: WorkflowJob.from_mapping(job)
                for identifier, job in data[WorkflowKey.JOBS].items()
            },
        )

    @property
    def only_job(self) -> WorkflowJob:
        """
        :return: Its one job.
        """
        (job,) = self.jobs.values()
        return job
