"""
Publish a repository's plans on the user's plan site, and start the site's build on every
push to its notes branch and every merged pull request.

Usage:
    "${BASSTLER_PYTHON}" -m basstler.plan_site.publication \\
        [--site-repository <owner/name>] [--branch-or-tag <branch or tag>]
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter

from basstler.class_property import classproperty
from basstler.exit_codes import CommandFailure
from basstler.github.repository_details import RepositoryDetails
from basstler.locations import ClaudeCodeVariable, ProjectLocation, WorkflowLocation
from basstler.maintenance.git_commands import GitCommandRunner
from basstler.maintenance.remote_branch import RemoteBranch
from basstler.plan_site.run_listing import RunListing
from basstler.plan_site.user_steps import (
    MergeWorkflowProposal,
    PendingStep,
    UserStep,
    UserSteps,
)
from basstler.plan_site.exceptions import NotesRepositoryUnresolvedError
from basstler.plan_site.hub import PlanHub
from basstler.plan_site.site_repository import SiteRepository
from basstler.plan_site.workflows import (
    DispatchWorkflow,
    MergeWorkflow,
    PlanSiteWorkflow,
    SiteWorkflow,
)
from basstler.repository import GitHubAddress, Repository
from basstler.setup.steps import PersonalNotesSetting, resolve_repository
from basstler.standard_streams import StandardStreamHandler
from basstler.github.client import (
    GitHubClient,
    GitHubRestClient,
)
from basstler.upstream_reviews.vocabulary import BasstlerSource

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% the notes repository on GitHub


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

    skipped: list[str] = field(default_factory=list)
    """
    What was left out on purpose, one line each, with why.
    """

    @property
    def complete(self) -> bool:
        """:return: Whether nothing is left to the user."""
        return not self.pending

    def render(self) -> str:
        """:return: The report as it is printed."""
        lines = [f"Plan site: {self.site_url}"]
        lines.extend(f"- {line}" for line in self.written or ["nothing to write"])
        lines.extend(f"- skipped: {line}" for line in self.skipped)
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

    github: GitHubClient
    """
    What reads repositories and their workflow runs from GitHub, and opens the pull
    request proposing the merge workflow.
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

    merge_workflow_branch: str = "basstler/plan-site-merge"
    """
    The branch the merge workflow waits on until its pull request merges.
    """

    @classproperty
    def fork_skip_reason(cls) -> str:
        """
        Why a fork gets no merge workflow.
        """
        return (
            f"{WorkflowLocation.PLAN_SITE_MERGE}, because the repository is a fork and "
            "its default branch has to stay as its upstream's; merges show at the next "
            "push to the notes branch"
        )

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
        return RemoteBranch(self.dispatch_workflow.notes_branch, self.git, remote)

    def default_branch_of(self, remote: str) -> RemoteBranch | None:
        """
        :param remote: A remote, as a remote name or a URL.
        :return: Its default branch, :attr:`initial_branch` when it has none yet, or
            ``None`` when it cannot be reached.
        """
        listed = self.git.attempt("ls-remote", "--symref", remote, "HEAD")
        if not listed.succeeded:
            return None
        match = re.search(
            r"^ref: refs/heads/(?P<branch>\S+)\s+HEAD$", listed.output, re.MULTILINE
        )
        return RemoteBranch(
            match["branch"] if match else self.initial_branch, self.git, remote
        )

    def publish(self) -> PublicationReport:
        """
        Write every file publishing needs, then re-check the steps left to the user.

        :return: What was written and what is left.
        """
        notes_repository = self.dispatch_workflow.notes_repository
        site = self.dispatch_workflow.site
        report = PublicationReport(site.site_url)
        site_branch = self.default_branch_of(
            site.repository.clone_url_under(self.remote_root)
        )
        if site_branch is None:
            user_steps = UserSteps(notes_repository, site, [])
            report.pending.append(user_steps.pending(UserStep.CREATE_SITE_REPOSITORY))
            return report
        site_runs = RunListing.read(self.github, site.repository, site_branch.name)
        notes_runs = RunListing.read(
            self.github, notes_repository, self.dispatch_workflow.notes_branch
        )
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
        proposal = self.write_merge_workflow(report)
        user_steps = UserSteps(notes_repository, site, hub.repositories)
        if not site_runs.succeeded(SiteWorkflow.location):
            report.pending.append(
                user_steps.pending(
                    UserStep.TURN_ON_PAGES, site_runs.latest(SiteWorkflow.location)
                )
            )
        if not notes_runs.succeeded(DispatchWorkflow.location):
            latest_dispatch = notes_runs.latest(DispatchWorkflow.location)
            report.pending.extend(
                user_steps.pending(step, latest_dispatch)
                for step in (UserStep.CREATE_TOKEN, UserStep.STORE_TOKEN)
            )
        if proposal is not None:
            report.pending.append(proposal.pending(self.github))
        return report

    def run(self) -> int:
        """
        Publish and print what was written and what is left.

        :return: 0 when nothing is left to the user, 1 otherwise, and a failure's own
            exit status when GitHub or the credential stopped the publication.
        """
        try:
            report = self.publish()
        except CommandFailure as error:
            logger.error(f"{error}")
            return error.exit_code
        logger.info(report.render())
        return 0 if report.complete else 1

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
        :raises GitCommandFailed: If the branch refuses the workflow.
        """
        if branch.read_latest(workflow.location) == workflow.text:
            return
        branch.write({workflow.location.as_posix(): workflow.text}, message)
        report.written.append(f"{workflow.location} on {branch.description}")

    def write_merge_workflow(
        self, report: PublicationReport
    ) -> MergeWorkflowProposal | None:
        """
        Write the merge workflow onto :attr:`merge_workflow_branch` for a pull request
        into the notes repository's default branch, so it reaches that branch through
        the repository's own checks.

        :param report: Where to record the writes.
        :return: The workflow left for the user to merge, or ``None`` when the default
            branch holds it or, for a fork, is left without it.
        """
        notes_repository = self.dispatch_workflow.notes_repository
        if RepositoryDetails.from_json(
            self.github.get(notes_repository.api_path)
        ).is_fork:
            report.skipped.append(self.fork_skip_reason)
            return None
        workflow = MergeWorkflow(self.dispatch_workflow)
        message = (
            "Start the plan site build in "
            f"{self.dispatch_workflow.site.repository.full_name} on every merge"
        )
        default_branch = self.default_branch_of(self.notes_remote)
        if default_branch.read_latest(workflow.location) == workflow.text:
            return None
        head = RemoteBranch(self.merge_workflow_branch, self.git, self.notes_remote)
        self.write(head, workflow, message, report)
        return MergeWorkflowProposal(notes_repository, default_branch.name, head.name)

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
    The ``owner/name`` repository that builds and serves the site, the one the notes
    branch records when not given.
    """


