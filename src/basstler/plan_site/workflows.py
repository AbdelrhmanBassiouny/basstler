"""
The GitHub Actions workflows publishing the plan site writes, and the parsed shape of a
written one.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import yaml

from basstler.class_property import classproperty
from basstler.environment import GitHubCredentialVariable
from basstler.locations import WorkflowLocation
from basstler.render_common import create_template_environment
from basstler.repository import Repository
from basstler.json_model import JSONModel
from basstler.upstream_reviews.action.branch import BasstlerSource

if TYPE_CHECKING:
    from basstler.plan_site.site_repository import SiteRepository

# %% names


class PlanSiteSecret(StrEnum):
    """
    The Actions secrets the plan site's workflows read.
    """

    TOKEN = "PLAN_SITE_TOKEN"
    """
    The user's fine-grained token, stored on each notes repository, that lets its
    dispatch workflow start the build in the site repository.
    """

    READ_TOKEN = "PLAN_SITE_READ_TOKEN"
    """
    The user's read-only token, stored on the site repository, that lets the build
    read private repositories.
    """

    @classproperty
    def private_repository_correction(cls) -> str:
        """
        How the build comes to read a private repository, as a clause of a correction.
        """
        return (
            f"for a private repository, store a read-only token as {cls.READ_TOKEN} on "
            "the site repository and re-run plan_site.publication "
            "(/setup-personal-notes), so the site workflow passes it to the build"
        )

    def path_on(self, repository: Repository) -> str:
        """
        :param repository: The repository that stores it.
        :return: The REST path of its metadata there.
        """
        return f"{repository.api_path}/actions/secrets/{self}"


class PlanSiteJob(StrEnum):
    """
    The job each of the plan site's workflows runs.
    """

    BUILD = "build"
    """
    The site workflow's job, which calls basstler's build.
    """

    DISPATCH = "dispatch"
    """
    The dispatch workflow's job, which starts the site workflow.
    """


class GitHubCommandLineOption(StrEnum):
    """
    The ``gh`` options the plan site's workflows pass.
    """

    REPOSITORY = "--repo"
    """
    The ``owner/name`` repository a command acts on.
    """


class BuildInput(StrEnum):
    """
    The inputs of basstler's reusable build, :attr:`WorkflowLocation.PLAN_SITE_BUILD`.
    """

    BRANCH_OR_TAG = "basstler_branch_or_tag"
    """
    The basstler branch or release tag whose renderer builds the site.
    """

    REGISTRY = "registry"
    """
    The ``owner/name`` repository whose notes hold the complete hub file.
    """


class BuildSecret(StrEnum):
    """
    The secrets basstler's reusable build, :attr:`WorkflowLocation.PLAN_SITE_BUILD`,
    accepts.
    """

    READ_TOKEN = "read_token"
    """
    The token that reads the notes repositories in place of the site repository's own.
    """


class PlanSiteTemplate(StrEnum):
    """
    The templates in :attr:`PackageLocation.TEMPLATES` the site's workflows are rendered
    from.
    """

    SITE_WORKFLOW = "plan_site_workflow.yml"
    """
    The workflow on the site repository.
    """

    DISPATCH_WORKFLOW = "plan_site_dispatch_workflow.yml"
    """
    The workflow on a notes branch.
    """

    MERGE_WORKFLOW = "plan_site_merge_workflow.yml"
    """
    The workflow on a notes repository's default branch.
    """

    def render(self, **context: Any) -> str:
        """
        :param context: The values the template substitutes, by name.
        :return: The rendered file, without its final newline.
        """
        template = create_template_environment().get_template(self.value)
        return template.render(**context).rstrip("\n")


# %% a written workflow, parsed


class WorkflowKey(StrEnum):
    """
    Every key read out of a workflow file.
    """

    TRIGGERS = "on"
    """
    The events that start the workflow, by event.
    """

    PUSH = "push"
    """
    The push event, under :attr:`TRIGGERS`.
    """

    BRANCHES = "branches"
    """
    The branches a push to starts the workflow, under :attr:`PUSH`.
    """

    JOBS = "jobs"
    """
    The workflow's jobs, by job.
    """

    CONDITION = "if"
    """
    The expression a job runs only when true.
    """

    CALLED_WORKFLOW = "uses"
    """
    The reusable workflow a job calls, as ``owner/name/path@branch-or-tag``.
    """

    INPUTS = "with"
    """
    The inputs a job passes to its called workflow, by input.
    """

    SECRETS = "secrets"
    """
    The secrets a job passes to its called workflow, by secret.
    """

    STEPS = "steps"
    """
    A job's steps, in order.
    """

    ENVIRONMENT = "env"
    """
    The environment variables a step sets, by variable.
    """

    COMMAND = "run"
    """
    The shell command a step runs.
    """


@dataclass(frozen=True)
class WorkflowStep(JSONModel):
    """
    One step of a job that runs a shell command.
    """

    command: str
    """
    The shell command.
    """

    environment: dict[str, str] = field(default_factory=dict)
    """
    The environment variables it sets, by variable.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> WorkflowStep:
        """
        :param data: One step.
        :return: The parsed step.
        """
        return cls(data[WorkflowKey.COMMAND], data.get(WorkflowKey.ENVIRONMENT, {}))


