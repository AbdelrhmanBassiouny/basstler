"""
Tests for :mod:`basstler.plan_site.dispatch_check`: whether every repository the plan
site publishes stores the token and starts the site's build.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path

import pytest

from basstler.environment import GitHubCredentialVariable
from basstler.github.client import GitHubAttemptReader, GitHubResponse, HttpMethod
from basstler.github.credential import CredentialProvider
from basstler.github.exceptions import GitHubRequestFailed
from basstler.locations import ClaudeCodeVariable, ProjectLocation
from basstler.maintenance.git_commands import GitCommandRunner
from basstler.maintenance.remote_branch import RemoteBranch
from basstler.personal_notes.branch import PersonalNotesLocation
from basstler.plan_site import dispatch_check
from basstler.plan_site.dispatch_check import (
    UNVERIFIED_PREFIX,
    DispatchCheck,
    DispatchReading,
    DispatchState,
    FailureAfterSuccessCause,
    ReadRefusal,
    RepositoryDispatch,
    TokenSecret,
    UnreadableDispatch,
    published_repositories,
)
from basstler.plan_site.exceptions import NotesRepositoryUnresolvedError
from basstler.plan_site.hub import PlanHub
from basstler.plan_site.publication import PublicationOption
from basstler.github.run_listing import RunListing
from basstler.plan_site.site_repository import SiteRepository
from basstler.plan_site.workflows import DispatchWorkflow, PlanSiteSecret
from basstler.repository import Repository
from basstler.setup.report import CheckResult, CheckStatus
from basstler.setup.steps import PersonalNotesSetting
from basstler.upstream_reviews.vocabulary import CheckOutcome

from ..constants.paths import DatasetLocation
from ..constants.stack import RemoteName
from ..maintenance.fork import ForkCheckout
from .test_hub import publish_notes
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
            credential_origin=CredentialProvider.CALLER,
        ),
    )


def runs_refused(repository: Repository, status: HTTPStatus) -> GitHubResponse:
    """
    :param repository: The repository whose dispatch runs are asked for.
    :param status: The status GitHub refuses with.
    :return: The refusal of a request made with the token in ``GH_TOKEN``.
    """
    return GitHubResponse(
        None,
        failure=GitHubRequestFailed.for_status(
            status=status,
            detail="",
            method=HttpMethod.GET,
            path=RunListing.path(repository, NOTES_BRANCH),
            credential_origin=GitHubCredentialVariable.GH_TOKEN,
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
        DatasetLocation.PLAN_SITE_DISPATCH_RUNS_NEVER_SUCCEEDED, TOKEN_BEFORE_FAILURE
    )

    assert dispatch.state is DispatchState.RUN_FAILED


def test_a_run_failing_after_an_earlier_success_is_told_apart():
    dispatch = dispatch_of(
        DatasetLocation.PLAN_SITE_DISPATCH_RUNS_FAILED, TOKEN_BEFORE_FAILURE
    )

    assert dispatch.state is DispatchState.STOPPED_STARTING_BUILD


def test_a_run_failing_after_an_earlier_success_names_every_cause_to_look_for():
    description = dispatch_of(
        DatasetLocation.PLAN_SITE_DISPATCH_RUNS_FAILED, TOKEN_BEFORE_FAILURE
    ).describe()

    assert [cause for cause in FailureAfterSuccessCause if cause in description] == (
        list(FailureAfterSuccessCause)
    )


def test_a_run_failing_after_an_earlier_success_links_that_success():
    """
    A failure after an earlier success links that success's page.
    """
    listing = DatasetLocation.PLAN_SITE_DISPATCH_RUNS_FAILED
    latest_success = RunListing.read(
        runs_replaying(listing), NOTES_REPOSITORY, NOTES_BRANCH
    ).latest_success(DispatchWorkflow.location)

    assert (
        latest_success.page_url in dispatch_of(listing, TOKEN_BEFORE_FAILURE).describe()
    )


def test_a_token_set_after_the_failed_run_waits_for_the_next_push():
    """
    A token set after the latest failed run is stored after failure.
    """
    dispatch = dispatch_of(
        DatasetLocation.PLAN_SITE_DISPATCH_RUNS_FAILED,
        stored(DatasetLocation.PLAN_SITE_TOKEN_STORED_AFTER_FAILURE),
    )

    assert dispatch.state is DispatchState.TOKEN_STORED_AFTER_FAILURE


def test_a_dispatch_that_never_ran_is_reported():
    dispatch = dispatch_of(DatasetLocation.WORKFLOW_RUNS_NONE, TOKEN_BEFORE_FAILURE)

    assert dispatch.state is DispatchState.NEVER_RAN


@pytest.mark.parametrize(
    ("listing", "expected"),
    [
        (DatasetLocation.PLAN_SITE_DISPATCH_RUNS_SUCCEEDED, DispatchState.STARTS_BUILD),
        (
            DatasetLocation.PLAN_SITE_DISPATCH_RUNS_NEVER_SUCCEEDED,
            DispatchState.RUN_FAILED,
        ),
    ],
)
def test_a_secret_that_cannot_be_read_leaves_the_verdict_to_the_runs(listing, expected):
    dispatch = dispatch_of(listing, refused(NOTES_REPOSITORY, HTTPStatus.FORBIDDEN))

    assert dispatch.state is expected


def test_a_failed_run_is_linked():
    """
    The latest failed run's page is linked.
    """
    listing = DatasetLocation.PLAN_SITE_DISPATCH_RUNS_FAILED
    latest = RunListing.read(
        runs_replaying(listing), NOTES_REPOSITORY, NOTES_BRANCH
    ).latest(DispatchWorkflow.location)

    assert latest.page_url in dispatch_of(listing, TOKEN_BEFORE_FAILURE).describe()


def test_every_failed_run_is_counted():
    """
    Every failed run in the listing is counted.
    """
    listing = DatasetLocation.PLAN_SITE_DISPATCH_RUNS_NEVER_SUCCEEDED
    recorded = RunListing.read(runs_replaying(listing), NOTES_REPOSITORY, NOTES_BRANCH)

    dispatch = dispatch_of(listing, TOKEN_BEFORE_FAILURE)

    assert dispatch.runs.count(CheckOutcome.FAILURE) == len(recorded.workflow_runs)


def test_a_failed_run_reports_the_dispatch_run_history():
    dispatch = dispatch_of(
        DatasetLocation.PLAN_SITE_DISPATCH_RUNS_NEVER_SUCCEEDED, TOKEN_BEFORE_FAILURE
    )

    assert dispatch.run_history in dispatch.describe()


def test_a_missing_token_says_how_to_store_it():
    description = dispatch_of(
        DatasetLocation.PLAN_SITE_DISPATCH_RUNS_NEVER_SUCCEEDED,
        refused(NOTES_REPOSITORY, HTTPStatus.NOT_FOUND),
    ).describe()

    assert (
        f"gh secret set {PlanSiteSecret.TOKEN} --repo {NOTES_REPOSITORY.full_name}"
        in description
    )


def test_a_missing_token_reports_the_dispatch_run_history():
    dispatch = dispatch_of(
        DatasetLocation.PLAN_SITE_DISPATCH_RUNS_NEVER_SUCCEEDED,
        refused(NOTES_REPOSITORY, HTTPStatus.NOT_FOUND),
    )

    assert dispatch.run_history in dispatch.describe()


def test_a_failed_run_says_whether_the_token_is_stored():
    dispatch = dispatch_of(
        DatasetLocation.PLAN_SITE_DISPATCH_RUNS_NEVER_SUCCEEDED, TOKEN_BEFORE_FAILURE
    )

    assert dispatch.token.describe(NOTES_REPOSITORY) in dispatch.describe()


def reading_with_runs_refused(status: HTTPStatus) -> DispatchReading:
    """
    :param status: The status GitHub refuses the notes repository's runs with.
    :return: What reading its dispatch found.
    """
    refusing = SecretAnsweringClient(
        {
            RunListing.path(NOTES_REPOSITORY, NOTES_BRANCH): runs_refused(
                NOTES_REPOSITORY, status
            )
        }
    )
    return DispatchReading.read(refusing, refusing, NOTES_REPOSITORY, NOTES_BRANCH)


def test_runs_that_cannot_be_read_leave_the_dispatch_unverified():
    reading = reading_with_runs_refused(HTTPStatus.UNAUTHORIZED)

    assert isinstance(reading, UnreadableDispatch)
    assert reading.status is CheckStatus.UNVERIFIED


def test_a_rejected_session_token_is_named_and_told_apart_from_the_secret():
    """
    A rejected session token is reported by the failure and told apart from the secret.
    """
    reading = reading_with_runs_refused(HTTPStatus.UNAUTHORIZED)

    description = reading.describe()

    assert reading.failure.error_message() in description
    assert PlanSiteSecret.TOKEN in description


# %% the clone's own repository is judged


def starting_the_build(repository: Repository) -> RepositoryDispatch:
    """
    :param repository: The repository.
    :return: Its dispatch, which starts the build.
    """
    return dispatch_of(
        DatasetLocation.PLAN_SITE_DISPATCH_RUNS_SUCCEEDED,
        TOKEN_BEFORE_FAILURE,
        repository,
    )


def missing_the_token(repository: Repository) -> RepositoryDispatch:
    """
    :param repository: The repository.
    :return: Its dispatch, which stores no token.
    """
    return dispatch_of(
        DatasetLocation.PLAN_SITE_DISPATCH_RUNS_SUCCEEDED,
        refused(repository, HTTPStatus.NOT_FOUND),
        repository,
    )


def unreadable(repository: Repository) -> UnreadableDispatch:
    """
    :param repository: The repository.
    :return: Its dispatch, whose runs GitHub refuses to list.
    """
    refusing = SecretAnsweringClient(
        {
            RunListing.path(repository, NOTES_BRANCH): runs_refused(
                repository, HTTPStatus.FORBIDDEN
            )
        }
    )
    return DispatchReading.read(refusing, refusing, repository, NOTES_BRANCH)


def test_the_own_repository_starting_the_build_is_ok():
    check = DispatchCheck(starting_the_build(NOTES_REPOSITORY), [])

    assert check.result().status is CheckStatus.OK


def test_the_own_repository_missing_the_token_needs_setup():
    check = DispatchCheck(missing_the_token(NOTES_REPOSITORY), [])

    assert check.result().status is CheckStatus.NEEDS_SETUP


def test_the_own_repository_is_judged_whatever_the_others_are():
    check = DispatchCheck(
        starting_the_build(NOTES_REPOSITORY), [missing_the_token(OTHER_REPOSITORY)]
    )

    assert check.result().status is CheckStatus.OK


def test_the_verdict_names_only_the_own_repository():
    check = DispatchCheck(
        missing_the_token(NOTES_REPOSITORY), [missing_the_token(OTHER_REPOSITORY)]
    )

    detail = check.result().detail

    assert NOTES_REPOSITORY.full_name in detail
    assert OTHER_REPOSITORY.full_name not in detail


def test_a_token_waiting_for_the_next_push_is_not_verified():
    result = DispatchCheck(
        dispatch_of(
            DatasetLocation.PLAN_SITE_DISPATCH_RUNS_FAILED,
            stored(DatasetLocation.PLAN_SITE_TOKEN_STORED_AFTER_FAILURE),
        ),
        [],
    ).result()

    assert result.status is CheckStatus.UNVERIFIED
    assert result.detail.startswith(UNVERIFIED_PREFIX)


# %% every other repository is informational


def test_every_other_repository_has_one_informational_row():
    others = [
        starting_the_build(OTHER_REPOSITORY),
        missing_the_token(Repository.parse("an-owner/a-third-repository")),
    ]
    check = DispatchCheck(starting_the_build(NOTES_REPOSITORY), others)

    assert check.other_results() == [
        CheckResult(CheckStatus.INFORMATIONAL, other.describe()) for other in others
    ]


def test_another_repository_missing_the_token_stays_informational_and_says_so():
    check = DispatchCheck(
        starting_the_build(NOTES_REPOSITORY), [missing_the_token(OTHER_REPOSITORY)]
    )

    (row,) = check.other_results()

    assert row.status is CheckStatus.INFORMATIONAL
    assert row.detail == missing_the_token(OTHER_REPOSITORY).describe()


def test_another_repository_that_cannot_be_read_is_not_a_fault():
    check = DispatchCheck(
        starting_the_build(NOTES_REPOSITORY), [unreadable(OTHER_REPOSITORY)]
    )

    (row,) = check.other_results()

    assert row.status is CheckStatus.INFORMATIONAL
    assert row.detail == unreadable(OTHER_REPOSITORY).describe()
    assert check.result().status is CheckStatus.OK


def test_the_rows_are_the_verdict_then_one_per_other_repository():
    check = DispatchCheck(
        starting_the_build(NOTES_REPOSITORY),
        [missing_the_token(OTHER_REPOSITORY)],
    )

    assert check.rows() == [check.result(), *check.other_results()]


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
    fork_checkout: ForkCheckout,
    notes_location: PersonalNotesLocation,
    tmp_path: Path,
):
    own_copy = PlanHub(
        registry=OTHER_REPOSITORY.full_name, repositories=[NOTES_REPOSITORY.full_name]
    )
    RemoteBranch(
        NOTES_BRANCH, GitCommandRunner(fork_checkout.project_root), RemoteName.ORIGIN
    ).write({ProjectLocation.PLAN_HUB.as_posix(): own_copy.to_text()}, "List the hub")
    registry_copy = PlanHub(
        registry=OTHER_REPOSITORY.full_name,
        repositories=[OTHER_REPOSITORY.full_name, NOTES_REPOSITORY.full_name],
    )
    publish_notes(
        tmp_path,
        OTHER_REPOSITORY,
        {Path(ProjectLocation.PLAN_HUB.name): registry_copy.to_text()},
    )

    assert published_repositories(
        fork_checkout.project_root, notes_location, NOTES_REPOSITORY, str(tmp_path)
    ) == [NOTES_REPOSITORY, OTHER_REPOSITORY]


# %% the command


def test_a_notes_remote_off_github_cannot_be_checked(
    fork_checkout: ForkCheckout, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(fork_checkout.project_root)
    monkeypatch.delenv(ClaudeCodeVariable.PROJECT_DIRECTORY, raising=False)

    with pytest.raises(NotesRepositoryUnresolvedError):
        dispatch_check.report_dispatch()


def test_runs_that_cannot_be_read_are_reported_as_not_verified():
    result = DispatchCheck(
        reading_with_runs_refused(HTTPStatus.UNAUTHORIZED), []
    ).result()

    assert result.status is CheckStatus.UNVERIFIED
    assert result.detail.startswith(UNVERIFIED_PREFIX)


def test_the_recorded_site_repository_is_named_in_the_command():
    """
    The publication command names the site repository the notes branch records.
    """
    site = SiteRepository(Repository("An-Owner", "a-site"))
    check = DispatchCheck(
        dispatch_of(
            DatasetLocation.PLAN_SITE_DISPATCH_RUNS_NEVER_SUCCEEDED,
            refused(NOTES_REPOSITORY, HTTPStatus.NOT_FOUND),
        ),
        [],
        site,
    )

    assert (
        f"{PublicationOption.SITE_REPOSITORY} {site.repository.full_name}"
        in check.result().detail
    )


# %% a read GitHub refused


def test_a_refusal_with_a_multi_line_body_is_reported_on_one_line():
    """
    A refusal whose body spans several lines still fits one report row.
    """
    failure = GitHubRequestFailed.for_status(
        status=HTTPStatus.FORBIDDEN,
        detail="first line\nsecond line",
        method=HttpMethod.GET,
        path=TokenSecret.path(NOTES_REPOSITORY),
        credential_origin=CredentialProvider.CALLER,
    )

    assert "\n" not in ReadRefusal(failure).describe()
