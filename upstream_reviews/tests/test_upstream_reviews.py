"""
Tests for upstream_reviews.py's payload parsing, thread pagination, pull request
resolution, report rendering, and the gh-backed transport.
"""

import json
import os
import shutil
import stat
from pathlib import Path

import pytest
from conftest import ReplayingTransport, load_fixture

from upstream_reviews import (
    GitHubCommandFailed,
    GitHubCommandTransport,
    PullRequestReviewSnapshot,
    Repository,
    ReviewState,
    UnresolvedThreadReport,
    UpstreamPullRequestNotFound,
    UpstreamReviewReader,
    main,
    resolve_upstream_repository,
)

UPSTREAM = Repository("example-upstream", "example-repo")
FORK_OWNER = "example-fork-owner"


def make_reader(transport: ReplayingTransport) -> UpstreamReviewReader:
    """
    Build a reader wired to *transport* and the tests' fixed upstream.

    :param transport: The transport to replay payloads from.
    :return: The reader under test.
    """
    return UpstreamReviewReader(transport, UPSTREAM, FORK_OWNER)


# %% payload parsing


def test_thread_fields_are_read_from_the_payload(paginated_transport):
    snapshot = make_reader(paginated_transport).snapshot(513)

    assert snapshot.number == 513
    assert snapshot.url == "https://github.com/example-upstream/example-repo/pull/513"
    resolved = snapshot.thread("THREAD_RESOLVED")
    assert resolved.is_resolved is True
    assert resolved.path == ".claude/stack/maintenance.py"
    assert resolved.line == 1031
    assert [comment.body for comment in resolved.comments] == ["doc formatting"]
    assert resolved.comments[0].database_id == 3728009027
    assert resolved.comments[0].author == "first-reviewer"


def test_a_thread_keeps_every_comment_in_order(paginated_transport):
    snapshot = make_reader(paginated_transport).snapshot(513)

    thread = snapshot.thread("THREAD_UNRESOLVED_MIDDLE")
    assert [comment.author for comment in thread.comments] == [
        "first-reviewer",
        "pull-request-author",
    ]


def test_reviews_are_parsed_with_their_state(paginated_transport):
    snapshot = make_reader(paginated_transport).snapshot(513)

    assert [(review.author, review.state) for review in snapshot.reviews] == [
        ("first-reviewer", ReviewState.CHANGES_REQUESTED),
        ("second-reviewer", ReviewState.COMMENTED),
    ]


def test_a_thread_on_an_outdated_hunk_has_no_line(paginated_transport):
    snapshot = make_reader(paginated_transport).snapshot(513)

    outdated = snapshot.thread("THREAD_UNRESOLVED_OUTDATED")
    assert outdated.is_outdated is True
    assert outdated.line is None
    assert outdated.location == ".claude/stack/maintenance.py"


# %% thread pagination


def test_both_pages_are_merged_into_one_snapshot(paginated_transport):
    snapshot = make_reader(paginated_transport).snapshot(513)

    assert [thread.identifier for thread in snapshot.threads] == [
        "THREAD_RESOLVED",
        "THREAD_UNRESOLVED_MIDDLE",
        "THREAD_UNRESOLVED_OUTDATED",
    ]


def test_the_second_request_carries_the_first_pages_cursor(paginated_transport):
    make_reader(paginated_transport).snapshot(513)

    assert len(paginated_transport.calls) == 2
    assert paginated_transport.calls[0][1]["threadCursor"] is None
    assert paginated_transport.calls[1][1]["threadCursor"] == "CURSOR_PAGE_ONE"


def test_paging_stops_once_a_page_reports_no_successor(paginated_transport):
    make_reader(paginated_transport).snapshot(513)

    assert paginated_transport.payloads == []


# %% resolved filtering


def test_resolved_threads_are_excluded_by_default(paginated_transport):
    snapshot = make_reader(paginated_transport).snapshot(513)

    assert [thread.identifier for thread in snapshot.unresolved_threads] == [
        "THREAD_UNRESOLVED_MIDDLE",
        "THREAD_UNRESOLVED_OUTDATED",
    ]


def test_the_report_omits_a_resolved_thread(paginated_transport):
    snapshot = make_reader(paginated_transport).snapshot(513)

    assert "doc formatting" not in UnresolvedThreadReport(snapshot).render()


def test_including_resolved_threads_restores_it(paginated_transport):
    snapshot = make_reader(paginated_transport).snapshot(513)

    rendered = UnresolvedThreadReport(snapshot, include_resolved=True).render()

    assert "doc formatting" in rendered


def test_including_resolved_threads_counts_what_is_shown(paginated_transport):
    snapshot = make_reader(paginated_transport).snapshot(513)

    rendered = UnresolvedThreadReport(snapshot, include_resolved=True).render()

    assert "## 3 review threads, 2 unresolved" in rendered


# %% pull request resolution


def test_a_branch_resolves_to_the_forks_own_pull_request():
    transport = ReplayingTransport([load_fixture("branch_pull_requests")])

    number = make_reader(transport).resolve_pull_request_number("some-branch")

    assert number == 513


def test_the_branch_name_and_upstream_are_sent_as_variables():
    transport = ReplayingTransport([load_fixture("branch_pull_requests")])

    make_reader(transport).resolve_pull_request_number("some-branch")

    assert transport.calls[0][1] == {
        "owner": "example-upstream",
        "name": "example-repo",
        "headRefName": "some-branch",
    }


