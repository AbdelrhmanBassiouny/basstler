"""
Publish a repository's plans on the user's own plan site, and start the site's build on
every push to the repository's notes branch.

Writes the site repository's workflow, registers the repository in the hub file, and
commits the notes branch's dispatch workflow. Reports each step only the user can take -
creating the site repository, turning Pages on, storing the token - as one copyable line.
Run again, it re-checks them: a step counts as done once a run that needs it succeeded.

Usage:
    "${BASSTLER_PYTHON}" -m basstler.plan_site.publication \\
        [--site-repository <owner/name>] [--branch-or-tag <branch or tag>]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from basstler.class_property import classproperty
from basstler.locations import ClaudeCodeVariable, ProjectLocation, WorkflowLocation
from basstler.maintenance.git_commands import GitCommandRunner
from basstler.maintenance.remote_branch import RemoteBranch
from basstler.plan_site.exceptions import NotesRepositoryUnresolvedError
from basstler.plan_site.hub import PlanHub
from basstler.plan_site.site_repository import SiteRepository
from basstler.plan_site.workflows import (
    DispatchWorkflow,
    PlanSiteSecret,
    PlanSiteWorkflow,
    SiteWorkflow,
)
from basstler.repository import GitHubAddress, Repository
from basstler.setup.steps import PersonalNotesSetting, resolve_repository
from basstler.standard_streams import StandardStreamHandler
from basstler.upstream_reviews.clients import GitHubCommandLineClient, RestClient
from basstler.upstream_reviews.vocabulary import BasstlerSource, CheckOutcome, JSONModel

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% the runs that confirm a step


class WorkflowRunKey(StrEnum):
    """
    Every field read out of a repository's run listing.
    """

    WORKFLOW_RUNS = "workflow_runs"
    """
    The listed runs, newest first.
    """

    PATH = "path"
    """
    The path of the workflow file a run ran, relative to its repository's root.
    """

    CONCLUSION = "conclusion"
    """
    How a run ended, ``null`` while it runs.
    """


class RunListingParameter(StrEnum):
    """
    The query parameters a run listing is narrowed by.
    """

    BRANCH = "branch"
    """
    The branch the runs ran on.
    """

    RUNS_PER_PAGE = "per_page"
    """
    How many runs the listing holds.
    """


@dataclass(frozen=True)
class ListedRun(JSONModel):
    """
    One run in a repository's run listing.
    """

    workflow: Path
    """
    The workflow file it ran, relative to its repository's root.
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
            Path(data[WorkflowRunKey.PATH]),
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
    def path(repository: Repository, branch: str, runs_per_page: int = 20) -> str:
        """
        :param repository: The repository.
        :param branch: The branch the runs ran on.
        :param runs_per_page: How many of the latest runs to list.
        :return: The REST path listing them.
        """
        query = urlencode(
            {
                RunListingParameter.BRANCH: branch,
                RunListingParameter.RUNS_PER_PAGE: runs_per_page,
            }
        )
        return f"{repository.api_path}/actions/runs?{query}"

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
        latest = next((run for run in self.runs if run.workflow == workflow), None)
        return latest is not None and latest.outcome is CheckOutcome.SUCCESS


# %% what is left to the user


