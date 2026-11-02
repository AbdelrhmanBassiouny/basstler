"""
Tests for :mod:`basstler.plan_site.dispatch_check`: whether every repository the plan
site publishes stores the token and starts the site's build.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from http import HTTPStatus

import pytest

from basstler.github.client import GitHubAttemptReader, GitHubResponse, HttpMethod
from basstler.github.exceptions import GitHubRequestFailed
from basstler.locations import ClaudeCodeVariable, ProjectLocation
from basstler.maintenance.git_commands import GitCommandRunner
from basstler.maintenance.remote_branch import RemoteBranch
from basstler.personal_notes.branch import PersonalNotesLocation
from basstler.plan_site import dispatch_check
from basstler.plan_site.dispatch_check import (
    DispatchCheck,
    DispatchState,
    RepositoryDispatch,
    TokenSecret,
    published_repositories,
)
from basstler.plan_site.exceptions import NotesRepositoryUnresolvedError
from basstler.plan_site.hub import PlanHub
from basstler.plan_site.run_listing import RunListing
from basstler.plan_site.workflows import DispatchWorkflow
from basstler.repository import Repository
from basstler.setup.report import CheckStatus
from basstler.setup.steps import PersonalNotesSetting

from ..constants.paths import DatasetLocation
from ..constants.stack import RemoteName
from ..maintenance.fork import ForkCheckout
from ..upstream_reviews.replay import ReplayingRestClient

NOTES_REPOSITORY = Repository.parse("an-owner/a-repository")
"""
The notes repository whose dispatch is checked.
"""

OTHER_REPOSITORY = Repository.parse("an-owner/another-repository")
"""
A second repository the plan site publishes.
"""

NOTES_BRANCH = PersonalNotesSetting.BRANCH.default
"""
The notes branch the dispatch runs on.
"""

# %% recorded answers


@dataclass
class SecretAnsweringClient(GitHubAttemptReader):
    """
    Answers each secret's path with a recorded answer.
    """

    answers: dict[str, GitHubResponse]
    """
    The answer each path gets.
    """

    def attempt_get(self, path: str) -> GitHubResponse:
        return self.answers[path]


def refused(repository: Repository, status: HTTPStatus) -> GitHubResponse:
    """
    :param repository: The repository whose secret is asked for.
    :param status: The status GitHub refuses with.
    :return: The refusal.
    """
    return GitHubResponse(
        None,
        failure=GitHubRequestFailed(
            status=status,
            detail="",
            method=HttpMethod.GET,
            path=TokenSecret.path(repository),
        ),
    )


def stored(secret: DatasetLocation) -> GitHubResponse:
    """
    :param secret: The recorded secret.
    :return: GitHub's answer with it.
    """
    return GitHubResponse(json.loads(secret.read_text()))


def runs_replaying(
    listing: DatasetLocation, repository: Repository = NOTES_REPOSITORY
) -> ReplayingRestClient:
    """
    :param listing: The recorded run listing of the repository's notes branch.
    :param repository: The repository.
    :return: A client answering with that listing.
    """
    return ReplayingRestClient(
        {RunListing.path(repository, NOTES_BRANCH): json.loads(listing.read_text())}
    )


def dispatch_of(
    listing: DatasetLocation,
    secret: GitHubResponse,
    repository: Repository = NOTES_REPOSITORY,
) -> RepositoryDispatch:
    """
    :param listing: The recorded run listing of the repository's notes branch.
    :param secret: GitHub's answer for its token secret.
    :param repository: The repository.
    :return: Its dispatch, read from those answers.
    """
    return RepositoryDispatch.read(
        runs_replaying(listing, repository),
        SecretAnsweringClient({TokenSecret.path(repository): secret}),
        repository,
        NOTES_BRANCH,
    )


TOKEN_BEFORE_FAILURE = stored(DatasetLocation.PLAN_SITE_TOKEN_STORED_BEFORE_FAILURE)
"""
A token set before the recorded failed dispatch run started.
"""


# %% one repository's dispatch


def test_a_stored_token_and_a_succeeded_run_start_the_build():
    dispatch = dispatch_of(
        DatasetLocation.PLAN_SITE_DISPATCH_RUNS_SUCCEEDED, TOKEN_BEFORE_FAILURE
    )

    assert dispatch.state is DispatchState.STARTS_BUILD


def test_a_missing_token_is_reported_even_after_a_succeeded_run():
    dispatch = dispatch_of(
        DatasetLocation.PLAN_SITE_DISPATCH_RUNS_SUCCEEDED,
        refused(NOTES_REPOSITORY, HTTPStatus.NOT_FOUND),
    )

    assert dispatch.state is DispatchState.TOKEN_MISSING


def test_a_run_that_failed_with_the_stored_token_is_reported():
    dispatch = dispatch_of(
        DatasetLocation.PLAN_SITE_DISPATCH_RUNS_FAILED, TOKEN_BEFORE_FAILURE
    )

    assert dispatch.state is DispatchState.RUN_FAILED


def test_a_token_set_after_the_failed_run_waits_for_the_next_push():
    dispatch = dispatch_of(
        DatasetLocation.PLAN_SITE_DISPATCH_RUNS_FAILED,
        stored(DatasetLocation.PLAN_SITE_TOKEN_STORED_AFTER_FAILURE),
    )

    assert dispatch.state is DispatchState.TOKEN_STORED_SINCE_FAILURE


def test_a_dispatch_that_never_ran_is_reported():
    dispatch = dispatch_of(DatasetLocation.WORKFLOW_RUNS_NONE, TOKEN_BEFORE_FAILURE)

    assert dispatch.state is DispatchState.NEVER_RAN


@pytest.mark.parametrize(
    ("listing", "expected"),
    [
        (DatasetLocation.PLAN_SITE_DISPATCH_RUNS_SUCCEEDED, DispatchState.STARTS_BUILD),
        (DatasetLocation.PLAN_SITE_DISPATCH_RUNS_FAILED, DispatchState.RUN_FAILED),
    ],
)
def test_a_secret_that_cannot_be_read_leaves_the_verdict_to_the_runs(listing, expected):
    dispatch = dispatch_of(listing, refused(NOTES_REPOSITORY, HTTPStatus.FORBIDDEN))

    assert dispatch.state is expected


def test_a_failed_run_is_linked():
    listing = DatasetLocation.PLAN_SITE_DISPATCH_RUNS_FAILED
    latest = RunListing.read(
        runs_replaying(listing), NOTES_REPOSITORY, NOTES_BRANCH
    ).latest(DispatchWorkflow.location)

    assert latest.url in dispatch_of(listing, TOKEN_BEFORE_FAILURE).describe()


# %% every repository the plan site publishes


def test_every_repository_starting_the_build_is_ok():
    check = DispatchCheck(
        [
            dispatch_of(
                DatasetLocation.PLAN_SITE_DISPATCH_RUNS_SUCCEEDED,
                TOKEN_BEFORE_FAILURE,
                repository,
            )
            for repository in (NOTES_REPOSITORY, OTHER_REPOSITORY)
        ]
    )

    assert check.result().status is CheckStatus.OK


def one_repository_missing_the_token() -> DispatchCheck:
    """
    :return: A check over the notes repository, starting the build, and
        :data:`OTHER_REPOSITORY`, which stores no token.
    """
    return DispatchCheck(
        [
            dispatch_of(
                DatasetLocation.PLAN_SITE_DISPATCH_RUNS_SUCCEEDED, TOKEN_BEFORE_FAILURE
            ),
            dispatch_of(
                DatasetLocation.PLAN_SITE_DISPATCH_RUNS_SUCCEEDED,
                refused(OTHER_REPOSITORY, HTTPStatus.NOT_FOUND),
                OTHER_REPOSITORY,
            ),
        ]
    )


def test_one_repository_missing_the_token_needs_setup():
    assert one_repository_missing_the_token().result().status is (
        CheckStatus.NEEDS_SETUP
    )


def test_only_the_repositories_not_starting_the_build_are_named():
    detail = one_repository_missing_the_token().result().detail

    assert OTHER_REPOSITORY.full_name in detail
    assert f"{NOTES_REPOSITORY.full_name} " not in detail


def test_a_token_waiting_for_the_next_push_is_context_rather_than_setup():
    check = DispatchCheck(
        [
            dispatch_of(
                DatasetLocation.PLAN_SITE_DISPATCH_RUNS_FAILED,
                stored(DatasetLocation.PLAN_SITE_TOKEN_STORED_AFTER_FAILURE),
            )
        ]
    )

    assert check.result().status is CheckStatus.INFORMATIONAL


# %% the repositories the hub lists


@pytest.fixture
def notes_location() -> PersonalNotesLocation:
    """:return: Notes kept on the fork checkout's ``origin``."""
    return PersonalNotesLocation(
        RemoteName.ORIGIN, NOTES_BRANCH, str(ProjectLocation.PERSONAL_NOTES_DOCUMENT)
    )


