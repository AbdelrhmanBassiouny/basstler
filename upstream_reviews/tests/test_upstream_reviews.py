"""
Tests for upstream_reviews.py's payload parsing, thread pagination, pull request
resolution, report rendering, and the gh-backed transport.
"""

import json
import os
import shutil
import stat
from enum import StrEnum
from pathlib import Path
from typing import Any

import pytest
from conftest import FixtureName, RecordedCall, ReplayingTransport

from upstream_reviews import (
    GitHubCommandFailed,
    GitHubCommandTransport,
    GraphQLErrorsReturned,
    PayloadKey,
    PullRequestReviewSnapshot,
    QueryVariable,
    Repository,
    ReviewState,
    ThreadMarker,
    UnresolvedThreadReport,
    UpstreamPullRequestNotFound,
    UpstreamReviewReader,
    main,
    resolve_upstream_repository,
)


class Example(StrEnum):
    """
    The identities the recorded payloads were built around.
    """

    UPSTREAM_OWNER = "example-upstream"
    UPSTREAM_NAME = "example-repo"
    FORK_OWNER = "example-fork-owner"
    FOREIGN_OWNER = "another-contributor"
    BRANCH = "some-branch"
    UNPROMOTED_BRANCH = "never-promoted"


class ThreadIdentifier(StrEnum):
    """
    The review threads the recorded payloads carry.
    """

    RESOLVED = "THREAD_RESOLVED"
    UNRESOLVED_MIDDLE = "THREAD_UNRESOLVED_MIDDLE"
    UNRESOLVED_OUTDATED = "THREAD_UNRESOLVED_OUTDATED"


class ThreadCursor(StrEnum):
    """
    The cursors the recorded pages hand back.
    """

    PAGE_ONE = "CURSOR_PAGE_ONE"


class StubEnvironmentVariable(StrEnum):
    """
    The knobs the ``gh`` stub reads.
    """

    GRAPHQL_JSON = "STUB_GH_GRAPHQL_JSON"
    EXIT_CODE = "STUB_GH_EXIT_CODE"
    CALL_LOG = "STUB_GH_CALL_LOG"


UPSTREAM = Repository(Example.UPSTREAM_OWNER, Example.UPSTREAM_NAME)
RECORDED_PULL_REQUEST_NUMBER = 513
GRAPHQL_ERROR_MESSAGE = "Could not resolve to a Repository"
UPSTREAM_SETTING_TEMPLATE = 'upstream_repository = "{repository}"\n'


def make_reader(transport: ReplayingTransport) -> UpstreamReviewReader:
    """
    Build a reader wired to *transport* and the recorded upstream.

    :param transport: The transport to replay payloads from.
    :return: The reader under test.
    """
    return UpstreamReviewReader(transport, UPSTREAM, Example.FORK_OWNER)


def recorded_pull_request(fixture: FixtureName) -> dict[str, Any]:
    """
    Read the ``pullRequest`` node straight out of a recorded payload.

    Lets a test compare parsed values against their recorded source rather than
    restating them as literals.

    :param fixture: The fixture to read.
    :return: The recorded node.
    """
    return fixture.load()[PayloadKey.REPOSITORY][PayloadKey.PULL_REQUEST]


def recorded_thread(
    fixture: FixtureName, identifier: ThreadIdentifier
) -> dict[str, Any]:
    """
    Read one recorded review-thread node by its identifier.

    :param fixture: The fixture to read.
    :param identifier: The thread to find.
    :return: The recorded node.
    :raises KeyError: If the fixture carries no such thread.
    """
    nodes = recorded_pull_request(fixture)[PayloadKey.REVIEW_THREADS][PayloadKey.NODES]
    for node in nodes:
        if node[PayloadKey.IDENTIFIER] == identifier:
            return node
    raise KeyError(identifier)


# %% payload parsing


def test_thread_fields_are_read_from_the_payload(paginated_transport):
    snapshot = make_reader(paginated_transport).read_current_state(
        RECORDED_PULL_REQUEST_NUMBER
    )

    recorded = recorded_thread(
        FixtureName.PULL_REQUEST_PAGE_ONE, ThreadIdentifier.RESOLVED
    )
    parsed = snapshot.thread(ThreadIdentifier.RESOLVED)
    assert parsed.is_resolved is recorded[PayloadKey.IS_RESOLVED]
    assert parsed.path == recorded[PayloadKey.PATH]
    assert parsed.line == recorded[PayloadKey.LINE]
    recorded_comment = recorded[PayloadKey.COMMENTS][PayloadKey.NODES][0]
    assert parsed.comments[0].body == recorded_comment[PayloadKey.BODY]
    assert (
        parsed.comments[0].database_identifier
        == recorded_comment[PayloadKey.DATABASE_IDENTIFIER]
    )
    assert (
        parsed.comments[0].author.login
        == recorded_comment[PayloadKey.AUTHOR][PayloadKey.LOGIN]
    )