class UserStep(StrEnum):
    """
    The steps of publishing that only the user can take.
    """

    CREATE_SITE_REPOSITORY = "create the site repository"
    """
    The site repository does not exist, or cannot be reached.
    """

    TURN_ON_PAGES = "turn on GitHub Pages for the site repository"
    """
    No build in the site repository has succeeded yet.
    """

    STORE_TOKEN = "store the token that starts the build"
    """
    No dispatch from the notes branch has succeeded yet.
    """


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

    site: SiteRepository
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
                f"gh repo create {self.site.repository.full_name} --public"
            ),
            UserStep.TURN_ON_PAGES: (
                f"gh api -X POST {self.site.repository.api_path}/pages "
                "-f build_type=workflow"
            ),
            UserStep.STORE_TOKEN: (
                f"create a fine-grained token at {self.token_page} with Actions: write "
                f"on {self.site.repository.full_name} and Contents: read on "
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
    The remote the notes branch lives on, as a remote name or a URL, pointing at
    :attr:`DispatchWorkflow.notes_repository`.
    """

    dispatch_workflow: DispatchWorkflow
    """
    The notes branch's workflow, naming the notes repository, its notes branch and the
    site repository.
    """

    site_workflow: SiteWorkflow
    """
    The site repository's workflow, whose registry an existing one's replaces.
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
            if repository == self.dispatch_workflow.notes_repository
            else repository.clone_url_under(self.remote_root)
        )
        return RemoteBranch(self.git, remote, self.dispatch_workflow.notes_branch)

    def site_branch(self) -> RemoteBranch | None:
        """
        :return: The site repository's default branch, or ``None`` when the site
            repository cannot be reached.
        """
        remote = self.dispatch_workflow.site.repository.clone_url_under(
            self.remote_root
        )
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
        notes_repository = self.dispatch_workflow.notes_repository
        site = self.dispatch_workflow.site
        report = PublicationReport(site.site_url)
        site_branch = self.site_branch()
        if site_branch is None:
            user_steps = UserSteps(notes_repository, site, [])
            report.pending.append(user_steps.pending(UserStep.CREATE_SITE_REPOSITORY))
            return report
        existing = site_branch.read_latest(SiteWorkflow.location)
        site_workflow = (
            replace(
                self.site_workflow, registry=SiteWorkflow.from_text(existing).registry
            )
            if existing
            else self.site_workflow
        )
        self.write(
            site_branch,
            site_workflow,
            f"Build the plan site with basstler {site_workflow.branch_or_tag}",
            report,
        )
        hub = self.register(site_workflow.registry, report)
        self.write(
            self.notes_branch_of(notes_repository),
            self.dispatch_workflow,
            f"Start the plan site build in {site.repository.full_name} on every push",
            report,
        )
        user_steps = UserSteps(notes_repository, site, hub.repositories)
        site_runs = RunListing.read(self.runs, site.repository, site_branch.name)
        if not site_runs.succeeded(SiteWorkflow.location):
            report.pending.append(user_steps.pending(UserStep.TURN_ON_PAGES))
        notes_runs = RunListing.read(
            self.runs, notes_repository, self.dispatch_workflow.notes_branch
        )
        if not notes_runs.succeeded(DispatchWorkflow.location):
            report.pending.append(user_steps.pending(UserStep.STORE_TOKEN))
        return report

    @staticmethod
    def write(
        branch: RemoteBranch,
        workflow: PlanSiteWorkflow,
        message: str,
        report: PublicationReport,
    ) -> None:
        """
        Write a workflow onto a branch unless the branch already has it as it is.

        :param branch: The branch to write onto.
        :param workflow: The workflow.
        :param message: The commit message.
        :param report: Where to record the write.
        """
        if branch.read_latest(workflow.location) == workflow.text:
            return
        branch.write({workflow.location.as_posix(): workflow.text}, message)
        report.written.append(f"{workflow.location} on {branch.description}")

    def register(self, registry: Repository, report: PublicationReport) -> PlanHub:
        """
        List the notes repository in the registry's hub file, and give the notes branch
        the same copy.

        :param registry: The repository whose notes hold the complete hub file.
        :param report: Where to record the writes.
        :return: The hub file as written.
        """
        notes_repository = self.dispatch_workflow.notes_repository
        path = ProjectLocation.PLAN_HUB.as_posix()
        hub = PlanHub.from_text(self.notes_branch_of(registry).read_latest(path))
        if hub is None:
            hub = PlanHub(registry=registry.full_name)
        hub.register(notes_repository.full_name)
        hub.site_url = self.dispatch_workflow.site.site_url
        text = hub.to_text().rstrip("\n")
        for repository in dict.fromkeys([registry, notes_repository]):
            branch = self.notes_branch_of(repository)
            if branch.read_latest(path) == text:
                continue
            branch.write(
                {path: text}, f"List {notes_repository.full_name} on the plan site"
            )
            report.written.append(f"{path} on {branch.description}")
        return hub


# %% command line


class PublicationOption(StrEnum):
    """
    Every option the command takes, named once so no caller spells one out.
    """

    BRANCH_OR_TAG = "--branch-or-tag"
    """
    The basstler branch or release tag the site's build runs, the latest release when
    not given.
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
    parser.add_argument(
        PublicationOption.BRANCH_OR_TAG, default=BasstlerSource.LATEST_RELEASE
    )
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
        DispatchWorkflow(
            notes_repository,
            PersonalNotesSetting.BRANCH.resolve(project_root, os.environ),
            site,
        ),
        SiteWorkflow(arguments.branch_or_tag, notes_repository),
        GitHubCommandLineClient(),
    ).publish()
    logger.info(report.render())
    return 0 if report.complete else 1


if __name__ == "__main__":
    sys.exit(main())