@dataclass(frozen=True)
class WorkflowJob(JSONModel):
    """
    One job of a workflow: either it calls a reusable workflow or it runs steps.
    """

    condition: str | None = None
    """
    The expression it runs only when true, ``None`` when it always runs.
    """

    called_workflow: str | None = None
    """
    The reusable workflow it calls, as ``owner/name/path@branch-or-tag``.
    """

    inputs: dict[str, str] = field(default_factory=dict)
    """
    The inputs it passes to :attr:`called_workflow`, by input.
    """

    steps: list[WorkflowStep] = field(default_factory=list)
    """
    The steps it runs, in order.
    """

    secrets: dict[str, str] = field(default_factory=dict)
    """
    The secrets it passes to :attr:`called_workflow`, by secret.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> WorkflowJob:
        """
        :param data: One job.
        :return: The parsed job.
        """
        return cls(
            data.get(WorkflowKey.CONDITION),
            data.get(WorkflowKey.CALLED_WORKFLOW),
            data.get(WorkflowKey.INPUTS, {}),
            [WorkflowStep.from_json(step) for step in data.get(WorkflowKey.STEPS, [])],
            data.get(WorkflowKey.SECRETS, {}),
        )


@dataclass(frozen=True)
class WorkflowFile(JSONModel):
    """
    What a written workflow file says about when it runs and what its jobs do.
    """

    pushed_branches: list[str]
    """
    The branches a push to starts it, empty when no push does.
    """

    jobs: dict[str, WorkflowJob]
    """
    Its jobs, by job.
    """

    @classmethod
    def from_text(cls, workflow_text: str) -> WorkflowFile:
        """
        :param workflow_text: The workflow file's text.
        :return: The parsed workflow, every value read as text.
        """
        return cls.from_json(yaml.load(workflow_text, Loader=yaml.BaseLoader))

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> WorkflowFile:
        """
        :param data: The whole workflow file.
        :return: The parsed workflow.
        """
        push = data[WorkflowKey.TRIGGERS].get(WorkflowKey.PUSH, {})
        return cls(
            push.get(WorkflowKey.BRANCHES, []),
            {
                job: WorkflowJob.from_json(job_data)
                for job, job_data in data[WorkflowKey.JOBS].items()
            },
        )


# %% the workflows publishing writes


@dataclass(frozen=True)
class PlanSiteWorkflow(ABC):
    """
    A workflow file publishing writes, rendered from its template.
    """

    @classproperty
    @abstractmethod
    def location(cls) -> WorkflowLocation:
        """
        Where the workflow is written, relative to its branch's root.
        """

    @classproperty
    @abstractmethod
    def template(cls) -> PlanSiteTemplate:
        """
        The template it is rendered from.
        """

    @property
    @abstractmethod
    def template_values(self) -> dict[str, Any]:
        """
        :return: The values :attr:`template` substitutes, by name.
        """

    @property
    def text(self) -> str:
        """:return: The workflow."""
        return self.template.render(**self.template_values)


@dataclass(frozen=True)
class SiteWorkflow(PlanSiteWorkflow):
    """
    The site repository's workflow, which calls basstler's build.
    """

    branch_or_tag: str
    """
    The basstler branch or release tag whose build it runs.
    """

    registry: Repository
    """
    The repository whose notes hold the complete hub file.
    """

    @classproperty
    def location(cls) -> WorkflowLocation:
        return WorkflowLocation.PLAN_SITE

    @classproperty
    def template(cls) -> PlanSiteTemplate:
        return PlanSiteTemplate.SITE_WORKFLOW

    @classmethod
    def from_text(cls, workflow_text: str) -> SiteWorkflow:
        """
        :param workflow_text: A site workflow as written on the site repository.
        :return: The workflow it is.
        """
        inputs = WorkflowFile.from_text(workflow_text).jobs[PlanSiteJob.BUILD].inputs
        return cls(
            inputs[BuildInput.BRANCH_OR_TAG],
            Repository.parse(inputs[BuildInput.REGISTRY]),
        )

    @property
    def template_values(self) -> dict[str, Any]:
        return {
            "job": PlanSiteJob.BUILD,
            "called_workflow": (
                f"{BasstlerSource.REPOSITORY}/"
                f"{WorkflowLocation.PLAN_SITE_BUILD.as_posix()}@{self.branch_or_tag}"
            ),
            "inputs": {
                BuildInput.BRANCH_OR_TAG: self.branch_or_tag,
                BuildInput.REGISTRY: self.registry.full_name,
            },
            "secrets": {
                BuildSecret.READ_TOKEN: f"${{{{ secrets.{PlanSiteSecret.READ_TOKEN} }}}}"
            },
        }


@dataclass(frozen=True)
class DispatchWorkflow(PlanSiteWorkflow):
    """
    The notes branch's workflow that starts the site workflow on every push to it.
    """

    notes_repository: Repository
    """
    The repository the notes branch belongs to.
    """

    notes_branch: str
    """
    The notes branch.
    """

    site: SiteRepository
    """
    The site repository, whose default branch the site workflow is started on.
    """

    @classproperty
    def location(cls) -> WorkflowLocation:
        return WorkflowLocation.PLAN_SITE_DISPATCH

    @classproperty
    def template(cls) -> PlanSiteTemplate:
        return PlanSiteTemplate.DISPATCH_WORKFLOW

    @property
    def template_values(self) -> dict[str, Any]:
        return {
            "job": PlanSiteJob.DISPATCH,
            "repository_option": GitHubCommandLineOption.REPOSITORY,
            "notes_repository": self.notes_repository.full_name,
            "notes_branch": self.notes_branch,
            "site_repository": self.site.repository.full_name,
            "site_workflow_name": SiteWorkflow.location.name,
            "token_variable": GitHubCredentialVariable.GH_TOKEN,
            "token_secret": PlanSiteSecret.TOKEN,
        }


@dataclass(frozen=True)
class MergeWorkflow(PlanSiteWorkflow):
    """
    The notes repository's default-branch workflow that starts the site workflow
    whenever a pull request merges into it.
    """

    dispatch: DispatchWorkflow
    """
    The notes branch's workflow, whose build start this one runs on a merge instead of a
    push.
    """

    @classproperty
    def location(cls) -> WorkflowLocation:
        return WorkflowLocation.PLAN_SITE_MERGE

    @classproperty
    def template(cls) -> PlanSiteTemplate:
        return PlanSiteTemplate.MERGE_WORKFLOW

    @property
    def template_values(self) -> dict[str, Any]:
        return self.dispatch.template_values
