"""
Publish a repository's plans on the user's own plan site, and start the site's build on
every push to the repository's notes branch.

Writes the site repository's workflow, registers the repository in the hub file, and
commits the notes branch's dispatch workflow. Reports each step only the user can take -
creating the site repository, turning Pages on, storing the token - as one copyable line.
Run again, it re-checks them: a step counts as done once a run that needs it succeeded.

Usage:
    "${BASSTLER_PYTHON}" -m basstler.plan_site.publication --branch-or-tag <branch or tag> \\
        [--site-repository <owner/name>]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from basstler.class_property import classproperty
from basstler.locations import ClaudeCodeVariable, ProjectLocation, WorkflowLocation
from basstler.maintenance.git_commands import GitCommandRunner
from basstler.maintenance.remote_branch import RemoteBranch
from basstler.plan_site.exceptions import NotesRepositoryUnresolvedError
from basstler.plan_site.hub import PlanHub
from basstler.render_common import create_template_environment
from basstler.repository import GitHubAddress, Repository
from basstler.setup.steps import PersonalNotesSetting, resolve_repository
from basstler.standard_streams import StandardStreamHandler
from basstler.upstream_reviews.clients import GitHubCommandLineClient, RestClient
from basstler.upstream_reviews.vocabulary import BasstlerSource, CheckOutcome, JSONModel

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

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

    def render(self, **context: Any) -> str:
        """
        :param context: The values the template substitutes, by name.
        :return: The rendered file, without its final newline.
        """
        return create_template_environment().get_template(self.value).render(**context)


# %% the site repository


@dataclass(frozen=True)
class SiteRepository:
    """
    The repository the user owns that builds and serves the plan site.
    """

    repository: Repository
    """
    The repository on GitHub.
    """

    @classmethod
    def default_for(
        cls, notes_repository: Repository, name: str = "plans"
    ) -> SiteRepository:
        """
        :param notes_repository: The repository whose plans the site publishes.
        :param name: The site repository's name.
        :return: The repository of that name under the same owner.
        """
        return cls(Repository(notes_repository.owner, name))

    @property
    def site_url(self) -> str:
        """
        :return: The address GitHub Pages serves the repository's site from.
        """
        host = f"{self.repository.owner.lower()}.github.io"
        if self.repository.name.lower() == host:
            return f"https://{host}/"
        return f"https://{host}/{self.repository.name}/"


@dataclass(frozen=True)
class SiteWorkflow:
    """
    The site repository's workflow, as one basstler release writes it.
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
    def registry_line(cls) -> re.Pattern[str]:
        """
        The line of a written workflow naming its registry.
        """
        return re.compile(r"^\s*registry:\s*(?P<registry>\S+)\s*$", re.MULTILINE)

    @classmethod
    def registry_in(cls, text: str) -> Repository | None:
        """
        :param text: A site workflow as written on the site repository.
        :return: The registry it names, or ``None`` when it names none.
        """
        match = cls.registry_line.search(text)
        return Repository.parse(match["registry"]) if match else None

    @property
    def text(self) -> str:
        """:return: The workflow."""
        return PlanSiteTemplate.SITE_WORKFLOW.render(
            basstler_repository=BasstlerSource.REPOSITORY,
            build_workflow=WorkflowLocation.PLAN_SITE_BUILD.as_posix(),
            branch_or_tag=self.branch_or_tag,
            registry=self.registry.full_name,
        )


@dataclass(frozen=True)
class DispatchWorkflow:
    """
    The notes branch's workflow that starts the site's build on every push to it.
    """

    notes_repository: Repository
    """
    The repository the notes branch belongs to.
    """

    notes_branch: str
    """
    The notes branch.
    """

    site: Repository
    """
    The site repository whose workflow it starts.
    """

    site_branch: str
    """
    The site repository's branch its workflow runs on.
    """

    @property
    def text(self) -> str:
        """:return: The workflow."""
        return PlanSiteTemplate.DISPATCH_WORKFLOW.render(
            notes_repository=self.notes_repository.full_name,
            notes_branch=self.notes_branch,
            site_repository=self.site.full_name,
            site_branch=self.site_branch,
            site_workflow_name=WorkflowLocation.PLAN_SITE.name,
            token_secret=PlanSiteSecret.TOKEN,
        )