app = App(help=__doc__)
"""
The command.
"""


@app.default
def publish(
    *,
    branch_or_tag: Annotated[
        str, Parameter(name=PublicationOption.BRANCH_OR_TAG)
    ] = BasstlerSource.LATEST_RELEASE.value,
    site_repository: Annotated[
        str | None, Parameter(name=PublicationOption.SITE_REPOSITORY)
    ] = None,
) -> int:
    """
    Publish this clone's notes repository on the plan site. See the module docstring.

    :param branch_or_tag: The basstler branch or release tag the site's build runs.
    :param site_repository: The ``owner/name`` repository that builds and serves the
        site, the one the notes branch records when not given.
    :return: The status :meth:`PlanSitePublication.run` ends with.
    :raises NotesRepositoryUnresolvedError: If the notes remote is not on GitHub.
    """
    project_root = Path(
        os.environ.get(ClaudeCodeVariable.PROJECT_DIRECTORY, Path.cwd())
    )
    notes_remote = PersonalNotesSetting.REMOTE.resolve(project_root, os.environ)
    notes_repository = resolve_repository(project_root, notes_remote)
    if notes_repository is None:
        raise NotesRepositoryUnresolvedError(notes_remote)
    git = GitCommandRunner(project_root)
    notes_branch = PersonalNotesSetting.BRANCH.resolve(project_root, os.environ)
    site = (
        SiteRepository.recorded_on(RemoteBranch(notes_branch, git, notes_remote))
        if site_repository is None
        else SiteRepository(Repository.parse(site_repository))
    ) or SiteRepository.default_for(notes_repository)
    return PlanSitePublication(
        git,
        notes_remote,
        DispatchWorkflow(notes_repository, notes_branch, site),
        SiteWorkflow(branch_or_tag, notes_repository),
        GitHubRestClient(),
    ).run()


if __name__ == "__main__":
    app()