def test_the_snapshot_identifies_the_pull_request_it_read(paginated_transport):
    snapshot = make_reader(paginated_transport).read_current_state(
        RECORDED_PULL_REQUEST_NUMBER
    )

    recorded = recorded_pull_request(FixtureName.PULL_REQUEST_PAGE_ONE)
    assert snapshot.number == recorded[PayloadKey.NUMBER]
    assert snapshot.title == recorded[PayloadKey.TITLE]
    assert snapshot.url == recorded[PayloadKey.URL]


def test_a_thread_keeps_every_comment_in_order(paginated_transport):
    snapshot = make_reader(paginated_transport).read_current_state(
        RECORDED_PULL_REQUEST_NUMBER
    )

    recorded = recorded_thread(
        FixtureName.PULL_REQUEST_PAGE_ONE, ThreadIdentifier.UNRESOLVED_MIDDLE
    )
    parsed = snapshot.thread(ThreadIdentifier.UNRESOLVED_MIDDLE)
    assert [comment.author.login for comment in parsed.comments] == [
        comment[PayloadKey.AUTHOR][PayloadKey.LOGIN]
        for comment in recorded[PayloadKey.COMMENTS][PayloadKey.NODES]
    ]


def test_reviews_are_parsed_with_their_state(paginated_transport):
    snapshot = make_reader(paginated_transport).read_current_state(
        RECORDED_PULL_REQUEST_NUMBER
    )

    assert [review.state for review in snapshot.reviews] == [
        ReviewState.CHANGES_REQUESTED,
        ReviewState.COMMENTED,
    ]


def test_a_thread_on_an_outdated_hunk_has_no_line(paginated_transport):
    snapshot = make_reader(paginated_transport).read_current_state(
        RECORDED_PULL_REQUEST_NUMBER
    )

    outdated = snapshot.thread(ThreadIdentifier.UNRESOLVED_OUTDATED)
    assert outdated.markers == [ThreadMarker.OUTDATED]
    assert outdated.line is None
    assert outdated.location == outdated.path


def test_a_thread_anchored_to_a_line_is_located_by_it(paginated_transport):
    snapshot = make_reader(paginated_transport).read_current_state(
        RECORDED_PULL_REQUEST_NUMBER
    )

    anchored = snapshot.thread(ThreadIdentifier.UNRESOLVED_MIDDLE)
    assert anchored.location == f"{anchored.path}:{anchored.line}"


# %% thread pagination


def test_both_pages_are_merged_into_one_snapshot(paginated_transport):
    snapshot = make_reader(paginated_transport).read_current_state(
        RECORDED_PULL_REQUEST_NUMBER
    )

    assert [thread.identifier for thread in snapshot.threads] == [
        ThreadIdentifier.RESOLVED,
        ThreadIdentifier.UNRESOLVED_MIDDLE,
        ThreadIdentifier.UNRESOLVED_OUTDATED,
    ]


def test_the_second_request_carries_the_first_pages_cursor(paginated_transport):
    make_reader(paginated_transport).read_current_state(RECORDED_PULL_REQUEST_NUMBER)

    assert len(paginated_transport.calls) == 2
    assert paginated_transport.calls[0].variables[QueryVariable.THREAD_CURSOR] is None
    assert (
        paginated_transport.calls[1].variables[QueryVariable.THREAD_CURSOR]
        == ThreadCursor.PAGE_ONE
    )


def test_paging_stops_once_a_page_reports_no_successor(paginated_transport):
    make_reader(paginated_transport).read_current_state(RECORDED_PULL_REQUEST_NUMBER)

    assert paginated_transport.payloads == []


# %% resolved filtering


def test_resolved_threads_are_excluded_by_default(paginated_transport):
    snapshot = make_reader(paginated_transport).read_current_state(
        RECORDED_PULL_REQUEST_NUMBER
    )

    assert [thread.identifier for thread in snapshot.unresolved_threads] == [
        ThreadIdentifier.UNRESOLVED_MIDDLE,
        ThreadIdentifier.UNRESOLVED_OUTDATED,
    ]


def test_the_report_omits_a_resolved_thread(paginated_transport):
    snapshot = make_reader(paginated_transport).read_current_state(
        RECORDED_PULL_REQUEST_NUMBER
    )

    report = UnresolvedThreadReport(snapshot)

    assert ThreadIdentifier.RESOLVED not in {
        thread.identifier for thread in report.shown_threads
    }
    assert snapshot.thread(ThreadIdentifier.RESOLVED).comments[0].body not in (
        report.render()
    )