# %% the runs that confirm a step


class WorkflowRunKey(StrEnum):
    """
    Every field read out of a repository's run listing.
    """

    WORKFLOW_RUNS = "workflow_runs"
    PATH = "path"
    CONCLUSION = "conclusion"


@dataclass(frozen=True)
class ListedRun(JSONModel):
    """
    One run in a repository's run listing.
    """

    workflow: str
    """
    The path of the workflow file it ran.
    """

    outcome: CheckOutcome
    """
    How it ended, :attr:`CheckOutcome.PENDING` while it runs.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ListedRun:
        """
        :param data: One listed run.
        :return: The parsed run.
        """
        return cls(
            data[WorkflowRunKey.PATH],
            CheckOutcome.from_conclusion(data[WorkflowRunKey.CONCLUSION]),
        )


@dataclass(frozen=True)
class RunListing:
    """
    The latest runs on one branch of a repository, newest first.
    """

    runs: list[ListedRun]
    """
    The runs.
    """

    @staticmethod
    def path(repository: Repository, branch: str) -> str:
        """
        :param repository: The repository.
        :param branch: The branch the runs ran on.
        :return: The REST path listing them.
        """
        return f"{repository.api_path}/actions/runs?branch={branch}&per_page=20"

    @classmethod
    def read(
        cls, client: RestClient, repository: Repository, branch: str
    ) -> RunListing:
        """
        :param client: What reads the listing.
        :param repository: The repository.
        :param branch: The branch the runs ran on.
        :return: The listing.
        """
        data = client.get(cls.path(repository, branch))
        return cls(
            [ListedRun.from_json(run) for run in data[WorkflowRunKey.WORKFLOW_RUNS]]
        )

    def succeeded(self, workflow: WorkflowLocation) -> bool:
        """
        :param workflow: The workflow.
        :return: Whether its latest run succeeded.
        """
        latest = next(
            (run for run in self.runs if run.workflow == workflow.as_posix()), None
        )
        return latest is not None and latest.outcome is CheckOutcome.SUCCESS


# %% what is left to the user


class UserStep(StrEnum):
    """
    The steps of publishing that only the user can take.
    """

    CREATE_SITE_REPOSITORY = "create the site repository"
    TURN_ON_PAGES = "turn on GitHub Pages for the site repository"
    STORE_TOKEN = "store the token that starts the build"


@dataclass(frozen=True)
class PendingStep:
    """
    One step left to the user, with the line that takes it.
    """

    step: UserStep
    """
    The step.
    """

    line: str
    """
    The one copyable line that takes it.
    """

    def render(self) -> str:
        """:return: The step as it is printed."""
        return f"- {self.step}:\n    {self.line}"


@dataclass(frozen=True)
class UserSteps:
    """
    The copyable line for each step left to the user.
    """

    notes_repository: Repository
    """
    The repository whose notes branch starts the build.
    """

    site: Repository
    """
    The site repository.
    """

    registered: Sequence[str]
    """
    Every ``owner/name`` the site publishes, which the token has to read.
    """

    @classproperty
    def token_page(cls) -> str:
        """
        Where a fine-grained token is created.
        """
        return f"{GitHubAddress.WEB}/settings/personal-access-tokens/new"

    def pending(self, step: UserStep) -> PendingStep:
        """
        :param step: The step.
        :return: The step with its line.
        """
        lines = {
            UserStep.CREATE_SITE_REPOSITORY: (
                f"gh repo create {self.site.full_name} --public"
            ),
            UserStep.TURN_ON_PAGES: (
                f"gh api -X POST {self.site.api_path}/pages -f build_type=workflow"
            ),
            UserStep.STORE_TOKEN: (
                f"create a fine-grained token at {self.token_page} with Actions: write "
                f"on {self.site.full_name} and Contents: read on "
                f"{', '.join(self.registered)}, then: gh secret set "
                f"{PlanSiteSecret.TOKEN} --repo {self.notes_repository.full_name}"
            ),
        }
        return PendingStep(step, lines[step])


# %% publishing


@dataclass
class PublicationReport:
    """
    What one run of :meth:`PlanSitePublication.publish` changed and left to the user.
    """

    site_url: str
    """
    The address the site is served from.
    """

    written: list[str] = field(default_factory=list)
    """
    What was written, one line each.
    """

    pending: list[PendingStep] = field(default_factory=list)
    """
    The steps left to the user, in the order to take them.
    """

    @property
    def complete(self) -> bool:
        """:return: Whether nothing is left to the user."""
        return not self.pending

    def render(self) -> str:
        """:return: The report as it is printed."""
        lines = [f"Plan site: {self.site_url}"]
        lines.extend(f"- {line}" for line in self.written or ["nothing to write"])
        if self.pending:
            lines.append("Left to you - run this command again once they are done:")
            lines.extend(step.render() for step in self.pending)
        return "\n".join(lines)


@dataclass(frozen=True)
class PlanSitePublication:
    """
    Publishing one repository's plans on the user's plan site.
    """

    git: GitCommandRunner
    """
    The clone to work in.
    """

    notes_remote: str
    """
    The remote the notes branch lives on, as a remote name or a URL.
    """

    notes_repository: Repository
    """
    The repository :attr:`notes_remote` points at.
    """

    notes_branch: str
    """
    The notes branch.
    """

    site: SiteRepository
    """
    The site repository.
    """

    branch_or_tag: str
    """
    The basstler branch or release tag the site's build runs.
    """

    runs: RestClient
    """
    What lists a repository's workflow runs.
    """

    remote_root: str = GitHubAddress.WEB
    """
    Where repositories other than the notes repository are fetched from and pushed to,
    as :meth:`Repository.clone_url_under` takes it.
    """

    initial_branch: str = "main"
    """
    The branch the site workflow goes on when the site repository has none yet.
    """

    def notes_branch_of(self, repository: Repository) -> RemoteBranch:
        """
        :param repository: A repository the site publishes.
        :return: Its notes branch.
        """
        remote = (
            self.notes_remote
            if repository == self.notes_repository
            else repository.clone_url_under(self.remote_root)
        )
        return RemoteBranch(self.git, remote, self.notes_branch)

    def site_branch(self) -> RemoteBranch | None:
        """
        :return: The site repository's default branch, or ``None`` when the site
            repository cannot be reached.
        """
        remote = self.site.repository.clone_url_under(self.remote_root)
        listed = self.git.attempt("ls-remote", "--symref", remote, "HEAD")
        if not listed.succeeded:
            return None
        match = re.search(
            r"^ref: refs/heads/(?P<branch>\S+)\s+HEAD$", listed.output, re.MULTILINE
        )
        return RemoteBranch(
            self.git, remote, match["branch"] if match else self.initial_branch
        )

    def publish(self) -> PublicationReport:
        """
        Write every file publishing needs, then re-check the steps left to the user.

        :return: What was written and what is left.
        """
        report = PublicationReport(self.site.site_url)
        site_branch = self.site_branch()
        user_steps = UserSteps(self.notes_repository, self.site.repository, [])
        if site_branch is None:
            report.pending.append(user_steps.pending(UserStep.CREATE_SITE_REPOSITORY))
            return report
        registry = self.write_site_workflow(site_branch, report)
        hub = self.register(registry, report)
        self.write_dispatch_workflow(site_branch.name, report)
        user_steps = UserSteps(
            self.notes_repository, self.site.repository, hub.repositories
        )
        site_runs = RunListing.read(self.runs, self.site.repository, site_branch.name)
        if not site_runs.succeeded(WorkflowLocation.PLAN_SITE):
            report.pending.append(user_steps.pending(UserStep.TURN_ON_PAGES))
        notes_runs = RunListing.read(
            self.runs, self.notes_repository, self.notes_branch
        )
        if not notes_runs.succeeded(WorkflowLocation.PLAN_SITE_DISPATCH):
            report.pending.append(user_steps.pending(UserStep.STORE_TOKEN))
        return report

    def write_site_workflow(
        self, site_branch: RemoteBranch, report: PublicationReport
    ) -> Repository:
        """
        Write the site workflow, keeping the registry an earlier one names.

        :param site_branch: The site repository's default branch.
        :param report: Where to record the write.
        :return: The registry the workflow names.
        """
        path = WorkflowLocation.PLAN_SITE.as_posix()
        existing = site_branch.read_latest(path)
        registry = (
            SiteWorkflow.registry_in(existing) if existing else None
        ) or self.notes_repository
        workflow = SiteWorkflow(self.branch_or_tag, registry).text
        if existing != workflow:
            site_branch.write(
                {path: workflow},
                f"Build the plan site with basstler {self.branch_or_tag}",
            )
            report.written.append(f"{path} on {site_branch.description}")
        return registry

    def register(self, registry: Repository, report: PublicationReport) -> PlanHub:
        """
        List the notes repository in the registry's hub file, and give the notes branch
        the same copy.

        :param registry: The repository whose notes hold the complete hub file.
        :param report: Where to record the writes.
        :return: The hub file as written.
        """
        path = ProjectLocation.PLAN_HUB.as_posix()
        hub = PlanHub.from_text(self.notes_branch_of(registry).read_latest(path))
        if hub is None:
            hub = PlanHub(registry=registry.full_name)
        hub.register(self.notes_repository.full_name)
        hub.site_url = self.site.site_url
        text = hub.to_text().rstrip("\n")
        for repository in dict.fromkeys([registry, self.notes_repository]):
            branch = self.notes_branch_of(repository)
            if branch.read_latest(path) == text:
                continue
            branch.write(
                {path: text},
                f"List {self.notes_repository.full_name} on the plan site",
            )
            report.written.append(f"{path} on {branch.description}")
        return hub

    def write_dispatch_workflow(
        self, site_branch: str, report: PublicationReport
    ) -> None:
        """
        Write the notes branch's dispatch workflow.

        :param site_branch: The site repository's branch its workflow runs on.
        :param report: Where to record the write.
        """
        path = WorkflowLocation.PLAN_SITE_DISPATCH.as_posix()
        workflow = DispatchWorkflow(
            self.notes_repository, self.notes_branch, self.site.repository, site_branch
        ).text
        notes = self.notes_branch_of(self.notes_repository)
        if notes.read_latest(path) == workflow:
            return
        notes.write(
            {path: workflow},
            f"Start the plan site build in {self.site.repository.full_name} on every push",
        )
        report.written.append(f"{path} on {notes.description}")


# %% command line


class PublicationOption(StrEnum):
    """
    Every option the command takes, named once so no caller spells one out.
    """

    BRANCH_OR_TAG = "--branch-or-tag"
    """
    The basstler branch or release tag the site's build runs.
    """

    SITE_REPOSITORY = "--site-repository"
    """
    The ``owner/name`` repository that builds and serves the site.
    """


def main(argv: list[str] | None = None) -> int:
    """
    Publish this clone's notes repository on the plan site. See the module docstring.

    :param argv: The arguments to parse, defaulting to the process's own.
    :return: 0 when nothing is left to the user, 1 otherwise.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(PublicationOption.BRANCH_OR_TAG, required=True)
    parser.add_argument(
        PublicationOption.SITE_REPOSITORY,
        type=lambda text: SiteRepository(Repository.parse(text)),
    )
    arguments = parser.parse_args(argv)
    project_root = Path(
        os.environ.get(ClaudeCodeVariable.PROJECT_DIRECTORY, Path.cwd())
    )
    notes_remote = PersonalNotesSetting.REMOTE.resolve(project_root, os.environ)
    notes_repository = resolve_repository(project_root, notes_remote)
    if notes_repository is None:
        raise NotesRepositoryUnresolvedError(notes_remote)
    site = arguments.site_repository or SiteRepository.default_for(notes_repository)
    report = PlanSitePublication(
        GitCommandRunner(project_root),
        notes_remote,
        notes_repository,
        PersonalNotesSetting.BRANCH.resolve(project_root, os.environ),
        site,
        arguments.branch_or_tag,
        GitHubCommandLineClient(),
    ).publish()
    logger.info(report.render())
    return 0 if report.complete else 1


if __name__ == "__main__":
    sys.exit(main())
