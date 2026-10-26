"""
Tests for reading a commit's checks: judging each one, the verdict they add up to, and
the client reading them from the API.
"""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest

from basstler.maintenance.check_results import (
    CheckField,
    CheckResult,
    CheckState,
    CommitChecks,
)
from basstler.maintenance.github import (
    CommentField,
    CommitPath,
    GitHubRepository,
    IssuePath,
    ListingParameter,
    RepositoryPath,
)

from ..constants.paths import RecordedCommitChecks
from .fork import PullRequestHeadRepository

A_COMMIT = "0123456789abcdef0123456789abcdef01234567"
"""
The commit every recorded payload here describes.
"""


def recorded(response: RecordedCommitChecks) -> Any:
    """
    :param response: A recorded payload.
    :return: It, decoded.
    """
    return json.loads(response.read_text())


def checks_of(
    check_runs: RecordedCommitChecks, combined_status: RecordedCommitChecks
) -> CommitChecks:
    """
    :param check_runs: The recorded check-run listing.
    :param combined_status: The recorded combined status.
    :return: The checks the two add up to.
    """
    return CommitChecks.from_json(
        A_COMMIT,
        recorded(check_runs)[CheckField.CHECK_RUNS],
        recorded(combined_status),
    )


# %% the verdict


@pytest.mark.parametrize(
    "check_runs, combined_status, state",
    [
        (
            RecordedCommitChecks.ONE_CHECK_RUN_FAILING,
            RecordedCommitChecks.NO_STATUSES,
            CheckState.FAILING,
        ),
        (
            RecordedCommitChecks.ONE_CHECK_RUN_RUNNING,
            RecordedCommitChecks.NO_STATUSES,
            CheckState.PENDING,
        ),
        (
            RecordedCommitChecks.EVERY_CHECK_RUN_FINISHED,
            RecordedCommitChecks.NO_STATUSES,
            CheckState.PASSING,
        ),
        (
            RecordedCommitChecks.EVERY_CHECK_RUN_FINISHED,
            RecordedCommitChecks.ONE_STATUS_ERRORING,
            CheckState.FAILING,
        ),
        (
            RecordedCommitChecks.NO_CHECK_RUNS,
            RecordedCommitChecks.NO_STATUSES,
            CheckState.NO_CHECKS,
        ),
    ],
)
def test_the_checks_on_a_commit_add_up_to_one_verdict(
    check_runs: RecordedCommitChecks,
    combined_status: RecordedCommitChecks,
    state: CheckState,
):
    assert checks_of(check_runs, combined_status).state is state


def test_a_failure_outranks_a_check_still_running():
    """
    The recording has one check failed and one still running: waiting for the second
    cannot make the commit green.
    """
    checks = checks_of(
        RecordedCommitChecks.ONE_CHECK_RUN_FAILING, RecordedCommitChecks.NO_STATUSES
    )

    assert CheckState.PENDING in {result.state for result in checks.results}
    assert checks.state is CheckState.FAILING


def test_only_the_failing_checks_are_named_from_both_kinds():
    check_runs = recorded(RecordedCommitChecks.ONE_CHECK_RUN_FAILING)[
        CheckField.CHECK_RUNS
    ]
    statuses = recorded(RecordedCommitChecks.ONE_STATUS_ERRORING)

    checks = CommitChecks.from_json(A_COMMIT, check_runs, statuses)

    assert checks.failing_check_names == (
        CheckResult.from_check_run(check_runs[0]).check_name,
        CheckResult.from_commit_status(statuses[CheckField.STATUSES][0]).check_name,
    )


# %% the client reading them


@dataclass(frozen=True)
class RepositoryAnsweringFromRecordings(GitHubRepository):
    """
    A repository client answering every call from a recorded response, keyed by path.
    """

    responses: Mapping[str, Any] = field(default_factory=dict)
    """
    The decoded response to each path.
    """

    def _call(
        self, method: str, path: str, payload: Mapping[str, Any] | None = None
    ) -> Any:
        return self.responses[path]


def first_page(path: str) -> str:
    """
    :param path: A paged listing below the repository.
    :return: The path its first page is read from.
    """
    query = urllib.parse.urlencode(
        {
            ListingParameter.PAGE_SIZE: GitHubRepository.page_size,
            ListingParameter.PAGE: 1,
        }
    )
    return f"{path}?{query}"


def test_the_client_reads_both_kinds_of_check_on_a_commit():
    below_commit = f"{RepositoryPath.COMMITS}/{A_COMMIT}"
    client = RepositoryAnsweringFromRecordings(
        PullRequestHeadRepository.FORK.value,
        "a-token",
        responses={
            first_page(f"{below_commit}{CommitPath.CHECK_RUNS}"): recorded(
                RecordedCommitChecks.ONE_CHECK_RUN_FAILING
            ),
            f"{below_commit}{CommitPath.STATUS}": recorded(
                RecordedCommitChecks.ONE_STATUS_ERRORING
            ),
        },
    )

    assert client.commit_checks(A_COMMIT) == checks_of(
        RecordedCommitChecks.ONE_CHECK_RUN_FAILING,
        RecordedCommitChecks.ONE_STATUS_ERRORING,
    )


def test_the_client_reads_every_comment_on_a_pull_request():
    number = 7
    bodies = ["first", "second"]
    client = RepositoryAnsweringFromRecordings(
        PullRequestHeadRepository.FORK.value,
        "a-token",
        responses={
            first_page(f"{RepositoryPath.ISSUES}/{number}{IssuePath.COMMENTS}"): [
                {CommentField.BODY: body} for body in bodies
            ]
        },
    )

    assert client.comment_bodies(number) == bodies
