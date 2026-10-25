"""
A GitHub Actions workflow file, parsed into the parts the suites check.
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
    Every key read out of a workflow file.
    """

    JOBS = "jobs"
    STEPS = "steps"
    OUTPUTS = "outputs"
    CONDITION = "if"
    USES = "uses"
    IDENTIFIER = "id"
    RUN = "run"
    CONCURRENCY = "concurrency"
    GROUP = "group"
    CANCEL_IN_PROGRESS = "cancel-in-progress"


class WorkflowTrigger(StrEnum):
    """
    The events a workflow runs on, as its ``on`` key names them.
    """

    WORKFLOW_CALL = "workflow_call"


class ExpressionDelimiter(StrEnum):
    """
    The marks around an expression GitHub evaluates.
    """

    OPENING = "${{"
    CLOSING = "}}"


class ActionVersionSeparator(StrEnum):
    """
    The mark between an action and the version a step pins it at.
    """

    AT = "@"


class ExpressionLiteral(StrEnum):
    """
    The literals an expression compares an output with.
    """

    TRUE = "'true'"


# %% expressions


@dataclass(frozen=True)
class StepOutputReference:
    """
    An expression reading one output of one step of the same job.
    """

    step_identifier: str
    """
    The step's ``id``.
    """

    output_name: str
    """
    The output the step writes.
    """

    @classmethod
    def from_expression(cls, expression: str) -> StepOutputReference:
        """
        :param expression: ``${{ steps.<id>.outputs.<name> }}``.
        :return: The step and output it reads.
        """
        inner = (
            expression.removeprefix(ExpressionDelimiter.OPENING)
            .removesuffix(ExpressionDelimiter.CLOSING)
            .strip()
        )
        _, step_identifier, _, output_name = inner.split(".")
        return cls(step_identifier, output_name)

    @property
    def true_condition(self) -> str:
        """
        The condition that holds when this output is ``true``.
        """
        return (
            f"steps.{self.step_identifier}.outputs.{self.output_name} "
            f"== {ExpressionLiteral.TRUE}"
        )


@dataclass(frozen=True)
class JobOutputReference:
    """
    An expression reading one output of a job the reading job needs.
    """

    job_name: str
    """
    The needed job.
    """

    output_name: str
    """
    The output it declares.
    """

    @property
    def true_condition(self) -> str:
        """
        The condition that holds when this output is ``true``.
        """
        return (
            f"needs.{self.job_name}.outputs.{self.output_name} "
            f"== {ExpressionLiteral.TRUE}"
        )


# %% workflow parts


@dataclass(frozen=True)
class WorkflowStep:
    """
    One step of a job.
    """

    identifier: str | None
    """
    Its ``id``, unset when nothing reads its outputs.
    """

    action: str | None
    """
    The action it uses, without the version it pins, unset for a shell step.
    """

    command: str | None
    """
    The shell it runs, unset for an action step.
    """

    condition: str | None
    """
    The condition it runs under, unset when it always runs.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> WorkflowStep:
        """
        :param data: The step as the workflow file writes it.
        :return: The parsed step.
        """
        uses = data.get(WorkflowKey.USES)
        return cls(
            data.get(WorkflowKey.IDENTIFIER),
            uses.partition(ActionVersionSeparator.AT)[0] if uses else None,
            data.get(WorkflowKey.RUN),
            data.get(WorkflowKey.CONDITION),
        )


@dataclass(frozen=True)
class WorkflowJob:
    """
    One job of a workflow.
    """

    name: str
    """
    Its key under ``jobs``.
    """

    steps: list[WorkflowStep]
    """
    Its steps, in order.
    """

    outputs: dict[str, StepOutputReference]
    """
    Each output it declares, by name, and the step output it reads.
    """

    condition: str | None
    """
    The condition it runs under, unset when it always runs.
    """

    @classmethod
    def from_json(cls, name: str, data: dict[str, Any]) -> WorkflowJob:
        """
        :param name: Its key under ``jobs``.
        :param data: The job as the workflow file writes it.
        :return: The parsed job.
        """
        return cls(
            name,
            [WorkflowStep.from_json(step) for step in data.get(WorkflowKey.STEPS, [])],
            {
                output_name: StepOutputReference.from_expression(expression)
                for output_name, expression in data.get(WorkflowKey.OUTPUTS, {}).items()
            },
            data.get(WorkflowKey.CONDITION),
        )

    def step_using(self, action: str) -> WorkflowStep:
        """
        :param action: An action, without its version.
        :return: The one step that uses it.
        """
        (step,) = (step for step in self.steps if step.action == action)
        return step

    def step_identified_as(self, identifier: str) -> WorkflowStep:
        """
        :param identifier: A step's ``id``.
        :return: That step.
        """
        (step,) = (step for step in self.steps if step.identifier == identifier)
        return step

    def output(self, output_name: str) -> JobOutputReference:
        """
        :param output_name: An output this job declares.
        :return: The expression a job needing this one reads it with.
        """
        return JobOutputReference(self.name, output_name)


@dataclass(frozen=True)
class Concurrency:
    """
    How runs sharing a group wait for each other.
    """

    group: str
    """
    The group whose runs wait for each other.
    """

    cancel_in_progress: bool
    """
    Whether a new run cancels the one running, rather than waiting for it.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Concurrency:
        """
        :param data: The ``concurrency`` mapping.
        :return: The parsed setting.
        """
        return cls(
            data[WorkflowKey.GROUP], data.get(WorkflowKey.CANCEL_IN_PROGRESS, False)
        )


@dataclass(frozen=True)
class Workflow:
    """
    A workflow file.
    """

    triggers: set[str]
    """
    The events it runs on.
    """

    jobs: dict[str, WorkflowJob]
    """
    Its jobs, by name.
    """

    concurrency: Concurrency | None
    """
    How its runs wait for each other, unset when they run side by side.
    """

    @classmethod
    def from_json(cls, data: dict[Any, Any]) -> Workflow:
        """
        :param data: The workflow file as YAML loads it, which reads the ``on`` key as
            ``True``.
        :return: The parsed workflow.
        """
        concurrency = data.get(WorkflowKey.CONCURRENCY)
        return cls(
            set(data[True]),
            {
                name: WorkflowJob.from_json(name, job)
                for name, job in data[WorkflowKey.JOBS].items()
            },
            Concurrency.from_json(concurrency) if concurrency else None,
        )

    @classmethod
    def read(cls, path: Path) -> Workflow:
        """
        :param path: A workflow file.
        :return: The parsed workflow.
        """
        return cls.from_json(yaml.safe_load(path.read_text()))
