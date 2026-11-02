"""
Tests for plan_site/publication.py: publishing a repository's plans on the user's plan
site, against bare repositories standing in for GitHub and recorded run listings.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest

from basstler.actions_budget import ActionsBudget
from basstler.environment import GitHubCredentialVariable
from basstler.github.client import (
    GitHubReader,
    GitHubResponse,
    GitHubWriter,
    HttpMethod,
)
from basstler.github.exceptions import (
    GitHubCallFailed,
    GitHubRequestFailed,
    GitHubUnreachableError,
)
from basstler.locations import ProjectLocation, WorkflowLocation
from basstler.maintenance.git_commands import GitCommandRunner
from basstler.plan_site.hub import PlanHub
from basstler.plan_site.publication import PlanSitePublication
from basstler.plan_site.run_listing import ListedRun, RunListing
from basstler.plan_site.user_steps import MergeWorkflowProposal, UserStep, UserSteps
from basstler.plan_site.site_repository import SiteRepository
from basstler.plan_site.workflows import (
    DispatchWorkflow,
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
from basstler.upstream_reviews.vocabulary import BasstlerSource, CheckOutcome
from basstler.workflows import ActivityType, TriggerEvent, Workflow

from ..constants.paths import DatasetLocation
from ..constants.stack import RemoteName
from ..github.recorded_client import SentWrite
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

    writes: list[SentWrite] = field(default_factory=list)
    """
    Every write sent, oldest first.
    """

    def attempt_send(
        self, method: HttpMethod, path: str, payload: Mapping[str, Any]
    ) -> GitHubResponse:
        self.writes.append(SentWrite(method, path, payload))
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

    def publication(self, runs: PullRequestOpeningClient) -> PlanSitePublication:
        """:return: Publishing the notes repository on its site."""
        return PlanSitePublication(
            GitCommandRunner(self.checkout.project_root),
            RemoteName.ORIGIN,
            DispatchWorkflow(self.notes_repository, NOTES_BRANCH, self.site),
            SiteWorkflow(BRANCH_OR_TAG, self.notes_repository),
            runs,
            remote_root=self.root.as_uri(),
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

    def hub_on(self, repository: Repository) -> PlanHub | None:
        """:return: The hub file on *repository*'s notes branch."""
        return PlanHub.from_text(
            self.file(repository, NOTES_BRANCH, ProjectLocation.PLAN_HUB.as_posix())
        )

    def runs(
        self,
        site_listing: DatasetLocation,
        notes_listing: DatasetLocation,
        site_branch: str = "main",
        notes_details: DatasetLocation = DatasetLocation.REPOSITORY_NOT_FORK,
        open_pull_requests: tuple[DatasetLocation, ...] = (),
    ) -> PullRequestOpeningClient:
        """:return: A client answering both run listings, the notes repository's
        details and its open merge workflow pull requests from recordings, and opening
        :attr:`DatasetLocation.MERGE_WORKFLOW_PULL_REQUEST`."""
        return PullRequestOpeningClient(
            {
                RunListing.path(self.site.repository, site_branch): json.loads(
                    site_listing.read_text()
                ),
                RunListing.path(self.notes_repository, NOTES_BRANCH): json.loads(
                    notes_listing.read_text()
                ),
                self.notes_repository.api_path: json.loads(notes_details.read_text()),
                self.merge_workflow_proposal.open_pull_requests_path: [
                    json.loads(listed.read_text()) for listed in open_pull_requests
                ],
            },
            opened=json.loads(DatasetLocation.MERGE_WORKFLOW_PULL_REQUEST.read_text()),
        )

    @property
    def merge_workflow_proposal(self) -> MergeWorkflowProposal:
        """:return: The merge workflow as publishing proposes it when the default
        branch refuses it."""
        return MergeWorkflowProposal(
            self.notes_repository,
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


def test_an_empty_site_repository_gets_the_workflow_naming_the_notes_repository(
    published,
):
    assert (
        published.file(
            published.site.repository, "main", SiteWorkflow.location.as_posix()
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
    workflow = SiteWorkflow(BRANCH_OR_TAG, Repository("an-owner", "a-registry"))

    job = WorkflowFile.from_text(workflow.text).jobs[PlanSiteJob.BUILD]

    assert job.called_workflow == (
        f"{BasstlerSource.REPOSITORY}/{WorkflowLocation.PLAN_SITE_BUILD.as_posix()}"
        f"@{BRANCH_OR_TAG}"
    )


def test_a_written_site_workflow_reads_back_as_the_same_workflow():
    workflow = SiteWorkflow(BRANCH_OR_TAG, Repository("an-owner", "a-registry"))

    assert SiteWorkflow.from_text(workflow.text) == workflow


@pytest.mark.parametrize(
    ("repository", "expected"),
    [
        (Repository("An-Owner", "plans"), "https://an-owner.github.io/plans/"),
        (Repository("An-Owner", "an-owner.github.io"), "https://an-owner.github.io/"),
    ],
)
def test_the_site_is_served_from_the_repository_s_pages_address(repository, expected):
    assert SiteRepository(repository).site_url == expected


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
    assert published.file(
        published.notes_repository,
        NOTES_BRANCH,
        DispatchWorkflow.location.as_posix(),
    ) == (
        DispatchWorkflow(published.notes_repository, NOTES_BRANCH, published.site).text
    )


def test_the_dispatch_workflow_runs_on_every_push_to_the_notes_branch():
    workflow = DispatchWorkflow(
        Repository("an-owner", "a-project"),
        NOTES_BRANCH,
        SiteRepository(Repository("an-owner", "plans")),
    )

    assert WorkflowFile.from_text(workflow.text).pushed_branches == [NOTES_BRANCH]


def test_the_dispatch_workflow_runs_only_in_the_notes_repository():
    notes_repository = Repository("an-owner", "a-project")
    workflow = DispatchWorkflow(
        notes_repository, NOTES_BRANCH, SiteRepository(Repository("an-owner", "plans"))
    )

    job = WorkflowFile.from_text(workflow.text).jobs[PlanSiteJob.DISPATCH]

    assert job.condition == f"github.repository == '{notes_repository.full_name}'"


def test_the_dispatch_workflow_starts_the_site_workflow_with_the_token():
    site = SiteRepository(Repository("an-owner", "plans"))
    workflow = DispatchWorkflow(Repository("an-owner", "a-project"), NOTES_BRANCH, site)

    job = WorkflowFile.from_text(workflow.text).jobs[PlanSiteJob.DISPATCH]

    assert job.steps == [
        WorkflowStep(
            f"gh workflow run {SiteWorkflow.location.name} "
            f"--repo {site.repository.full_name}",
            {
                GitHubCredentialVariable.GH_TOKEN: (
                    f"${{{{ secrets.{PlanSiteSecret.TOKEN} }}}}"
                )
            },
        )
    ]


# %% the merge workflow


def a_dispatch_workflow() -> DispatchWorkflow:
    """:return: A dispatch workflow from a notes repository to its site."""
    return DispatchWorkflow(
        Repository("an-owner", "a-project"),
        NOTES_BRANCH,
        SiteRepository(Repository("an-owner", "plans")),
    )


def test_the_notes_repository_s_default_branch_gets_the_merge_workflow(published):
    dispatch = DispatchWorkflow(
        published.notes_repository, NOTES_BRANCH, published.site
    )

    assert (
        published.file(
            published.notes_repository,
            UPSTREAM_BASE,
            MergeWorkflow.location.as_posix(),
        )
        == MergeWorkflow(dispatch).text
    )


def test_the_merge_workflow_follows_the_notes_repository_s_default_branch(
    publishing,
):
    publishing.create(publishing.site.repository)
    notes_path = publishing.checkout.fork_path
    publishing.git(notes_path, "branch", "trunk", UPSTREAM_BASE)
    publishing.git(notes_path, "symbolic-ref", "HEAD", "refs/heads/trunk")

    publishing.publication(publishing.runs_none()).publish()

    assert publishing.file(
        publishing.notes_repository, "trunk", MergeWorkflow.location.as_posix()
    ) == (
        MergeWorkflow(
            DispatchWorkflow(publishing.notes_repository, NOTES_BRANCH, publishing.site)
        ).text
    )


def test_the_merge_workflow_runs_when_a_pull_request_closes(tmp_path):
    """
    On the base repository's side, so a merged pull request from a fork starts the build
    with the token too.
    """
    path = tmp_path / MergeWorkflow.location.name
    path.write_text(MergeWorkflow(a_dispatch_workflow()).text)

    trigger = Workflow.at(path).trigger(TriggerEvent.PULL_REQUEST_TARGET)

    assert trigger.activity_types == {ActivityType.CLOSED}


def test_the_merge_workflow_runs_for_any_merge_in_the_notes_repository():
    dispatch = a_dispatch_workflow()

    job = WorkflowFile.from_text(MergeWorkflow(dispatch).text).jobs[
        PlanSiteJob.DISPATCH
    ]

    assert job.condition == (
        f"github.repository == '{dispatch.notes_repository.full_name}'"
        " && github.event.pull_request.merged"
    )


def test_the_merge_workflow_starts_the_build_as_the_dispatch_workflow_does():
    dispatch = a_dispatch_workflow()

    merge_job = WorkflowFile.from_text(MergeWorkflow(dispatch).text).jobs[
        PlanSiteJob.DISPATCH
    ]
    dispatch_job = WorkflowFile.from_text(dispatch.text).jobs[PlanSiteJob.DISPATCH]

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
    proposal = protected.merge_workflow_proposal

    protected.publication(client).publish()

    assert client.writes == [
        SentWrite(
            HttpMethod.POST,
            f"{protected.notes_repository.api_path}/pulls",
            {
                "title": proposal.title,
                "head": proposal.head,
                "base": proposal.base,
            },
        )
    ]


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
    path = f"{notes.api_path}/pulls"
    return [
        GitHubRequestFailed(
            status=HTTPStatus.FORBIDDEN,
            detail=DatasetLocation.PULL_REQUEST_REFUSED.read_text(),
            method=HttpMethod.POST,
            path=path,
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
    publication = protected.publication(protected.runs_none())
    protected.git(
        protected.checkout.fork_path,
        "branch",
        "--force",
        UPSTREAM_BASE,
        publication.merge_workflow_branch,
    )

    report = publication.publish()

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
    ]


def test_once_both_workflows_succeeded_nothing_is_left(published):
    runs = published.runs(
        DatasetLocation.PLAN_SITE_RUNS_SUCCEEDED,
        DatasetLocation.PLAN_SITE_DISPATCH_RUNS_SUCCEEDED,
    )

    assert published.publication(runs).publish().complete


def test_a_failed_latest_dispatch_leaves_the_token_to_the_user(published):
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
            status=HTTPStatus.FORBIDDEN, detail="", method=HttpMethod.GET, path=path
        )

    def get_pages(self, path: str):
        raise GitHubRequestFailed(
            status=HTTPStatus.FORBIDDEN, detail="", method=HttpMethod.GET, path=path
        )


def test_runs_that_cannot_be_read_stop_the_publication_before_anything_is_written(
    publishing,
):
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
            publishing.site.repository, "main", SiteWorkflow.location.as_posix()
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


def test_creating_the_token_walks_through_scoping_it_to_every_registered_repository(
    published,
):
    report = published.publication(published.runs_none()).publish()

    browser_steps = pending_step(report, UserStep.CREATE_TOKEN).browser_steps

    text = "\n".join(browser_steps)
    assert UserSteps.token_page in text
    assert published.site.repository.full_name in text
    assert published.notes_repository.full_name in text


def test_creating_a_token_has_no_command_line_because_github_offers_none(published):
    report = published.publication(published.runs_none()).publish()

    assert pending_step(report, UserStep.CREATE_TOKEN).line is None


def test_storing_the_token_is_one_command_that_sets_the_secret_in_every_registered_repository(
    published, tmp_path
):
    second_repository = Repository(published.notes_repository.owner, "another")
    published.create(second_repository)
    second = ForkCheckout.create(tmp_path / "second")
    second.run_git(
        "remote",
        "set-url",
        RemoteName.ORIGIN,
        published.path_of(second_repository).as_uri(),
    )
    second_publishing = Publishing(second, published.root)

    report = second_publishing.publication(second_publishing.runs_none()).publish()

    line = pending_step(report, UserStep.STORE_TOKEN).line
    assert line.count(f"gh secret set {PlanSiteSecret.TOKEN}") == 1
    assert published.notes_repository.full_name in line
    assert second_repository.full_name in line


def test_storing_the_token_in_the_browser_opens_each_registered_repository_s_secret_page(
    published,
):
    report = published.publication(published.runs_none()).publish()

    text = "\n".join(pending_step(report, UserStep.STORE_TOKEN).browser_steps)

    assert f"{published.notes_repository.url}/settings/secrets/actions/new" in text
    assert PlanSiteSecret.TOKEN in text


def test_a_failed_dispatch_run_is_linked_from_the_step_it_leaves_to_the_user(
    published,
):
    runs = published.runs(
        DatasetLocation.PLAN_SITE_RUNS_SUCCEEDED,
        DatasetLocation.PLAN_SITE_DISPATCH_RUNS_FAILED,
    )

    report = published.publication(runs).publish()

    latest_run = pending_step(report, UserStep.STORE_TOKEN).latest_run
    assert latest_run == ListedRun(
        Path(DispatchWorkflow.location),
        CheckOutcome.FAILURE,
        "https://github.com/an-owner/a-repository/actions/runs/4004",
        datetime(2026, 10, 2, 10, tzinfo=UTC),
    )


def test_without_a_run_no_run_is_linked(published):
    report = published.publication(published.runs_none()).publish()

    assert pending_step(report, UserStep.STORE_TOKEN).latest_run is None


def test_a_rendered_step_shows_the_command_and_then_the_browser_steps(published):
    report = published.publication(published.runs_none()).publish()
    pending = pending_step(report, UserStep.TURN_ON_PAGES)

    assert pending.render() == (
        f"- {pending.step}:\n    {pending.line}\n  Or in the browser:\n"
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


def test_a_rendered_step_links_the_latest_run_that_made_it_necessary(published):
    runs = published.runs(
        DatasetLocation.PLAN_SITE_RUNS_SUCCEEDED,
        DatasetLocation.PLAN_SITE_DISPATCH_RUNS_FAILED,
    )
    pending = pending_step(published.publication(runs).publish(), UserStep.STORE_TOKEN)

    assert pending.render().splitlines()[1] == (
        f"  Latest run, {pending.latest_run.outcome}: {pending.latest_run.url}"
    )