def test_including_resolved_threads_restores_it(paginated_transport):
    snapshot = make_reader(paginated_transport).read_current_state(
        RECORDED_PULL_REQUEST_NUMBER
    )

    rendered = UnresolvedThreadReport(snapshot, include_resolved=True).render()

    assert snapshot.thread(ThreadIdentifier.RESOLVED).comments[0].body in rendered


def test_including_resolved_threads_counts_what_is_shown(paginated_transport):
    snapshot = make_reader(paginated_transport).read_current_state(
        RECORDED_PULL_REQUEST_NUMBER
    )

    report = UnresolvedThreadReport(snapshot, include_resolved=True)

    assert report.heading(len(snapshot.threads)) in report.render()
    assert len(report.shown_threads) == len(snapshot.threads)


# %% pull request resolution


def test_a_branch_resolves_to_the_forks_own_pull_request():
    transport = ReplayingTransport([FixtureName.BRANCH_PULL_REQUESTS.load()])

    number = make_reader(transport).resolve_pull_request_number(Example.BRANCH)

    assert number == RECORDED_PULL_REQUEST_NUMBER


def test_the_branch_name_and_upstream_are_sent_as_variables():
    transport = ReplayingTransport([FixtureName.BRANCH_PULL_REQUESTS.load()])

    make_reader(transport).resolve_pull_request_number(Example.BRANCH)

    assert transport.calls[0].variables == {
        QueryVariable.OWNER: Example.UPSTREAM_OWNER,
        QueryVariable.NAME: Example.UPSTREAM_NAME,
        QueryVariable.HEAD_REF_NAME: Example.BRANCH,
    }


def test_a_branch_of_another_contributor_is_not_claimed():
    transport = ReplayingTransport(
        [FixtureName.BRANCH_PULL_REQUESTS_FOREIGN_OWNER.load()]
    )

    with pytest.raises(UpstreamPullRequestNotFound) as raised:
        make_reader(transport).resolve_pull_request_number(Example.BRANCH)

    assert raised.value.branch == Example.BRANCH
    assert raised.value.fork_owner == Example.FORK_OWNER


def test_a_branch_never_promoted_upstream_is_reported_clearly():
    transport = ReplayingTransport(
        [{PayloadKey.REPOSITORY: {PayloadKey.PULL_REQUESTS: {PayloadKey.NODES: []}}}]
    )

    with pytest.raises(UpstreamPullRequestNotFound) as raised:
        make_reader(transport).resolve_pull_request_number(Example.UNPROMOTED_BRANCH)

    assert raised.value.upstream == UPSTREAM


# %% portability


def test_the_configured_upstream_reaches_the_query():
    transport = ReplayingTransport([FixtureName.BRANCH_PULL_REQUESTS.load()])
    elsewhere = Repository("another-organization", "another-repository")
    reader = UpstreamReviewReader(transport, elsewhere, Example.FOREIGN_OWNER)

    reader.resolve_pull_request_number(Example.BRANCH)

    assert transport.calls[0].variables[QueryVariable.OWNER] == elsewhere.owner
    assert transport.calls[0].variables[QueryVariable.NAME] == elsewhere.name


def test_the_upstream_is_read_from_the_configuration_file(tmp_path):
    configured = Repository("some-organization", "some-repository")
    configuration = tmp_path / "stack.toml"
    configuration.write_text(UPSTREAM_SETTING_TEMPLATE.format(repository=configured))

    assert resolve_upstream_repository(configuration) == configured


def test_an_explicit_override_outranks_the_configuration_file(tmp_path):
    configured = Repository("some-organization", "some-repository")
    overriding = Repository("override-organization", "override-repository")
    configuration = tmp_path / "stack.toml"
    configuration.write_text(UPSTREAM_SETTING_TEMPLATE.format(repository=configured))

    assert resolve_upstream_repository(configuration, str(overriding)) == overriding


# %% report rendering


@pytest.fixture
def current_state(paginated_transport) -> PullRequestReviewSnapshot:
    """:return: The snapshot parsed from both recorded pages."""
    return make_reader(paginated_transport).read_current_state(
        RECORDED_PULL_REQUEST_NUMBER
    )


def test_each_unresolved_thread_is_located_by_file_and_line(current_state):
    rendered = UnresolvedThreadReport(current_state).render()

    for thread in current_state.unresolved_threads:
        assert thread.location in rendered


def test_comment_bodies_are_reproduced(current_state):
    rendered = UnresolvedThreadReport(current_state).render()

    for thread in current_state.unresolved_threads:
        for comment in thread.comments:
            assert comment.body in rendered