def test_a_branch_of_another_contributor_is_not_claimed():
    transport = ReplayingTransport([load_fixture("branch_pull_requests_foreign_owner")])

    with pytest.raises(UpstreamPullRequestNotFound) as raised:
        make_reader(transport).resolve_pull_request_number("some-branch")

    assert "some-branch" in str(raised.value)


def test_a_branch_never_promoted_upstream_is_reported_clearly():
    transport = ReplayingTransport([{"repository": {"pullRequests": {"nodes": []}}}])

    with pytest.raises(UpstreamPullRequestNotFound):
        make_reader(transport).resolve_pull_request_number("never-promoted")


# %% portability


def test_the_configured_upstream_reaches_the_query():
    transport = ReplayingTransport([load_fixture("branch_pull_requests")])
    reader = UpstreamReviewReader(
        transport, Repository("another-org", "another-repo"), "another-owner"
    )

    with pytest.raises(UpstreamPullRequestNotFound):
        reader.resolve_pull_request_number("some-branch")

    assert transport.calls[0][1]["owner"] == "another-org"
    assert transport.calls[0][1]["name"] == "another-repo"


def test_the_upstream_is_read_from_the_configuration_file(tmp_path):
    configuration = tmp_path / "stack.toml"
    configuration.write_text('upstream_repository = "some-org/some-repo"\n')

    assert resolve_upstream_repository(configuration) == Repository(
        "some-org", "some-repo"
    )


def test_an_explicit_override_outranks_the_configuration_file(tmp_path):
    configuration = tmp_path / "stack.toml"
    configuration.write_text('upstream_repository = "some-org/some-repo"\n')

    resolved = resolve_upstream_repository(configuration, "override-org/override-repo")

    assert resolved == Repository("override-org", "override-repo")


# %% report rendering


@pytest.fixture
def snapshot(paginated_transport):
    """:return: The snapshot parsed from both recorded pages."""
    return make_reader(paginated_transport).snapshot(513)


def test_each_unresolved_thread_is_located_by_file_and_line(snapshot):
    assert (
        ".claude/stack/maintenance.py:506" in UnresolvedThreadReport(snapshot).render()
    )


def test_comment_bodies_are_reproduced(snapshot):
    rendered = UnresolvedThreadReport(snapshot).render()

    assert (
        "i think its a bit weird to have this randomly in the middle of the file"
        in rendered
    )


def test_each_thread_links_back_to_its_first_comment(snapshot):
    rendered = UnresolvedThreadReport(snapshot).render()

    assert (
        "https://github.com/example-upstream/example-repo/pull/513#discussion_r3727247950"
        in rendered
    )


def test_an_outdated_thread_is_marked_as_such(snapshot):
    assert "outdated" in UnresolvedThreadReport(snapshot).render().lower()


def test_the_unresolved_count_is_stated(snapshot):
    rendered = UnresolvedThreadReport(snapshot).render()

    assert str(len(snapshot.unresolved_threads)) in rendered


def test_a_pull_request_with_nothing_outstanding_says_so(snapshot):
    settled = PullRequestReviewSnapshot(
        number=snapshot.number,
        title=snapshot.title,
        url=snapshot.url,
        reviews=snapshot.reviews,
        threads=[thread for thread in snapshot.threads if thread.is_resolved],
    )

    assert "No unresolved review threads" in UnresolvedThreadReport(settled).render()


# %% gh transport


@pytest.fixture
def stubbed_gh(tmp_path, monkeypatch):
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
    monkeypatch.setenv(
        "STUB_GH_GRAPHQL_JSON", json.dumps({"data": {"repository": None}})
    )

    assert GitHubCommandTransport().execute("query {}", {}) == {"repository": None}


def test_the_query_and_variables_are_sent_as_the_request_body(
    stubbed_gh, monkeypatch, tmp_path
):
    call_log = tmp_path / "calls.txt"
    monkeypatch.setenv("STUB_GH_CALL_LOG", str(call_log))
    monkeypatch.setenv("STUB_GH_GRAPHQL_JSON", json.dumps({"data": {}}))

    GitHubCommandTransport().execute("query Example {}", {"number": 513})

    assert json.loads(call_log.read_text()) == {
        "query": "query Example {}",
        "variables": {"number": 513},
    }


def test_a_failing_gh_invocation_is_raised(stubbed_gh, monkeypatch):
    monkeypatch.setenv("STUB_GH_EXIT_CODE", "1")

    with pytest.raises(GitHubCommandFailed):
        GitHubCommandTransport().execute("query {}", {})


def test_a_branch_without_an_upstream_pull_request_exits_without_a_traceback(
    stubbed_gh, monkeypatch, capsys
):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setenv(
        "STUB_GH_GRAPHQL_JSON",
        json.dumps({"data": {"repository": {"pullRequests": {"nodes": []}}}}),
    )

    status = main(
        [
            "--branch",
            "never-promoted",
            "--fork-owner",
            "someone",
            "--upstream",
            "some-org/some-repo",
        ]
    )

    assert status == 1
    assert "not been promoted upstream" in capsys.readouterr().err


def test_graphql_errors_are_raised_rather_than_returned(stubbed_gh, monkeypatch):
    monkeypatch.setenv(
        "STUB_GH_GRAPHQL_JSON",
        json.dumps({"errors": [{"message": "Could not resolve to a Repository"}]}),
    )

    with pytest.raises(GitHubCommandFailed) as raised:
        GitHubCommandTransport().execute("query {}", {})

    assert "Could not resolve to a Repository" in str(raised.value)
