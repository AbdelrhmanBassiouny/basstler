"""
Tests for plan_site/publication.py: publishing a repository's plans on the user's plan
site, against bare repositories standing in for GitHub and recorded run listings.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest
import yaml

from basstler.actions_budget import ActionsBudget
from basstler.environment import GitHubCredentialVariable
from basstler.github.client import (
    GitHubReader,
    GitHubResponse,
    GitHubWriter,
    HttpMethod,
    GitHubWrite,
)
from basstler.github.credential import CredentialProvider, GitHubCommand
from basstler.github.exceptions import (
    GitHubCallFailed,
    GitHubRequestFailed,
    GitHubUnreachableError,
)
from basstler.locations import ProjectLocation, WorkflowLocation
from basstler.maintenance.git_commands import (
    GitCommandFailed,
    GitCommandResult,
    GitCommandRunner,
)
from basstler.maintenance.remote_branch import RemoteBranch
from basstler.plan.model import PlanDocument
from basstler.plan_site import token_storage
from basstler.plan_site.build_start import CodeFence
from basstler.plan_site.exceptions import PublicationPushRefusedError, PushRefusal
from basstler.plan_site.hub import PlanHub
from basstler.plan_site.publication import PlanSitePublication, PublicationOption
from basstler.plan_site.publication import app as publication_app
from basstler.github.run_listing import ListedRun, RunListing
from basstler.plan_site.user_steps import (
    MergeWorkflowProposal,
    PendingStep,
    PrivateRepositoryAccess,
    UserStep,
)
from basstler.plan_site.site_repository import SiteRepository
from basstler.plan_site.workflows import (
    BuildSecret,
    DispatchWorkflow,
    GitHubCommandLineOption,
    MergeWorkflow,
    PlanSiteJob,
    PlanSiteSecret,
    PlanSiteWorkflow,
    SiteWorkflow,
    WorkflowFile,
    WorkflowStep,
)
from basstler.repository import GitHubAddress, Repository
from basstler.setup.steps import PersonalNotesSetting
from basstler.upstream_reviews.rest_models import RestPullRequestSummary
from basstler.github.states import CheckOutcome
from basstler.upstream_reviews.action.branch import BasstlerSource
from basstler.workflows import TriggerEvent, Workflow

from ..constants.paths import DatasetLocation
from ..constants.stack import RemoteName
from ..maintenance.fork import UPSTREAM_BASE, ForkCheckout
from ..upstream_reviews.replay import ReplayingRestClient

BRANCH_OR_TAG = "v9.9.9"
"""
The basstler release the published workflows run.
"""

NETWORK_DOWN = "[Errno 101] Network is unreachable"
"""
What a call reports when the network is down.
"""

NOTES_BRANCH = PersonalNotesSetting.BRANCH.default
"""
The notes branch every repository under test keeps its notes on.
"""

# %% a notes repository, its site repository and other registered repositories


@dataclass
class PullRequestOpeningClient(ReplayingRestClient, GitHubWriter):
    """
    Answers reads from recordings, and every write with :attr:`opened`, or with
    :attr:`failure` when one is set, recording it.
    """

    opened: Any = None
    """
    The pull request every write answers with.
    """

    failure: GitHubCallFailed | None = None
    """
    Why every write fails, ``None`` when none does.
    """

    writes: list[GitHubWrite] = field(default_factory=list)
    """
    Every write sent, oldest first.
    """

    refusals: dict[str, GitHubCallFailed] = field(default_factory=dict)
    """
    Why each path that is refused is refused, by path.
    """

    def attempt_get(self, path: str) -> GitHubResponse:
        """
        Like :meth:`ReplayingRestClient.attempt_get`, but a path in :attr:`refusals` is
        answered with its refusal.
        """
        if path in self.refusals:
            self.calls.append(path)
            return GitHubResponse(None, failure=self.refusals[path])
        return super().attempt_get(path)

    def attempt_send(self, write: GitHubWrite) -> GitHubResponse:
        self.writes.append(write)
        if self.failure is not None:
            return GitHubResponse(None, failure=self.failure)
        return GitHubResponse(self.opened)


def bare_repository(path: Path) -> Path:
    """
    :param path: Where to create it, ending ``<owner>/<name>.git``.
    :return: The new, empty bare repository.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--quiet", "--bare", "--initial-branch=main", str(path)],
        check=True,
        capture_output=True,
    )
    return path


