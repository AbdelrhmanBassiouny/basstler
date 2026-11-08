"""
Tests for :mod:`basstler.plan_site.token_storage`: storing the plan site's token in
every repository and proving each copy with the dispatch run it starts.
"""

from __future__ import annotations

import io
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from http import HTTPStatus
from typing import Any

import pytest

from basstler.github.client import GitHubResponse, GitHubWrite
from basstler.github.credential import CredentialProvider
from basstler.github.exceptions import GitHubRequestFailed
from basstler.locations import WorkflowLocation
from basstler.plan_site import token_storage
from basstler.plan_site.exceptions import PlanSiteTokenEmptyError
from basstler.github.run_listing import RunListing
from basstler.github.workflow_run import WorkflowDispatch
from basstler.plan_site.token_storage import (
    GitHubCommandLineSecretStore,
    SecretStore,
    StorageResult,
    TokenStorage,
    read_token,
)
from basstler.plan_site.workflows import PlanSiteSecret
from basstler.repository import Repository

from ..constants.paths import DatasetLocation
from ..github.recorded_client import RecordedGitHubClient

NOTES_BRANCH = "claude/personal-notes"
"""
The branch every repository's dispatch workflow runs on.
"""

FIRST = Repository("an-owner", "a-repository")
"""
The first repository the token is stored in.
"""

SECOND = Repository("an-owner", "another-repository")
"""
The second repository the token is stored in.
"""

TOKEN = "a-token"
"""
The token stored.
"""

# %% mimics


@dataclass
class RecordingSecretStore(SecretStore):
    """
    Records every secret it is given, refusing the repositories in :attr:`refusals`.
    """

    refusals: Mapping[Repository, str] = field(default_factory=dict)
    """
    Why each refused repository refuses, by repository.
    """

    stored: list[tuple[Repository, PlanSiteSecret, str]] = field(default_factory=list)
    """
    Every secret stored, oldest first.
    """

    def store(self, repository: Repository, secret: PlanSiteSecret, value: str) -> str:
        refusal = self.refusals.get(repository, "")
        if not refusal:
            self.stored.append((repository, secret, value))
        return refusal


@dataclass
class RunStartingClient(RecordedGitHubClient):
    """
    Lists :attr:`listing_before` until a dispatch is sent, then :attr:`listing_after`,
    for every repository.
    """

    listing_before: DatasetLocation = DatasetLocation.WORKFLOW_RUNS_NONE
    """
    The run listing before the dispatch.
    """

    listing_after: DatasetLocation = DatasetLocation.PLAN_SITE_DISPATCH_RUNS_SUCCEEDED
    """
    The run listing once the dispatch was sent.
    """

    dispatch_refusal: HTTPStatus | None = None
    """
    The status the dispatch is refused with, ``None`` to accept it.
    """

    pending_reads: int = 0
    """
    How many reads after the dispatch list
    :attr:`DatasetLocation.PLAN_SITE_DISPATCH_RUNS_PENDING` before :attr:`listing_after`.
    """

    def get(self, path: str) -> Any:
        """
        Unlike :meth:`RecordedGitHubClient.get`, answer every path with a run listing.
        """
        if not self.writes:
            return json.loads(self.listing_before.read_text())
        if self.pending_reads:
            self.pending_reads -= 1
            return json.loads(
                DatasetLocation.PLAN_SITE_DISPATCH_RUNS_PENDING.read_text()
            )
        return json.loads(self.listing_after.read_text())

    def attempt_send(self, write: GitHubWrite) -> GitHubResponse:
        """
        Unlike :meth:`RecordedGitHubClient.attempt_send`, refuse the write with
        :attr:`dispatch_refusal` when it is set.
        """
        self.writes.append(write)
        if self.dispatch_refusal is None:
            return GitHubResponse(None)
        return GitHubResponse(
            None,
            failure=GitHubRequestFailed(
                status=self.dispatch_refusal,
                detail="",
                method=write.method,
                path=write.path,
                credential_origin=CredentialProvider.CALLER,
            ),
        )


@dataclass
class PauseCounter:
    """
    Counts the waits asked for instead of waiting.
    """

    pauses: list[float] = field(default_factory=list)
    """
    Every wait asked for, in seconds.
    """

    def __call__(self, seconds: float) -> None:
        self.pauses.append(seconds)


def storage_with(
    client: RunStartingClient, secrets: SecretStore | None = None
) -> TokenStorage:
    """
    :param client: Starts the dispatch workflows and lists their runs.
    :param secrets: Where the token is stored, a recording store when not given.
    :return: A storage that never waits.
    """
    return TokenStorage(
        NOTES_BRANCH,
        secrets or RecordingSecretStore(),
        client,
        pause=PauseCounter(),
    )


