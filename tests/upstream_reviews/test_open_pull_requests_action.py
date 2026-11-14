"""
Reading the upstream's open pull requests through the fork's Action, for the board.
"""

from __future__ import annotations

import json

import pytest

from basstler.git.commands import GitCommandRunner
from basstler.github.repository_access import GitHubRepository
from basstler.locations import ClaudeCodeVariable
from basstler.maintenance.board import UpstreamPullRequests
from basstler.maintenance.commands import MaintenancePass
from basstler.maintenance.upstream_action import (
    OpenPullRequestsAnswer,
    OpenPullRequestsRequest,
    UpstreamReadRoute,
)
from basstler.upstream_reviews.action.__main__ import ActionCommand, main
from basstler.upstream_reviews.action.branch import ActionFile, ActionInstallation
from basstler.upstream_reviews.action.exchange import (
    ActionRequest,
    ActionRequestKind,
)
from basstler.upstream_reviews.action.read import ActionRead
from basstler.upstream_reviews.exceptions import ActionNotInstalled

from ..maintenance.fork import (
    PullRequestHeadRepository,
    StackBranch,
    StackPullRequestNumber,
    an_api_record,
    make_configuration,
)
from ..maintenance.test_board import ListedRepository
from .test_action import (
    BRANCH_OR_TAG,
    REQUEST_IDENTIFIER,
    UPSTREAM,
    Fork,
    fork,
    sent_long_ago,
)

# %% the request and its answer


def a_request() -> OpenPullRequestsRequest:
    """:return: A request for the upstream's pull requests from the board's fork."""
    return OpenPullRequestsRequest(
        REQUEST_IDENTIFIER, UPSTREAM, PullRequestHeadRepository.FORK.value
    )


def an_upstream() -> ListedRepository:
    """:return: An upstream with one pull request from the fork and one from another."""
    return ListedRepository(
        records=(
            an_api_record(
                number=StackPullRequestNumber.UPSTREAM, head=StackBranch.PARENT
            ),
            an_api_record(
                number=StackPullRequestNumber.CHILD,
                head=StackBranch.CHILD,
                head_repository=PullRequestHeadRepository.ANOTHER_CONTRIBUTORS_FORK.value,
            ),
        )
    )


def test_a_sent_request_names_its_kind_and_reads_back_as_itself():
    sent = a_request().as_sent()

    assert ActionRequest.kind_of(sent) is ActionRequestKind.OPEN_PULL_REQUESTS
    assert OpenPullRequestsRequest.from_json(sent) == a_request()


def test_the_answer_holds_only_the_pull_requests_opened_from_the_fork():
    answer = OpenPullRequestsAnswer.answering(a_request(), an_upstream())

    assert answer.upstream_pull_requests == UpstreamPullRequests(
        PullRequestHeadRepository.FORK.value,
        {StackBranch.PARENT: StackPullRequestNumber.UPSTREAM},
    )


def test_a_committed_answer_reads_back_as_itself():
    answer = OpenPullRequestsAnswer.answering(a_request(), an_upstream())

    assert (
        OpenPullRequestsAnswer.from_json(json.loads(json.dumps(answer.to_json())))
        == answer
    )


# %% the run


def test_the_run_commits_its_answer_onto_the_request_s_branch(
    fork: Fork, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        GitHubRepository,
        "from_environment",
        classmethod(lambda cls, repository: an_upstream()),
    )
    ActionInstallation(BRANCH_OR_TAG).install(fork.branch)
    read = ActionRead(fork.branch, a_request(), answer_type=OpenPullRequestsAnswer)
    read.send()
    request_file = tmp_path / ActionFile.REQUEST
    request_file.write_text(json.dumps(a_request().as_sent()))

    status = main(
        [
            "--project-root",
            str(fork.clone),
            ActionCommand.RUN,
            "--request",
            str(request_file),
        ]
    )

    assert status == 0
    assert read.collect() == OpenPullRequestsAnswer.answering(
        a_request(), an_upstream()
    )


def test_the_run_deletes_abandoned_requests_after_answering(
    fork: Fork, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        GitHubRepository,
        "from_environment",
        classmethod(lambda cls, repository: an_upstream()),
    )
    ActionInstallation(BRANCH_OR_TAG).install(fork.branch)
    abandoned = sent_long_ago(fork, monkeypatch)
    read = ActionRead(fork.branch, a_request(), answer_type=OpenPullRequestsAnswer)
    read.send()
    request_file = tmp_path / ActionFile.REQUEST
    request_file.write_text(json.dumps(a_request().as_sent()))

    main(
        [
            "--project-root",
            str(fork.clone),
            ActionCommand.RUN,
            "--request",
            str(request_file),
        ]
    )

    assert abandoned.request_branch.name not in fork.branches()
    assert read.request_branch.name in fork.branches()


# %% the session's side


def test_the_answer_committed_for_the_request_is_collected(fork: Fork):
    ActionInstallation(BRANCH_OR_TAG).install(fork.branch)
    read = ActionRead(fork.branch, a_request(), answer_type=OpenPullRequestsAnswer)
    read.send()
    answer = OpenPullRequestsAnswer.answering(a_request(), an_upstream())
    fork.answer(answer)

    assert read.wait(timeout=0) == answer


def test_a_pass_reading_through_the_action_asks_the_fork_s_action_branch(fork: Fork):
    maintenance = MaintenancePass(
        configuration=make_configuration(),
        git=GitCommandRunner(fork.clone),
        board=fork.clone / "board.json",
        upstream_read=UpstreamReadRoute.ACTION,
    )

    with pytest.raises(ActionNotInstalled):
        maintenance.upstream_pull_requests()


# %% choosing the route


def test_a_cloud_session_reads_through_the_action(monkeypatch):
    monkeypatch.setenv(ClaudeCodeVariable.REMOTE, "true")

    assert UpstreamReadRoute.for_this_session() is UpstreamReadRoute.ACTION


def test_anywhere_else_reads_directly(monkeypatch):
    monkeypatch.delenv(ClaudeCodeVariable.REMOTE, raising=False)

    assert UpstreamReadRoute.for_this_session() is UpstreamReadRoute.DIRECT