def test_without_a_hub_only_the_notes_repository_is_published(
    fork_checkout: ForkCheckout, notes_location: PersonalNotesLocation
):
    assert published_repositories(
        fork_checkout.project_root, notes_location, NOTES_REPOSITORY
    ) == [NOTES_REPOSITORY]


def test_every_repository_the_registry_s_hub_lists_is_published(
    fork_checkout: ForkCheckout, notes_location: PersonalNotesLocation
):
    hub = PlanHub(
        registry=NOTES_REPOSITORY.full_name,
        repositories=[OTHER_REPOSITORY.full_name, NOTES_REPOSITORY.full_name],
    )
    RemoteBranch(
        NOTES_BRANCH, GitCommandRunner(fork_checkout.project_root), RemoteName.ORIGIN
    ).write({ProjectLocation.PLAN_HUB.as_posix(): hub.to_text()}, "List the hub")

    assert published_repositories(
        fork_checkout.project_root, notes_location, NOTES_REPOSITORY
    ) == [NOTES_REPOSITORY, OTHER_REPOSITORY]


# %% the command


def test_a_notes_remote_off_github_cannot_be_checked(
    fork_checkout: ForkCheckout, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(fork_checkout.project_root)
    monkeypatch.delenv(ClaudeCodeVariable.PROJECT_DIRECTORY, raising=False)

    with pytest.raises(NotesRepositoryUnresolvedError):
        dispatch_check.main()