def test_each_thread_links_back_to_its_first_comment(current_state):
    rendered = UnresolvedThreadReport(current_state).render()

    for thread in current_state.unresolved_threads:
        assert thread.comments[0].url in rendered


def test_an_outdated_thread_is_marked_as_such(current_state):
    rendered = UnresolvedThreadReport(current_state).render()

    assert ThreadMarker.OUTDATED in rendered


def test_the_unresolved_count_is_stated(current_state):
    report = UnresolvedThreadReport(current_state)

    assert report.heading(len(report.shown_threads)) in report.render()


def test_every_reviewer_and_verdict_is_listed(current_state):
    rendered = UnresolvedThreadReport(current_state).render()

    for review in current_state.reviews:
        assert review.author.login in rendered
        assert review.state.spoken in rendered


def test_a_pull_request_with_nothing_outstanding_says_so(current_state):
    settled = PullRequestReviewSnapshot(
        number=current_state.number,
        title=current_state.title,
        url=current_state.url,
        reviews=current_state.reviews,
        threads=[thread for thread in current_state.threads if thread.is_resolved],
    )

    rendered = UnresolvedThreadReport(settled).render()

    assert UnresolvedThreadReport.NO_UNRESOLVED_HEADING in rendered
    assert UnresolvedThreadReport.NOTHING_TO_ACT_ON in rendered


# %% gh transport


@pytest.fixture
def stubbed_gh(tmp_path, monkeypatch) -> Path:
    """
    Put the ``gh`` stub first on ``PATH``.

    :param tmp_path: pytest's per-test temporary directory.
    :param monkeypatch: The fixture used to prepend the stub directory.
    :return: The directory the stub was installed into.
    """
    stub_directory = tmp_path / "bin"
    stub_directory.mkdir()
    installed = stub_directory / "gh"
    shutil.copy(Path(__file__).parent / "stubs" / "gh.sh", installed)
    installed.chmod(installed.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{stub_directory}{os.pathsep}{os.environ['PATH']}")
    return stub_directory


def test_the_data_payload_is_unwrapped(stubbed_gh, monkeypatch):
    payload = {PayloadKey.REPOSITORY: None}
    monkeypatch.setenv(
        StubEnvironmentVariable.GRAPHQL_JSON, json.dumps({PayloadKey.DATA: payload})
    )

    assert GitHubCommandTransport().execute("query {}", {}) == payload


def test_the_query_and_variables_are_sent_as_the_request_body(
    stubbed_gh, monkeypatch, tmp_path
):
    call_log = tmp_path / "calls.txt"
    monkeypatch.setenv(StubEnvironmentVariable.CALL_LOG, str(call_log))
    monkeypatch.setenv(
        StubEnvironmentVariable.GRAPHQL_JSON, json.dumps({PayloadKey.DATA: {}})
    )
    sent = RecordedCall("query Example {}", {QueryVariable.NUMBER: 513})

    GitHubCommandTransport().execute(sent.query, sent.variables)

    assert json.loads(call_log.read_text()) == {
        PayloadKey.QUERY: sent.query,
        PayloadKey.VARIABLES: sent.variables,
    }


def test_a_failing_gh_invocation_is_raised(stubbed_gh, monkeypatch):
    monkeypatch.setenv(StubEnvironmentVariable.EXIT_CODE, "1")

    with pytest.raises(GitHubCommandFailed) as raised:
        GitHubCommandTransport().execute("query {}", {})

    assert raised.value.exit_code == 1


def test_graphql_errors_are_raised_rather_than_returned(stubbed_gh, monkeypatch):
    monkeypatch.setenv(
        StubEnvironmentVariable.GRAPHQL_JSON,
        json.dumps({PayloadKey.ERRORS: [{PayloadKey.MESSAGE: GRAPHQL_ERROR_MESSAGE}]}),
    )

    with pytest.raises(GraphQLErrorsReturned) as raised:
        GitHubCommandTransport().execute("query {}", {})

    assert raised.value.messages == [GRAPHQL_ERROR_MESSAGE]


def test_a_branch_without_an_upstream_pull_request_exits_without_a_traceback(
    stubbed_gh, monkeypatch, capsys
):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setenv(
        StubEnvironmentVariable.GRAPHQL_JSON,
        json.dumps(
            {
                PayloadKey.DATA: {
                    PayloadKey.REPOSITORY: {
                        PayloadKey.PULL_REQUESTS: {PayloadKey.NODES: []}
                    }
                }
            }
        ),
    )

    status = main(
        [
            "--branch",
            str(Example.UNPROMOTED_BRANCH),
            "--fork-owner",
            str(Example.FORK_OWNER),
            "--upstream",
            str(UPSTREAM),
        ]
    )

    assert status == 1
    assert str(Example.UNPROMOTED_BRANCH) in capsys.readouterr().err