def latest_dispatch_run(listing: DatasetLocation):
    """:return: The latest dispatch run in *listing*."""
    return RunListing.from_json(json.loads(listing.read_text())).latest(
        WorkflowLocation.PLAN_SITE_DISPATCH
    )


# %% storing


def test_the_token_is_stored_in_every_repository_given():
    secrets = RecordingSecretStore()

    storage_with(RunStartingClient(), secrets).store([FIRST, SECOND], TOKEN)

    assert secrets.stored == [
        (FIRST, PlanSiteSecret.TOKEN, TOKEN),
        (SECOND, PlanSiteSecret.TOKEN, TOKEN),
    ]


def test_a_refused_store_starts_no_dispatch_and_says_why():
    client = RunStartingClient()
    refusal = "HTTP 403"

    (result,) = storage_with(client, RecordingSecretStore({FIRST: refusal})).store(
        [FIRST], TOKEN
    )

    assert (client.writes, result) == ([], StorageResult(FIRST, refusal))


def test_a_missing_command_line_client_is_reported_as_the_refusal():
    executable = "no-such-github-command-line"

    refusal = GitHubCommandLineSecretStore(executable).store(
        FIRST, PlanSiteSecret.TOKEN, TOKEN
    )

    assert refusal == f"{executable} is not installed"


# %% proving


def test_a_stored_token_starts_the_dispatch_workflow_on_the_notes_branch():
    """
    A stored token is proven by dispatching the workflow on the notes branch.
    """
    client = RunStartingClient()

    storage_with(client).store([FIRST], TOKEN)

    assert client.writes == [
        WorkflowDispatch(FIRST, WorkflowLocation.PLAN_SITE_DISPATCH, NOTES_BRANCH)
    ]


def test_a_succeeded_dispatch_run_proves_the_token():
    (result,) = storage_with(RunStartingClient()).store([FIRST], TOKEN)

    assert result == StorageResult(
        FIRST,
        run=latest_dispatch_run(DatasetLocation.PLAN_SITE_DISPATCH_RUNS_SUCCEEDED),
    )
    assert result.proven


def test_a_failed_dispatch_run_is_linked_and_proves_nothing():
    """
    A dispatch run that failed leaves the token unproven and links the run's page.
    """
    listing = DatasetLocation.PLAN_SITE_DISPATCH_RUNS_FAILED

    (result,) = storage_with(RunStartingClient(listing_after=listing)).store(
        [FIRST], TOKEN
    )

    run = latest_dispatch_run(listing)
    assert (result.run, result.proven) == (run, False)
    assert run.page_url in result.describe(timedelta())


def test_a_run_listed_before_the_dispatch_is_not_taken_for_the_one_it_started():
    listing = DatasetLocation.PLAN_SITE_DISPATCH_RUNS_SUCCEEDED
    client = RunStartingClient(listing_before=listing, listing_after=listing)

    (result,) = storage_with(client).store([FIRST], TOKEN)

    assert result == StorageResult(FIRST)


def test_waiting_for_the_run_stops_after_the_wait():
    client = RunStartingClient(listing_after=DatasetLocation.WORKFLOW_RUNS_NONE)
    pause = PauseCounter()
    storage = TokenStorage(
        NOTES_BRANCH,
        RecordingSecretStore(),
        client,
        wait=timedelta(seconds=30),
        interval=timedelta(seconds=10),
        pause=pause,
    )

    storage.store([FIRST], TOKEN)

    assert pause.pauses == [storage.interval.total_seconds()] * int(
        storage.wait / storage.interval
    )


def test_a_refused_dispatch_is_reported_without_waiting():
    storage = storage_with(RunStartingClient(dispatch_refusal=HTTPStatus.FORBIDDEN))

    (result,) = storage.store([FIRST], TOKEN)

    assert result.refusal
    assert result.run is None
    assert storage.pause.pauses == []


def test_a_running_dispatch_run_is_waited_for_until_it_finishes():
    storage = storage_with(RunStartingClient(pending_reads=1))

    (result,) = storage.store([FIRST], TOKEN)

    assert result.run == latest_dispatch_run(
        DatasetLocation.PLAN_SITE_DISPATCH_RUNS_SUCCEEDED
    )
    assert len(storage.pause.pauses) == 2


# %% reading the token


def test_an_empty_token_is_refused(monkeypatch):
    monkeypatch.setattr(token_storage.sys, "stdin", io.StringIO("\n"))

    with pytest.raises(PlanSiteTokenEmptyError):
        read_token()


def test_a_piped_token_is_read_without_its_line_break(monkeypatch):
    monkeypatch.setattr(token_storage.sys, "stdin", io.StringIO(f"{TOKEN}\n"))

    assert read_token() == TOKEN
