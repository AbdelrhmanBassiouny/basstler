"""
Tests for plan_site/publication.py: publishing a repository's plans on the user's plan
site, against bare repositories standing in for GitHub and recorded run listings.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from basstler.environment import GitHubCredentialVariable
from basstler.locations import ProjectLocation, WorkflowLocation
from basstler.maintenance.git_commands import GitCommandRunner
from basstler.plan_site.hub import PlanHub
from basstler.plan_site.publication import (
    PlanSitePublication,
    RunListing,
    UserStep,
    UserSteps,
)
from basstler.plan_site.site_repository import SiteRepository
from basstler.plan_site.workflows import (
    DispatchWorkflow,
    PlanSiteJob,
    PlanSiteSecret,
    SiteWorkflow,
    WorkflowFile,
    WorkflowStep,
)
from basstler.repository import GitHubAddress, Repository
from basstler.setup.steps import PersonalNotesSetting
from basstler.upstream_reviews.vocabulary import BasstlerSource

from ..constants.paths import DatasetLocation
from ..constants.stack import RemoteName
from ..maintenance.fork import ForkCheckout
from ..upstream_reviews.replay import ReplayingRestClient

BRANCH_OR_TAG = "v9.9.9"
"""
The basstler release the published workflows run.
"""

NOTES_BRANCH = PersonalNotesSetting.BRANCH.default
"""
The notes branch every repository under test keeps its notes on.
"""

# %% a notes repository, its site repository and other registered repositories


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

    def publication(self, runs: ReplayingRestClient) -> PlanSitePublication:
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
    ) -> ReplayingRestClient:
        """:return: A client answering both run listings from recordings."""
        return ReplayingRestClient(
            {
                RunListing.path(self.site.repository, site_branch): json.loads(
                    site_listing.read_text()
                ),
                RunListing.path(self.notes_repository, NOTES_BRANCH): json.loads(
                    notes_listing.read_text()
                ),
            }
        )

    def runs_none(self) -> ReplayingRestClient:
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


# %% re-running


def test_publishing_again_writes_nothing(published):
    report = published.publication(published.runs_none()).publish()

    assert report.written == []


def test_without_successful_runs_pages_and_the_token_are_left_to_the_user(published):
    report = published.publication(published.runs_none()).publish()

    assert [pending.step for pending in report.pending] == [
        UserStep.TURN_ON_PAGES,
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

    assert [pending.step for pending in report.pending] == [UserStep.STORE_TOKEN]


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


def test_storing_the_token_walks_through_creating_it_and_saving_it_as_a_secret(
    published,
):
    report = published.publication(published.runs_none()).publish()

    browser_steps = pending_step(report, UserStep.STORE_TOKEN).browser_steps

    text = "\n".join(browser_steps)
    assert UserSteps.token_page in text
    assert published.site.repository.full_name in text
    assert published.notes_repository.full_name in text
    assert f"{published.notes_repository.url}/settings/secrets/actions/new" in text
    assert PlanSiteSecret.TOKEN in text


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
