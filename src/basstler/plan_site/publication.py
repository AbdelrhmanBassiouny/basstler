"""
Publish a repository's plans on the user's own plan site, and start the site's build on
every push to the repository's notes branch and every pull request merged into it.

Writes the site repository's workflow, registers the repository in the hub file, and
commits the notes branch's dispatch workflow and the default branch's merge workflow -
onto a branch of its own for the user to merge, when the default branch refuses it, and
not at all for a fork, whose default branch stays as its upstream's. Reports each step only the user can take -
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
from basstler.maintenance.remote_branch import FileWrite, RemoteBranch
from basstler.plan_site.exceptions import NotesRepositoryUnresolvedError
from basstler.plan_site.hub import PlanHub
from basstler.plan_site.site_repository import SiteRepository
from basstler.plan_site.workflows import (
    DispatchWorkflow,
    MergeWorkflow,
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


# %% the notes repository on GitHub


class RepositoryKey(StrEnum):
    """
    Every field read out of a repository's REST response.
    """

    FORK = "fork"
    """
    Whether the repository is a fork.
    """


@dataclass(frozen=True)
class RepositoryDetails(JSONModel):
    """
    What publishing reads about a repository from GitHub.
    """

    is_fork: bool
    """
    Whether it is a fork, whose default branch follows its upstream's.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RepositoryDetails:
        """
        :param data: A repository's REST response.
        :return: The parsed details.
        """
        return cls(data[RepositoryKey.FORK])


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

    ADD_MERGE_WORKFLOW = "merge the workflow that starts the build on every merge"
    """
    The notes repository's default branch refused the merge workflow, which waits on a
    branch of its own.
    """


@dataclass(frozen=True)
class PendingStep:
    """
    One step left to the user, with the command line and the browser steps that take it.
    """

    step: UserStep
    """
    The step.
    """

    line: str
    """
    The one copyable line that takes it.
    """

    browser_steps: tuple[str, ...]
    """
    The same step taken on github.com, one click or entry each, in order.
    """

    def render(self) -> str:
        """:return: The step as it is printed."""
        numbered = "\n".join(
            f"    {number}. {text}"
            for number, text in enumerate(self.browser_steps, start=1)
        )
        return f"- {self.step}:\n    {self.line}\n  Or in the browser:\n{numbered}"


@dataclass(frozen=True)
class UserSteps:
    """
    The command line and the browser steps for each step left to the user.
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
        :return: The step with its line and its browser steps.
        """
        site = self.site.repository
        notes = self.notes_repository
        steps = {
            UserStep.CREATE_SITE_REPOSITORY: PendingStep(
                step,
                f"gh repo create {site.full_name} --public",
                (
                    f"Open {GitHubAddress.WEB}/new.",
                    f"Set the owner to {site.owner} and the repository name to "
                    f"{site.name}.",
                    "Choose Public, then click Create repository.",
                ),
            ),
            UserStep.TURN_ON_PAGES: PendingStep(
                step,
                f"gh api -X POST {site.api_path}/pages -f build_type=workflow",
                (
                    f"Open {site.url}/settings/pages.",
                    "Under Build and deployment, set Source to GitHub Actions.",
                ),
            ),
            UserStep.STORE_TOKEN: PendingStep(
                step,
                f"create a fine-grained token at {self.token_page} with Actions: "
                f"write on {site.full_name} and Contents: read on "
                f"{', '.join(self.registered)}, then: gh secret set "
                f"{PlanSiteSecret.TOKEN} --repo {notes.full_name}",
                (
                    f"Open {self.token_page}.",
                    f"Name the token and set Resource owner to {site.owner}.",
                    "Under Repository access, choose Only select repositories and "
                    f"select {site.full_name}, {', '.join(self.registered)}.",
                    "Under Permissions, open Repository permissions and set Actions "
                    "to Read and write and Contents to Read-only.",
                    "Click Generate token and copy the token now; GitHub shows it "
                    "once.",
                    f"Open {notes.url}/settings/secrets/actions/new.",
                    f"Set the name to {PlanSiteSecret.TOKEN}, paste the token as "
                    "the secret, then click Add secret.",
                ),
            ),
        }
        return steps[step]


@dataclass(frozen=True)
class MergeWorkflowProposal:
    """
    The merge workflow waiting on a branch of its own, for the user to merge into a
    default branch that refused it.
    """

    repository: Repository
    """
    The notes repository.
    """

    base: str
    """
    Its default branch, which refused the workflow.
    """

    head: str
    """
    The branch holding the workflow.
    """

    def pending(self) -> PendingStep:
        """:return: The step that merges it, with its line and its browser steps."""
        return PendingStep(
            UserStep.ADD_MERGE_WORKFLOW,
            f"gh pr create --repo {self.repository.full_name} --base {self.base} "
            f"--head {self.head} --fill, then merge it",
            (
                f"Open {self.repository.url}/compare/{self.base}...{self.head}"
                "?expand=1.",
                "Click Create pull request.",
                "Merge the pull request.",
            ),
        )


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

    github: RestClient
    """
    What reads repositories and their workflow runs from GitHub.
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
    The branch the merge workflow waits on when the notes repository's default branch
    refuses it.
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
        site_runs = RunListing.read(self.github, site.repository, site_branch.name)
        if not site_runs.succeeded(SiteWorkflow.location):
            report.pending.append(user_steps.pending(UserStep.TURN_ON_PAGES))
        notes_runs = RunListing.read(
            self.github, notes_repository, self.dispatch_workflow.notes_branch
        )
        if not notes_runs.succeeded(DispatchWorkflow.location):
            report.pending.append(user_steps.pending(UserStep.STORE_TOKEN))
        if proposal is not None:
            report.pending.append(proposal.pending())
        return report

    @staticmethod
    def attempt_write(
        branch: RemoteBranch,
        workflow: PlanSiteWorkflow,
        message: str,
        report: PublicationReport,
    ) -> FileWrite | None:
        """
        Write a workflow onto a branch unless the branch already has it as it is.

        :param branch: The branch to write onto.
        :param workflow: The workflow.
        :param message: The commit message.
        :param report: Where to record a write the branch accepted.
        :return: The write, failed when the branch refused it, or ``None`` when the
            branch already had the workflow.
        """
        if branch.read_latest(workflow.location) == workflow.text:
            return None
        written = branch.attempt_write(
            {workflow.location.as_posix(): workflow.text}, message
        )
        if written.push.succeeded:
            report.written.append(f"{workflow.location} on {branch.description}")
        return written

    def write(
        self,
        branch: RemoteBranch,
        workflow: PlanSiteWorkflow,
        message: str,
        report: PublicationReport,
    ) -> None:
        """
        Like :meth:`attempt_write`, but a refused push is an error.

        :raises GitCommandFailed: If the branch refuses the workflow.
        """
        written = self.attempt_write(branch, workflow, message, report)
        if written is not None:
            written.push.raise_if_failed()

    def write_merge_workflow(
        self, report: PublicationReport
    ) -> MergeWorkflowProposal | None:
        """
        Write the merge workflow onto the notes repository's default branch, or onto
        :attr:`merge_workflow_branch` when the default branch refuses it.

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
        written = self.attempt_write(default_branch, workflow, message, report)
        if written is None or written.push.succeeded:
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