@dataclass(frozen=True)
class Publishing:
    """
    A clone of a notes repository, with the bare repositories it publishes through kept
    under one root standing in for GitHub.
    """

    checkout: ForkCheckout
    """
    The clone, whose ``origin`` is the notes repository.
    """

    root: Path
    """
    The directory holding every bare repository as ``<owner>/<name>.git``.
    """

    @property
    def notes_repository(self) -> Repository:
        """:return: The repository the clone's ``origin`` points at."""
        return Repository.from_remote_url(
            self.git(
                self.checkout.project_root, "remote", "get-url", RemoteName.ORIGIN
            ).stdout.strip()
        )

    @property
    def site(self) -> SiteRepository:
        """:return: The site repository under the notes repository's owner."""
        return SiteRepository.default_for(self.notes_repository)

    def path_of(self, repository: Repository) -> Path:
        """:return: The bare repository standing in for *repository*."""
        return self.root / repository.owner / f"{repository.name}.git"

    def create(self, repository: Repository, branch: str | None = None) -> None:
        """
        Create *repository*, with one commit on *branch* when one is given.
        """
        path = bare_repository(self.path_of(repository))
        if branch is None:
            return
        self.git(path, "symbolic-ref", "HEAD", f"refs/heads/{branch}")
        GitCommandRunner(self.checkout.project_root).run(
            "push", "--quiet", path.as_uri(), f"HEAD:refs/heads/{branch}"
        )

    def publication(
        self, runs: PullRequestOpeningClient, in_cloud_session: bool = False
    ) -> PlanSitePublication:
        """:return: Publishing the notes repository on its site."""
        return PlanSitePublication(
            GitCommandRunner(self.checkout.project_root),
            RemoteName.ORIGIN,
            DispatchWorkflow(self.notes_repository, NOTES_BRANCH, self.site),
            SiteWorkflow(BRANCH_OR_TAG, self.notes_repository),
            runs,
            remote_root=self.root.as_uri(),
            in_cloud_session=in_cloud_session,
        )

    @staticmethod
    def git(directory: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        """:return: The finished git command, run in *directory*."""
        return subprocess.run(
            ["git", *arguments], cwd=directory, capture_output=True, text=True
        )

    def file(self, repository: Repository, branch: str, path: str) -> str | None:
        """:return: The file on *repository*'s *branch*, ``None`` when it has none."""
        shown = self.git(self.path_of(repository), "show", f"{branch}:{path}")
        return shown.stdout.rstrip("\n") if shown.returncode == 0 else None

    def tip_on_notes(self, branch: str) -> str:
        """:return: The tip commit of *branch* on the notes repository."""
        return self.git(
            self.checkout.fork_path, "rev-parse", f"refs/heads/{branch}"
        ).stdout.strip()

    def parents_on_notes(self, branch: str) -> tuple[str, ...]:
        """:return: The parents of *branch*'s tip on the notes repository."""
        return GitCommandRunner(self.checkout.fork_path).parents_of(
            self.tip_on_notes(branch)
        )

    def hub_on(self, repository: Repository) -> PlanHub | None:
        """:return: The hub file on *repository*'s notes branch."""
        return PlanHub.from_yaml(
            self.file(repository, NOTES_BRANCH, ProjectLocation.PLAN_HUB.as_posix())
        )

    def runs(
        self,
        site_listing: DatasetLocation,
        notes_listing: DatasetLocation,
        site_branch: str = PlanSitePublication.initial_branch,
        notes_details: DatasetLocation = DatasetLocation.REPOSITORY_NOT_FORK,
        open_pull_requests: tuple[DatasetLocation, ...] = (),
        notes_default_branch: str = UPSTREAM_BASE,
    ) -> PullRequestOpeningClient:
        """:return: A client answering both run listings, the details of every
        repository under :attr:`root`, the notes repository's open merge workflow pull
        requests from recordings, and opening
        :attr:`DatasetLocation.MERGE_WORKFLOW_PULL_REQUEST`."""
        proposal = self.merge_workflow_proposal_into(notes_default_branch)
        return PullRequestOpeningClient(
            {
                **{
                    Repository(path.parent.name, path.stem).api_path: json.loads(
                        DatasetLocation.REPOSITORY_NOT_FORK.read_text()
                    )
                    for path in self.root.glob("*/*.git")
                },
                RunListing.path(self.site.repository, site_branch): json.loads(
                    site_listing.read_text()
                ),
                RunListing.path(self.notes_repository, NOTES_BRANCH): json.loads(
                    notes_listing.read_text()
                ),
                self.notes_repository.api_path: json.loads(notes_details.read_text()),
                proposal.open_pull_requests_path: [
                    json.loads(listed.read_text()) for listed in open_pull_requests
                ],
            },
            opened=json.loads(DatasetLocation.MERGE_WORKFLOW_PULL_REQUEST.read_text()),
        )

    def merge_workflow_proposal_into(self, base: str) -> MergeWorkflowProposal:
        """
        :param base: The notes repository's default branch.
        :return: The merge workflow as publishing proposes it into *base*.
        """
        return MergeWorkflowProposal(
            self.notes_repository, base, PlanSitePublication.merge_workflow_branch
        )

    @property
    def merge_workflow_proposal(self) -> MergeWorkflowProposal:
        """:return: The merge workflow as publishing proposes it into ``main``."""
        return self.merge_workflow_proposal_into(UPSTREAM_BASE)

    def merge_the_workflow(self) -> None:
        """
        Merge the merge workflow's branch into the notes repository's default branch, as
        merging its pull request does.
        """
        self.git(
            self.checkout.fork_path,
            "branch",
            "--force",
            UPSTREAM_BASE,
            PlanSitePublication.merge_workflow_branch,
        )

    def fork_runs(self) -> PullRequestOpeningClient:
        """:return: A client answering both run listings with no runs, for a notes
        repository that is a fork."""
        return self.runs(
            DatasetLocation.WORKFLOW_RUNS_NONE,
            DatasetLocation.WORKFLOW_RUNS_NONE,
            notes_details=DatasetLocation.REPOSITORY_FORK,
        )

    def runs_none(self) -> PullRequestOpeningClient:
        """:return: A client answering both run listings with no runs."""
        return self.runs(
            DatasetLocation.WORKFLOW_RUNS_NONE, DatasetLocation.WORKFLOW_RUNS_NONE
        )


@pytest.fixture
def publishing(fork_checkout: ForkCheckout, tmp_path: Path) -> Publishing:
    """:return: A notes repository with no site repository yet."""
    return Publishing(fork_checkout, tmp_path)


@pytest.fixture
def published(publishing: Publishing) -> Publishing:
    """:return: A notes repository published once on an empty site repository."""
    publishing.create(publishing.site.repository)
    publishing.publication(publishing.runs_none()).publish()
    return publishing


# %% the site repository


def test_a_missing_site_repository_is_left_to_the_user_and_nothing_is_written(
    publishing,
):
    report = publishing.publication(publishing.runs_none()).publish()

    assert [pending.step for pending in report.pending] == [
        UserStep.CREATE_SITE_REPOSITORY
    ]
    assert report.written == []


def test_a_missing_site_repository_is_reported_with_the_private_notes_read_access(
    publishing,
):
    """
    The read access a private notes repository needs is reported before the user
    creates the site repository, not only once it exists.
    """
    runs = private_runs(publishing, secret_refused(publishing, HTTPStatus.NOT_FOUND))

    report = publishing.publication(runs).publish()

    assert [pending.step for pending in report.pending] == [
        UserStep.CREATE_SITE_REPOSITORY,
        UserStep.GIVE_BUILD_READ_ACCESS,
    ]
    assert report.written == []


def test_creating_the_site_repository_warns_what_the_public_site_shows_of_private_notes(
    publishing,
):
    """
    The site repository is created public, so the warning that the site shows the
    private notes is read before it is created.
    """
    runs = private_runs(publishing, secret_refused(publishing, HTTPStatus.NOT_FOUND))

    report = publishing.publication(runs).publish()

    assert (
        pending_step(report, UserStep.CREATE_SITE_REPOSITORY).warning
        == PrivateRepositoryAccess(
            publishing.site, (publishing.notes_repository,)
        ).pending.warning
    )


def test_an_empty_site_repository_gets_the_workflow_naming_the_notes_repository(
    published,
):
    """
    The site workflow goes on the initial branch of a site repository that has none.
    """
    assert (
        published.file(
            published.site.repository,
            PlanSitePublication.initial_branch,
            SiteWorkflow.location.as_posix(),
        )
        == SiteWorkflow(BRANCH_OR_TAG, published.notes_repository).text
    )


def test_the_workflow_goes_on_the_site_repository_s_default_branch(publishing):
    publishing.create(publishing.site.repository, branch="trunk")
    runs = publishing.runs(
        DatasetLocation.WORKFLOW_RUNS_NONE,
        DatasetLocation.WORKFLOW_RUNS_NONE,
        site_branch="trunk",
    )

    publishing.publication(runs).publish()

    assert (
        publishing.file(
            publishing.site.repository, "trunk", SiteWorkflow.location.as_posix()
        )
        == SiteWorkflow(BRANCH_OR_TAG, publishing.notes_repository).text
    )


def test_the_site_workflow_calls_basstler_s_build_at_its_branch_or_tag():
    """
    The site workflow's build job calls basstler's build at the source it names.
    """
    workflow = SiteWorkflow(BRANCH_OR_TAG, Repository("an-owner", "a-registry"))

    job = WorkflowFile.from_yaml(workflow.text).jobs[PlanSiteJob.BUILD]

    assert job.called_workflow == (
        f"{BasstlerSource.REPOSITORY}/{WorkflowLocation.PLAN_SITE_BUILD.as_posix()}"
        f"@{BRANCH_OR_TAG}"
    )


def test_a_written_site_workflow_reads_back_as_the_same_workflow():
    """
    A site workflow's text parses back into an equal workflow.
    """
    workflow = SiteWorkflow(BRANCH_OR_TAG, Repository("an-owner", "a-registry"))

    assert SiteWorkflow.from_yaml(workflow.text) == workflow


@pytest.mark.parametrize(
    ("repository", "expected"),
    [
        (Repository("An-Owner", "plans"), "https://an-owner.github.io/plans/"),
        (Repository("An-Owner", "an-owner.github.io"), "https://an-owner.github.io/"),
    ],
)
def test_the_site_is_served_from_the_repository_s_pages_address(repository, expected):
    assert SiteRepository(repository).site_url == expected


@pytest.mark.parametrize(
    "repository",
    [Repository("an-owner", "plans"), Repository("an-owner", "an-owner.github.io")],
)
def test_a_site_address_reads_back_as_the_repository_serving_it(repository):
    site = SiteRepository(repository)

    assert SiteRepository.from_site_url(site.site_url) == site


def test_an_address_off_github_pages_names_no_site_repository():
    assert SiteRepository.from_site_url("https://plans.example.com/") is None


def test_a_written_dispatch_workflow_reads_back_its_site_repository():
    """
    A written dispatch workflow names the site repository it was written for.
    """
    workflow = a_dispatch_workflow()

    assert SiteRepository.from_dispatch_workflow(workflow.text) == workflow.site


# %% the site the notes branch records


def notes_branch_of(fork_checkout: ForkCheckout) -> RemoteBranch:
    """
    :param fork_checkout: The fork checkout.
    :return: Its notes branch on ``origin``.
    """
    return RemoteBranch(
        NOTES_BRANCH, GitCommandRunner(fork_checkout.project_root), RemoteName.ORIGIN
    )


def test_a_notes_branch_recording_no_site_names_none(fork_checkout):
    """
    A notes branch with neither a dispatch workflow nor a hub file records no site.
    """
    assert SiteRepository.recorded_on(notes_branch_of(fork_checkout)) is None


def test_the_site_the_dispatch_workflow_starts_is_the_recorded_one(fork_checkout):
    """
    The dispatch workflow's site repository is the one the notes branch records.
    """
    workflow = DispatchWorkflow(
        Repository("an-owner", "a-project"),
        NOTES_BRANCH,
        SiteRepository(Repository("An-Owner", "a-board")),
    )
    notes_branch = notes_branch_of(fork_checkout)
    notes_branch.write(
        {workflow.location.as_posix(): workflow.text}, "Add the dispatch workflow"
    )

    assert SiteRepository.recorded_on(notes_branch) == workflow.site


def test_without_a_dispatch_workflow_the_hub_s_site_is_the_recorded_one(
    fork_checkout,
):
    """
    Without a dispatch workflow, the site the hub file names is the recorded one.
    """
    site = SiteRepository(Repository("an-owner", "a-board"))
    hub = PlanHub(registry="an-owner/a-project", site_url=site.site_url)
    notes_branch = notes_branch_of(fork_checkout)
    notes_branch.write({ProjectLocation.PLAN_HUB.as_posix(): hub.to_text()}, "List")

    assert SiteRepository.recorded_on(notes_branch) == site


# %% the hub file


def test_the_notes_repository_is_listed_in_its_own_hub_with_the_site_address(
    published,
):
    assert published.hub_on(published.notes_repository) == PlanHub(
        registry=published.notes_repository.full_name,
        repositories=[published.notes_repository.full_name],
        site_url=published.site.site_url,
    )


def test_a_second_repository_is_listed_in_the_registry_named_by_the_site_workflow(
    published, tmp_path
):
    second = ForkCheckout.create(tmp_path / "second")
    second_repository = Repository(published.notes_repository.owner, "another")
    published.create(second_repository)
    second.run_git(
        "remote",
        "set-url",
        RemoteName.ORIGIN,
        published.path_of(second_repository).as_uri(),
    )
    second_publishing = Publishing(second, published.root)

    second_publishing.publication(second_publishing.runs_none()).publish()

    expected = PlanHub(
        registry=published.notes_repository.full_name,
        repositories=[
            published.notes_repository.full_name,
            second_repository.full_name,
        ],
        site_url=published.site.site_url,
    )
    assert published.hub_on(published.notes_repository) == expected
    assert published.hub_on(second_repository) == expected


# %% the dispatch workflow


def test_the_notes_branch_gets_the_dispatch_workflow(published):
    """
    The notes branch carries the dispatch workflow written for it.
    """
    assert published.file(
        published.notes_repository,
        NOTES_BRANCH,
        DispatchWorkflow.location.as_posix(),
    ) == (
        DispatchWorkflow(published.notes_repository, NOTES_BRANCH, published.site).text
    )


def test_the_dispatch_workflow_runs_on_every_push_to_the_notes_branch():
    """
    The dispatch workflow is triggered by pushes to the notes branch alone.
    """
    workflow = DispatchWorkflow(
        Repository("an-owner", "a-project"),
        NOTES_BRANCH,
        SiteRepository(Repository("an-owner", "plans")),
    )

    assert WorkflowFile.from_yaml(workflow.text).pushed_branches == [NOTES_BRANCH]


def test_the_dispatch_workflow_runs_only_in_the_notes_repository():
    """
    The dispatch job is limited to the notes repository, so forks never run it.
    """
    notes_repository = Repository("an-owner", "a-project")
    workflow = DispatchWorkflow(
        notes_repository, NOTES_BRANCH, SiteRepository(Repository("an-owner", "plans"))
    )

    job = WorkflowFile.from_yaml(workflow.text).jobs[PlanSiteJob.DISPATCH]

    assert job.condition == f"github.repository == '{notes_repository.full_name}'"


def dispatch_step_of(workflow: DispatchWorkflow) -> WorkflowStep:
    """:return: The one step of *workflow*'s job."""
    (step,) = WorkflowFile.from_yaml(workflow.text).jobs[PlanSiteJob.DISPATCH].steps
    return step


def test_the_dispatch_workflow_starts_the_site_workflow_with_the_token():
    site = SiteRepository(Repository("an-owner", "plans"))
    workflow = DispatchWorkflow(Repository("an-owner", "a-project"), NOTES_BRANCH, site)

    step = dispatch_step_of(workflow)

    assert step.environment == {
        GitHubCredentialVariable.GH_TOKEN: f"${{{{ secrets.{PlanSiteSecret.TOKEN} }}}}"
    }
    assert step.command.splitlines()[-1] == (
        f"gh workflow run {SiteWorkflow.location.name} "
        f"--repo {site.repository.full_name}"
    )


def test_a_dispatch_without_the_stored_token_fails_with_an_error_saying_how_to_store_it():
    """
    A missing secret leaves the token empty, which used to fail inside ``gh`` without
    naming the secret.
    """
    workflow = a_dispatch_workflow()
    step = dispatch_step_of(workflow)

    finished = subprocess.run(
        ["bash", "-c", step.command],
        env={GitHubCredentialVariable.GH_TOKEN: ""},
        capture_output=True,
        text=True,
    )

    assert finished.returncode == 1
    assert finished.stdout.startswith(f"::error title={PlanSiteSecret.TOKEN} ")
    assert workflow.site.token_form_url() in finished.stdout
    assert f"{workflow.notes_repository.url}/settings/secrets/actions/new" in (
        finished.stdout
    )


# %% the merge workflow


def a_dispatch_workflow() -> DispatchWorkflow:
    """:return: A dispatch workflow from a notes repository to its site."""
    return DispatchWorkflow(
        Repository("an-owner", "a-project"),
        NOTES_BRANCH,
        SiteRepository(Repository("an-owner", "plans")),
    )


def test_the_merge_workflow_reaches_the_default_branch_only_through_its_branch(
    published,
):
    """
    The default branch gets the workflow by merging a pull request, so it passes the
    repository's checks like any other change.
    """
    dispatch = DispatchWorkflow(
        published.notes_repository, NOTES_BRANCH, published.site
    )

    assert published.file(
        published.notes_repository,
        PlanSitePublication.merge_workflow_branch,
        MergeWorkflow.location.as_posix(),
    ) == (MergeWorkflow(dispatch).text)
    assert (
        published.file(
            published.notes_repository,
            UPSTREAM_BASE,
            MergeWorkflow.location.as_posix(),
        )
        is None
    )


def test_the_merge_workflow_s_branch_starts_from_the_default_branch_s_tip(published):
    """
    GitHub opens no pull request between branches with no history in common.
    """
    assert published.parents_on_notes(PlanSitePublication.merge_workflow_branch) == (
        published.tip_on_notes(UPSTREAM_BASE),
    )


def test_a_merge_workflow_branch_without_the_default_branch_s_history_is_rebuilt_on_it(
    publishing,
):
    """
    An affected release wrote the branch with no parent, and no pull request could be
    opened from it.
    """
    publishing.create(publishing.site.repository)
    publication = publishing.publication(publishing.runs_none())
    RemoteBranch(
        publication.merge_workflow_branch, publication.git, RemoteName.ORIGIN
    ).write(
        {
            MergeWorkflow.location.as_posix(): MergeWorkflow(
                publication.dispatch_workflow
            ).text
        },
        "Start the plan site build on every merge",
    )

    publication.publish()

    assert publishing.parents_on_notes(publication.merge_workflow_branch) == (
        publishing.tip_on_notes(UPSTREAM_BASE),
    )


def test_the_merge_workflow_follows_the_notes_repository_s_default_branch(
    publishing,
):
    publishing.create(publishing.site.repository)
    notes_path = publishing.checkout.fork_path
    publishing.git(notes_path, "branch", "trunk", UPSTREAM_BASE)
    publishing.git(notes_path, "symbolic-ref", "HEAD", "refs/heads/trunk")
    client = publishing.runs(
        DatasetLocation.WORKFLOW_RUNS_NONE,
        DatasetLocation.WORKFLOW_RUNS_NONE,
        notes_default_branch="trunk",
    )

    publishing.publication(client).publish()

    assert client.writes == [publishing.merge_workflow_proposal_into("trunk").opening]


def test_the_merge_workflow_runs_on_every_pull_request_state_change(tmp_path):
    """
    On the base repository's side, so a pull request from a fork starts the build with
    the token too.
    """
    path = tmp_path / MergeWorkflow.location.name
    path.write_text(MergeWorkflow(a_dispatch_workflow()).text)

    trigger = Workflow.at(path).trigger(TriggerEvent.PULL_REQUEST_TARGET)

    assert trigger.activity_types == set(MergeWorkflow.pull_request_activities)


def test_the_merge_workflow_runs_for_any_pull_request_in_the_notes_repository():
    """
    A pull request closed unmerged changes its state on the site too.
    """
    dispatch = a_dispatch_workflow()

    job = WorkflowFile.from_yaml(MergeWorkflow(dispatch).text).jobs[
        PlanSiteJob.DISPATCH
    ]

    assert job.condition == (
        f"github.repository == '{dispatch.notes_repository.full_name}'"
    )


def test_the_merge_workflow_starts_the_build_as_the_dispatch_workflow_does():
    """
    The merge workflow's job starts the build with the dispatch workflow's steps.
    """
    dispatch = a_dispatch_workflow()

    merge_job = WorkflowFile.from_yaml(MergeWorkflow(dispatch).text).jobs[
        PlanSiteJob.DISPATCH
    ]
    dispatch_job = WorkflowFile.from_yaml(dispatch.text).jobs[PlanSiteJob.DISPATCH]

    assert merge_job.steps == dispatch_job.steps


@pytest.mark.parametrize(
    "workflow",
    [a_dispatch_workflow(), MergeWorkflow(a_dispatch_workflow())],
    ids=["dispatch", "merge"],
)
def test_a_build_starting_workflow_keeps_to_the_actions_budget(
    workflow: PlanSiteWorkflow, tmp_path
):
    path = tmp_path / workflow.location.name
    path.write_text(workflow.text)

    assert ActionsBudget().violations_of(Workflow.at(path)) == ()


# %% a private repository the build reads


@pytest.fixture
def private_publishing(publishing: Publishing) -> Publishing:
    """:return: A notes repository with an empty site repository, for a test to
    decide which repositories are private."""
    publishing.create(publishing.site.repository)
    return publishing


def private_runs(
    publishing: Publishing, secret_refusal: GitHubCallFailed | None = None
) -> PullRequestOpeningClient:
    """
    :param publishing: The private notes repository.
    :param secret_refusal: Why reading the site repository's read token is refused,
        ``None`` when it is stored.
    :return: A client answering as :meth:`Publishing.runs` does for a private notes
        repository.
    """
    client = publishing.runs(
        DatasetLocation.WORKFLOW_RUNS_NONE,
        DatasetLocation.WORKFLOW_RUNS_NONE,
        notes_details=DatasetLocation.REPOSITORY_PRIVATE,
    )
    secret_path = PlanSiteSecret.READ_TOKEN.path_on(publishing.site.repository)
    if secret_refusal is None:
        client.responses[secret_path] = json.loads(
            DatasetLocation.PLAN_SITE_READ_TOKEN_STORED.read_text()
        )
    else:
        client.refusals[secret_path] = secret_refusal
    return client


def secret_refused(publishing: Publishing, status: HTTPStatus) -> GitHubRequestFailed:
    """
    :param publishing: The private notes repository.
    :param status: The status GitHub refuses the site repository's read token with.
    :return: The refusal.
    """
    return GitHubRequestFailed(
        status=status,
        detail="",
        method=HttpMethod.GET,
        path=PlanSiteSecret.READ_TOKEN.path_on(publishing.site.repository),
        credential_origin=CredentialProvider.CALLER,
    )


def test_a_private_notes_repository_without_a_read_token_writes_nothing(
    private_publishing,
):
    """
    Without the token, the build could not read the notes, so nothing is written.
    """
    runs = private_runs(
        private_publishing, secret_refused(private_publishing, HTTPStatus.NOT_FOUND)
    )

    report = private_publishing.publication(runs).publish()

    assert report.written == []
    assert report.pending == [
        PrivateRepositoryAccess(
            private_publishing.site, (private_publishing.notes_repository,)
        ).pending
    ]


def test_a_private_notes_repository_with_a_read_token_is_published(
    private_publishing,
):
    """
    With the token stored, publishing goes ahead and asks nothing about access.
    """
    report = private_publishing.publication(private_runs(private_publishing)).publish()

    assert (
        private_publishing.file(
            private_publishing.site.repository,
            PlanSitePublication.initial_branch,
            SiteWorkflow.location.as_posix(),
        )
        == SiteWorkflow(BRANCH_OR_TAG, private_publishing.notes_repository).text
    )
    assert UserStep.GIVE_BUILD_READ_ACCESS not in [
        pending.step for pending in report.pending
    ]


def test_an_unreadable_read_token_is_published_and_left_to_the_user_to_check(
    private_publishing,
):
    """
    A token that may be stored is not a reason to hold the files back.
    """
    refusal = secret_refused(private_publishing, HTTPStatus.FORBIDDEN)
    runs = private_runs(private_publishing, refusal)

    report = private_publishing.publication(runs).publish()

    assert (
        private_publishing.file(
            private_publishing.site.repository,
            PlanSitePublication.initial_branch,
            SiteWorkflow.location.as_posix(),
        )
        == SiteWorkflow(BRANCH_OR_TAG, private_publishing.notes_repository).text
    )
    assert (
        PrivateRepositoryAccess(
            private_publishing.site, (private_publishing.notes_repository,), refusal
        ).pending
        in report.pending
    )


def test_a_public_notes_repository_never_reads_the_read_token(published):
    """
    Public notes need no token, so publishing never asks for the secret.
    """
    runs = published.runs_none()

    published.publication(runs).publish()

    assert PlanSiteSecret.READ_TOKEN.path_on(published.site.repository) not in (
        runs.calls
    )


WORK_REPOSITORY = Repository("an-organization", "private-work")
"""
A private repository of another owner that a plan's items are on.
"""


def plan_naming(publishing: Publishing, repository: Repository) -> None:
    """
    Save a plan on the notes branch whose item is on *repository*.
    """
    manifest = {
        "id": "a-plan",
        "default_repository": publishing.notes_repository.full_name,
        "items": [{"id": "an-item", "repository": repository.full_name}],
    }
    notes_branch_of(publishing.checkout).write(
        {
            (ProjectLocation.PLANS / "a-plan" / PlanDocument.MANIFEST).as_posix(): (
                yaml.safe_dump(manifest, sort_keys=False).rstrip("\n")
            )
        },
        "Save a plan",
    )


def test_a_private_repository_a_plan_names_without_a_read_token_writes_nothing(
    private_publishing,
):
    """
    The notes are public, but the build could not read the items' pull requests.
    """
    plan_naming(private_publishing, WORK_REPOSITORY)
    runs = private_publishing.runs_none()
    runs.responses[WORK_REPOSITORY.api_path] = json.loads(
        DatasetLocation.REPOSITORY_PRIVATE.read_text()
    )
    runs.refusals[
        PlanSiteSecret.READ_TOKEN.path_on(private_publishing.site.repository)
    ] = secret_refused(private_publishing, HTTPStatus.NOT_FOUND)

    report = private_publishing.publication(runs).publish()

    assert report.written == []
    assert report.pending == [
        PrivateRepositoryAccess(private_publishing.site, (WORK_REPOSITORY,)).pending
    ]


def test_a_repository_whose_details_are_refused_is_published_and_left_to_check(
    private_publishing,
):
    """
    A repository the credential may not read could be public, so nothing is held back.
    """
    plan_naming(private_publishing, WORK_REPOSITORY)
    runs = private_publishing.runs_none()
    refusal = GitHubRequestFailed(
        status=HTTPStatus.NOT_FOUND,
        detail="",
        method=HttpMethod.GET,
        path=WORK_REPOSITORY.api_path,
        credential_origin=CredentialProvider.CALLER,
    )
    runs.refusals[WORK_REPOSITORY.api_path] = refusal
    runs.refusals[
        PlanSiteSecret.READ_TOKEN.path_on(private_publishing.site.repository)
    ] = secret_refused(private_publishing, HTTPStatus.NOT_FOUND)

    report = private_publishing.publication(runs).publish()

    assert (
        private_publishing.file(
            private_publishing.site.repository,
            PlanSitePublication.initial_branch,
            SiteWorkflow.location.as_posix(),
        )
        == SiteWorkflow(BRANCH_OR_TAG, private_publishing.notes_repository).text
    )
    assert (
        PrivateRepositoryAccess(
            private_publishing.site,
            (),
            unreadable_repositories={WORK_REPOSITORY: refusal},
        ).pending
        in report.pending
    )


def test_private_repositories_of_several_owners_need_a_classic_token():
    """
    A fine-grained token reads the repositories of one owner only.
    """
    site = SiteRepository(Repository("an-owner", "plans"))
    access = PrivateRepositoryAccess(
        site, (Repository("an-owner", "notes"), WORK_REPOSITORY)
    )

    assert access.pending.browser_steps[0] == (
        f"Open {SiteRepository.classic_token_page}."
    )


def test_a_classic_token_is_asked_for_with_a_warning_that_it_can_also_write():
    """
    A classic token has no read-only repository scope, so the step says what it allows.
    """
    site = SiteRepository(Repository("an-owner", "plans"))
    access = PrivateRepositoryAccess(
        site, (Repository("an-owner", "notes"), WORK_REPOSITORY)
    )

    assert PrivateRepositoryAccess.classic_token_warning in access.pending.warning


def test_a_fine_grained_token_is_asked_for_without_the_classic_token_warning():
    """
    Private repositories of one owner get a read-only token, which writes nothing.
    """
    site = SiteRepository(Repository("an-owner", "plans"))
    access = PrivateRepositoryAccess(site, (Repository("an-owner", "notes"),))

    assert PrivateRepositoryAccess.classic_token_warning not in access.pending.warning


def test_the_read_access_step_warns_that_the_public_site_shows_those_repositories():
    """
    The token lets the build put what it reads from the private repositories on a
    public site, so the step names the site and every repository it would expose.
    """
    site = SiteRepository(Repository("an-owner", "plans"))
    notes = Repository("an-owner", "notes")
    access = PrivateRepositoryAccess(site, (notes, WORK_REPOSITORY))

    warning = access.pending.warning

    assert all(
        name in warning
        for name in (site.site_url, notes.full_name, WORK_REPOSITORY.full_name)
    )


def test_the_site_workflow_passes_the_read_token_to_the_build():
    """
    The site repository's secret reaches the build under the name the build accepts.
    """
    workflow = SiteWorkflow(BRANCH_OR_TAG, Repository("an-owner", "a-registry"))

    job = WorkflowFile.from_yaml(workflow.text).jobs[PlanSiteJob.BUILD]

    assert job.secrets == {
        BuildSecret.READ_TOKEN: f"${{{{ secrets.{PlanSiteSecret.READ_TOKEN} }}}}"
    }


# %% a fork


@pytest.fixture
def published_fork(publishing: Publishing) -> Publishing:
    """:return: A notes repository that is a fork, published once."""
    publishing.create(publishing.site.repository)
    publishing.publication(publishing.fork_runs()).publish()
    return publishing


def test_a_fork_s_default_branch_is_left_as_its_upstream_has_it(published_fork):
    assert (
        published_fork.file(
            published_fork.notes_repository,
            UPSTREAM_BASE,
            MergeWorkflow.location.as_posix(),
        )
        is None
    )


def test_a_fork_still_gets_the_dispatch_workflow(published_fork):
    assert published_fork.file(
        published_fork.notes_repository,
        NOTES_BRANCH,
        DispatchWorkflow.location.as_posix(),
    ) == (
        DispatchWorkflow(
            published_fork.notes_repository, NOTES_BRANCH, published_fork.site
        ).text
    )


def test_a_fork_s_skipped_merge_workflow_is_reported(published_fork):
    report = published_fork.publication(published_fork.fork_runs()).publish()

    assert report.skipped == [PlanSitePublication.fork_skip_reason]


# %% a protected default branch


@pytest.fixture
def protected(publishing: Publishing) -> Publishing:
    """:return: A notes repository whose ``main`` refuses every push, published once."""
    hook = publishing.checkout.fork_path / "hooks" / "pre-receive"
    shutil.copy(DatasetLocation.PROTECTED_MAIN_HOOK, hook)
    publishing.create(publishing.site.repository)
    publishing.publication(publishing.runs_none()).publish()
    return publishing


def test_a_refused_default_branch_gets_the_merge_workflow_on_a_branch_of_its_own(
    protected,
):
    publication = protected.publication(protected.runs_none())
    dispatch = publication.dispatch_workflow

    assert protected.file(
        protected.notes_repository,
        publication.merge_workflow_branch,
        MergeWorkflow.location.as_posix(),
    ) == (MergeWorkflow(dispatch).text)
    assert (
        protected.file(
            protected.notes_repository,
            UPSTREAM_BASE,
            MergeWorkflow.location.as_posix(),
        )
        is None
    )


def test_a_refused_default_branch_leaves_merging_the_workflow_to_the_user(protected):
    report = protected.publication(protected.runs_none()).publish()

    assert [pending.step for pending in report.pending] == [
        UserStep.TURN_ON_PAGES,
        UserStep.CREATE_TOKEN,
        UserStep.STORE_TOKEN,
        UserStep.ADD_MERGE_WORKFLOW,
    ]


def test_a_refused_default_branch_opens_a_pull_request_from_the_workflow_s_branch(
    protected,
):
    client = protected.runs_none()

    protected.publication(client).publish()

    assert client.writes == [protected.merge_workflow_proposal.opening]


def test_an_open_pull_request_for_the_workflow_is_not_opened_again(protected):
    client = protected.runs(
        DatasetLocation.WORKFLOW_RUNS_NONE,
        DatasetLocation.WORKFLOW_RUNS_NONE,
        open_pull_requests=(DatasetLocation.MERGE_WORKFLOW_PULL_REQUEST,),
    )

    protected.publication(client).publish()

    assert client.writes == []


def test_merging_the_workflow_merges_its_pull_request(protected):
    report = protected.publication(protected.runs_none()).publish()
    pull_request = RestPullRequestSummary.from_json(
        json.loads(DatasetLocation.MERGE_WORKFLOW_PULL_REQUEST.read_text())
    )

    assert pending_step(report, UserStep.ADD_MERGE_WORKFLOW) == (
        MergeWorkflowProposal.merging(pull_request)
    )


def pull_request_failures(
    notes: Repository,
) -> list[GitHubCallFailed]:
    """:return: GitHub refusing to open the pull request, and the request getting no
    answer."""
    path = notes.pull_requests_path
    return [
        GitHubRequestFailed(
            status=HTTPStatus.FORBIDDEN,
            detail=DatasetLocation.PULL_REQUEST_REFUSED.read_text(),
            method=HttpMethod.POST,
            path=path,
            credential_origin=CredentialProvider.CALLER,
        ),
        GitHubUnreachableError(HttpMethod.POST, path, NETWORK_DOWN),
    ]


@pytest.fixture(params=[0, 1], ids=["refused", "unreachable"])
def failed_opening(request, protected) -> PullRequestOpeningClient:
    """:return: A client failing to open the merge workflow's pull request."""
    client = protected.runs_none()
    client.failure = pull_request_failures(protected.notes_repository)[request.param]
    return client


def test_an_unopened_pull_request_leaves_opening_it_to_the_user_with_the_reason(
    protected, failed_opening
):
    proposal = protected.merge_workflow_proposal
    notes = protected.notes_repository

    pending = pending_step(
        protected.publication(failed_opening).publish(), UserStep.ADD_MERGE_WORKFLOW
    )

    assert pending.failure == str(failed_opening.failure)
    assert pending.line == (
        f"gh pr create --repo {notes.full_name} --base {proposal.base} "
        f"--head {proposal.head} --fill, then merge it"
    )
    assert pending.browser_steps[0] == (
        f"Open {notes.url}/compare/{proposal.base}...{proposal.head}?expand=1."
    )


def test_an_unopened_pull_request_s_reason_is_printed_with_its_step(
    protected, failed_opening
):
    report = protected.publication(failed_opening).publish()

    rendered = report.render()

    assert [
        line
        for line in str(failed_opening.failure).splitlines()
        if line not in rendered
    ] == []


def test_once_the_workflow_is_merged_nothing_about_it_is_left(protected):
    (protected.checkout.fork_path / "hooks" / "pre-receive").unlink()
    protected.merge_the_workflow()

    report = protected.publication(protected.runs_none()).publish()

    assert UserStep.ADD_MERGE_WORKFLOW not in [
        pending.step for pending in report.pending
    ]


# %% re-running


def test_publishing_again_writes_nothing(published):
    report = published.publication(published.runs_none()).publish()

    assert report.written == []


def test_without_successful_runs_pages_and_the_token_are_left_to_the_user(published):
    report = published.publication(published.runs_none()).publish()

    assert [pending.step for pending in report.pending] == [
        UserStep.TURN_ON_PAGES,
        UserStep.CREATE_TOKEN,
        UserStep.STORE_TOKEN,
        UserStep.ADD_MERGE_WORKFLOW,
    ]


def test_once_both_workflows_succeeded_and_the_merge_workflow_merged_nothing_is_left(
    published,
):
    published.merge_the_workflow()
    runs = published.runs(
        DatasetLocation.PLAN_SITE_RUNS_SUCCEEDED,
        DatasetLocation.PLAN_SITE_DISPATCH_RUNS_SUCCEEDED,
    )

    assert published.publication(runs).publish().complete


def test_a_failed_latest_dispatch_leaves_the_token_to_the_user(published):
    published.merge_the_workflow()
    runs = published.runs(
        DatasetLocation.PLAN_SITE_RUNS_SUCCEEDED,
        DatasetLocation.PLAN_SITE_DISPATCH_RUNS_FAILED,
    )

    report = published.publication(runs).publish()

    assert [pending.step for pending in report.pending] == [
        UserStep.CREATE_TOKEN,
        UserStep.STORE_TOKEN,
    ]


@dataclass
class RefusingRestClient(GitHubReader):
    """
    A client for which GitHub refuses every request, as it does for a repository the
    session has no access to.
    """

    def get(self, path: str):
        raise GitHubRequestFailed(
            status=HTTPStatus.FORBIDDEN,
            detail="",
            method=HttpMethod.GET,
            path=path,
            credential_origin=CredentialProvider.CALLER,
        )

    def get_pages(self, path: str):
        raise GitHubRequestFailed(
            status=HTTPStatus.FORBIDDEN,
            detail="",
            method=HttpMethod.GET,
            path=path,
            credential_origin=CredentialProvider.CALLER,
        )


def test_runs_that_cannot_be_read_stop_the_publication_before_anything_is_written(
    publishing,
):
    """
    Unreadable run listings stop publication before any file is written.
    """
    publishing.create(publishing.site.repository)

    with pytest.raises(GitHubRequestFailed):
        publishing.publication(RefusingRestClient()).publish()

    assert (
        publishing.file(
            publishing.notes_repository,
            NOTES_BRANCH,
            DispatchWorkflow.location.as_posix(),
        )
        is None
    )
    assert (
        publishing.file(
            publishing.site.repository,
            PlanSitePublication.initial_branch,
            SiteWorkflow.location.as_posix(),
        )
        is None
    )


def test_a_refused_read_ends_the_command_with_the_error_s_own_exit_status(publishing):
    publishing.create(publishing.site.repository)

    exit_status = publishing.publication(RefusingRestClient()).run()

    assert exit_status == GitHubRequestFailed.exit_code


def test_a_command_with_steps_left_ends_with_the_incomplete_exit_status(published):
    assert published.publication(published.runs_none()).run() == 1


def test_a_command_with_nothing_left_ends_successfully(published):
    published.merge_the_workflow()
    runs = published.runs(
        DatasetLocation.PLAN_SITE_RUNS_SUCCEEDED,
        DatasetLocation.PLAN_SITE_DISPATCH_RUNS_SUCCEEDED,
    )

    assert published.publication(runs).run() == 0


# %% the steps in the browser


def pending_step(report, step: UserStep):
    """:return: The step *step* of *report*."""
    return next(pending for pending in report.pending if pending.step is step)


def test_creating_the_site_repository_points_at_github_s_new_repository_page(
    publishing,
):
    report = publishing.publication(publishing.runs_none()).publish()

    browser_steps = pending_step(report, UserStep.CREATE_SITE_REPOSITORY).browser_steps

    assert f"{GitHubAddress.WEB}/new" in browser_steps[0]
    assert any(publishing.site.repository.name in step for step in browser_steps)


def test_turning_on_pages_points_at_the_site_repository_s_pages_settings(published):
    report = published.publication(published.runs_none()).publish()

    browser_steps = pending_step(report, UserStep.TURN_ON_PAGES).browser_steps

    assert f"{published.site.repository.url}/settings/pages" in browser_steps[0]


def test_creating_the_token_walks_through_scoping_it_to_the_site_repository_only(
    published,
):
    """
    The token only starts the site's build, so it needs no access to a notes repository,
    and a repository joining the site needs no new token.
    """
    report = published.publication(published.runs_none()).publish()

    browser_steps = pending_step(report, UserStep.CREATE_TOKEN).browser_steps

    text = "\n".join(browser_steps)
    assert published.site.token_form_url() in text
    assert published.site.repository.full_name in text
    assert published.notes_repository.full_name not in text


def test_creating_a_token_has_no_command_line_because_github_offers_none(published):
    report = published.publication(published.runs_none()).publish()

    assert pending_step(report, UserStep.CREATE_TOKEN).line is None


def test_storing_the_token_is_the_command_that_stores_and_proves_it_everywhere(
    published,
):
    report = published.publication(published.runs_none()).publish()

    line = pending_step(report, UserStep.STORE_TOKEN).line

    assert line == f"{sys.executable} -m {token_storage.__name__}"


def test_storing_the_token_in_the_browser_opens_each_registered_repository_s_secret_page(
    published,
):
    report = published.publication(published.runs_none()).publish()

    text = "\n".join(pending_step(report, UserStep.STORE_TOKEN).browser_steps)

    assert f"{published.notes_repository.url}/settings/secrets/actions/new" in text
    assert PlanSiteSecret.TOKEN in text


# %% storing the token from a cloud session

TYPED_TOKEN = "github_pat_typed"
"""
The token typed at the store command's hidden prompt.
"""


class RecordingGitHubVariable(StrEnum):
    """
    The environment variables :attr:`DatasetLocation.RECORDING_GH` reads.
    """

    CALLS = "GH_CALLS"
    """
    The file each call is appended to.
    """

    WORKFLOW_RUN_STATUS = "GH_WORKFLOW_RUN_STATUS"
    """
    The status a workflow run exits with.
    """


def run_cloud_store_command(
    published, tmp_path: Path, monkeypatch, workflow_run_status: int = 0
) -> list[str]:
    """
    Run the store step's command of a cloud session's publication with a recording
    ``gh``, typing :data:`TYPED_TOKEN` at its prompt.

    :return: The recorded ``gh`` calls, one ``GH_TOKEN|arguments|standard input`` each.
    """
    report = published.publication(
        published.runs_none(), in_cloud_session=True
    ).publish()
    command = pending_step(report, UserStep.STORE_TOKEN).line
    executables = tmp_path / "bin"
    executables.mkdir()
    (executables / "gh").symlink_to(DatasetLocation.RECORDING_GH)
    calls = tmp_path / "gh-calls"
    monkeypatch.delenv(GitHubCredentialVariable.GH_TOKEN, raising=False)
    monkeypatch.setenv("PATH", f"{executables}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv(RecordingGitHubVariable.CALLS, str(calls))
    monkeypatch.setenv(
        RecordingGitHubVariable.WORKFLOW_RUN_STATUS, str(workflow_run_status)
    )
    subprocess.run(["sh", "-c", command], input=f"{TYPED_TOKEN}\n", text=True)
    return calls.read_text().splitlines()


def test_a_cloud_session_s_store_command_runs_without_this_session_s_python(published):
    """
    A cloud session's user runs the command on their own computer, where this session's
    interpreter does not exist.
    """
    report = published.publication(
        published.runs_none(), in_cloud_session=True
    ).publish()

    assert sys.executable not in pending_step(report, UserStep.STORE_TOKEN).line


def test_a_cloud_session_s_store_command_proves_the_token_by_starting_the_build(
    published, tmp_path, monkeypatch
):
    """
    The typed token starts the site's build first, as the dispatch workflow does.
    """
    calls = run_cloud_store_command(published, tmp_path, monkeypatch)

    assert calls[0] == (
        f"{TYPED_TOKEN}|workflow run {SiteWorkflow.location.name} "
        f"{GitHubCommandLineOption.REPOSITORY} {published.site.repository.full_name}|"
    )


def test_a_cloud_session_s_store_command_stores_the_token_in_every_registered_repository(
    published, tmp_path, monkeypatch
):
    """
    Once the build started, the token is stored in every registered repository with the
    user's own login.
    """
    calls = run_cloud_store_command(published, tmp_path, monkeypatch)

    registered = published.hub_on(published.notes_repository).repositories
    assert calls[1:] == [
        f"|secret set {PlanSiteSecret.TOKEN} {GitHubCommandLineOption.REPOSITORY} "
        f"{repository}|{TYPED_TOKEN}"
        for repository in registered
    ]


def test_a_cloud_session_s_store_command_stores_nothing_when_the_build_is_refused(
    published, tmp_path, monkeypatch
):
    """
    A token GitHub refuses to start the build with is stored nowhere.
    """
    calls = run_cloud_store_command(
        published, tmp_path, monkeypatch, workflow_run_status=1
    )

    assert len(calls) == 1


def test_a_failed_dispatch_run_is_linked_from_the_step_it_leaves_to_the_user(
    published,
):
    """
    The step left to the user carries the failed dispatch run that made it necessary.
    """
    runs = published.runs(
        DatasetLocation.PLAN_SITE_RUNS_SUCCEEDED,
        DatasetLocation.PLAN_SITE_DISPATCH_RUNS_FAILED,
    )

    report = published.publication(runs).publish()

    latest_run = pending_step(report, UserStep.STORE_TOKEN).latest_run
    assert latest_run == ListedRun(
        page_url="https://github.com/an-owner/a-repository/actions/runs/4004",
        identifier=4004,
        commit="4004" * 10,
        outcome=CheckOutcome.FAILURE,
        workflow_file_path=Path(DispatchWorkflow.location),
        created_at=datetime(2026, 10, 2, 10, tzinfo=UTC),
    )


def test_without_a_run_no_run_is_linked(published):
    """
    A step whose workflow has not run links no run.
    """
    report = published.publication(published.runs_none()).publish()

    assert pending_step(report, UserStep.STORE_TOKEN).latest_run is None


def test_a_rendered_step_shows_the_command_and_then_the_browser_steps(published):
    """
    The command is set in a bash block, so it is copied whole, before the browser steps.
    """
    report = published.publication(published.runs_none()).publish()
    pending = pending_step(report, UserStep.TURN_ON_PAGES)

    assert pending.render() == (
        f"- {pending.step}:\n    {CodeFence.BASH}\n    {pending.line}\n"
        f"    {CodeFence.CLOSE}\n  Or in the browser:\n"
        + "\n".join(
            f"    {number}. {step}"
            for number, step in enumerate(pending.browser_steps, start=1)
        )
    )


def test_a_rendered_step_without_a_command_says_so_before_the_browser_steps(published):
    report = published.publication(published.runs_none()).publish()
    pending = pending_step(report, UserStep.CREATE_TOKEN)

    assert pending.render().startswith(
        f"- {pending.step}:\n  GitHub offers no command for this; in the browser:\n"
    )


def test_a_rendered_step_shows_its_warning_right_under_its_heading():
    """
    A warning is read before the command that would act on it.
    """
    pending = PendingStep(
        UserStep.GIVE_BUILD_READ_ACCESS, "true", ("Open a page.",), warning="Careful."
    )

    assert pending.render().splitlines()[1] == f"    Warning: {pending.warning}"


def test_a_rendered_step_links_the_latest_run_that_made_it_necessary(published):
    """
    The rendered step links the page of the run that made it necessary.
    """
    runs = published.runs(
        DatasetLocation.PLAN_SITE_RUNS_SUCCEEDED,
        DatasetLocation.PLAN_SITE_DISPATCH_RUNS_FAILED,
    )
    pending = pending_step(published.publication(runs).publish(), UserStep.STORE_TOKEN)

    assert pending.render().splitlines()[1] == (
        f"  Latest run, {pending.latest_run.outcome}: {pending.latest_run.page_url}"
    )


# %% a refused push

REFUSED_NOTES_REPOSITORY = Repository("an-owner", "notes")
"""
The notes repository of a publication whose push was refused.
"""


@pytest.fixture
def scope_refused(publishing: Publishing) -> Publishing:
    """:return: A notes repository whose site repository refuses every push, as GitHub
    refuses a token without the ``workflow`` scope."""
    publishing.create(publishing.site.repository)
    shutil.copy(
        DatasetLocation.WORKFLOW_SCOPE_REFUSING_HOOK,
        publishing.path_of(publishing.site.repository) / "hooks" / "pre-receive",
    )
    return publishing


def refused_push(error_output: DatasetLocation) -> PublicationPushRefusedError:
    """
    :param error_output: What git printed refusing the push.
    :return: The error a publication raises for that refusal.
    """
    return PublicationPushRefusedError.from_push(
        GitCommandResult(
            arguments=("push",),
            exit_status=1,
            output="",
            error_output=error_output.read_text().strip(),
        ),
        notes_remote=RemoteName.ORIGIN,
        notes_repository=REFUSED_NOTES_REPOSITORY,
    )


def test_a_push_refused_for_the_workflow_scope_is_read_as_that_refusal(
    scope_refused,
):
    """
    The site repository's refusal stops publication with the refusal it reports.
    """
    with pytest.raises(PublicationPushRefusedError) as raised:
        scope_refused.publication(scope_refused.runs_none()).publish()

    assert raised.value.refusal is PushRefusal.MISSING_WORKFLOW_SCOPE


def test_a_push_refused_for_the_workflow_scope_suggests_adding_the_scope(
    scope_refused,
):
    """
    The suggestion names the command that gives ``gh``'s login the scope.
    """
    with pytest.raises(PublicationPushRefusedError) as raised:
        scope_refused.publication(scope_refused.runs_none()).publish()

    assert GitHubCommand.REFRESH_WORKFLOW_SCOPE in raised.value.suggest_correction()


def test_a_refused_push_ends_the_command_with_a_failed_git_command_s_exit_status(
    scope_refused,
):
    """
    Naming the fix keeps the status any failed git command ends with.
    """
    exit_status = scope_refused.publication(scope_refused.runs_none()).run()

    assert exit_status == GitCommandFailed.exit_code


def test_a_push_without_a_credential_is_read_as_that_refusal():
    """
    Git's prompt for a username it cannot ask for means it has no credential.
    """
    refused = refused_push(DatasetLocation.PUSH_REFUSED_WITHOUT_CREDENTIAL)

    assert refused.refusal is PushRefusal.NO_CREDENTIAL


def test_a_push_without_a_credential_suggests_logging_gh_in():
    """
    Git is lent ``gh``'s login, so a missing credential means ``gh`` is logged out.
    """
    refused = refused_push(DatasetLocation.PUSH_REFUSED_WITHOUT_CREDENTIAL)

    assert GitHubCommand.LOG_IN in refused.suggest_correction()


def test_a_push_declined_for_a_reason_git_does_not_name_is_no_known_refusal():
    """
    A refusal is read only from the text that reports it.
    """
    assert refused_push(DatasetLocation.PUSH_DECLINED).refusal is None


def test_a_push_declined_for_a_reason_git_does_not_name_suggests_every_fix():
    """
    Without a known refusal, the user is given every fix to choose from.
    """
    correction = refused_push(DatasetLocation.PUSH_DECLINED).suggest_correction()

    assert [refusal.fix for refusal in PushRefusal if refusal.fix in correction] == [
        refusal.fix for refusal in PushRefusal
    ]


@pytest.mark.parametrize(
    "error_output",
    [DatasetLocation.PUSH_REFUSED_WITHOUT_CREDENTIAL, DatasetLocation.PUSH_DECLINED],
)
def test_a_refused_push_suggests_reaching_github_over_ssh(error_output):
    """
    Every refusal names the notes repository's SSH address, which publication then
    pushes every repository over.
    """
    correction = refused_push(error_output).suggest_correction()

    assert REFUSED_NOTES_REPOSITORY.clone_url_under(GitHubAddress.SSH) in correction


# %% the command line


@pytest.mark.parametrize("option", list(PublicationOption))
def test_the_command_takes_every_option_it_names(option):
    """
    The command accepts every option :class:`PublicationOption` names.
    """
    _, bound, _ = publication_app.parse_args([option, "a-value"])

    assert list(bound.arguments.values()) == ["a-value"]
