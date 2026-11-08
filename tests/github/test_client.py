"""
Tests for the owned GitHub REST client: authentication, paging by page number, writes,
refusals and where its credential comes from.
"""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum
from http import HTTPStatus

import pytest

from basstler.environment import GitHubCredentialVariable
from basstler.github.client import GitHubRestClient, HttpMethod, RetryPolicy
from basstler.github.credential import (
    CredentialOrigin,
    CredentialProvider,
    GitHubCredential,
)
from basstler.github.issue import IssueComment
from basstler.github.label import LabelReplacement
from basstler.github.exceptions import (
    GitHubCredentialRejected,
    GitHubCredentialUnavailableError,
    GitHubRepositoryMoved,
    GitHubRequestFailed,
    GitHubUnreachableError,
)
from basstler.maintenance.constants import GitHubExecutable
from basstler.repository import Repository

from ..constants.environment import SearchPathVariable
from .api_stand_in import (
    CannedResponse,
    ReceivedRequest,
    RecordingApiServer,
    RequestLine,
)

TOKEN = "example-token"
REPOSITORY = Repository("example-owner", "example-repo")
LISTING = RequestLine.get(f"/{REPOSITORY.api_path}/pulls?state=open&per_page=2")
USER = RequestLine.get("/user")
MISSING_PULL_REQUEST_PATH = f"/{REPOSITORY.pull_request_path(404)}"
COMMENT = IssueComment(REPOSITORY, 1, "a comment")
COMMENTS = RequestLine(COMMENT.method, f"/{COMMENT.path}")
MOVED = CannedResponse(
    {
        "message": "Moved Permanently",
        "url": "https://api.github.com/repositories/1/pulls",
    },
    HTTPStatus.MOVED_PERMANENTLY,
)
"""
What GitHub answers a path naming a repository by the name it had before it moved.
"""


class StubEnvironmentVariable(StrEnum):
    """
    The knob the ``gh`` stub reads for ``gh auth token``.
    """

    AUTH_TOKEN = "STUB_GH_AUTH_TOKEN"


# %% fixtures


@pytest.fixture
def api_server():
    with RecordingApiServer().serving() as server:
        yield server


@pytest.fixture
def client(api_server):
    return GitHubRestClient(TOKEN, api_root=api_server.root)


# %% reading


def test_a_read_authenticates_with_the_token_and_returns_the_body(api_server, client):
    body = {"login": "example-login"}
    api_server.responses["GET /user"] = CannedResponse(body)

    assert client.get("/user") == body
    assert api_server.requests == [
        ReceivedRequest(HttpMethod.GET, "/user", f"Bearer {TOKEN}", None)
    ]


def test_a_path_without_a_leading_slash_reads_the_same_resource(api_server, client):
    body = {"number": 7}
    api_server.responses[
        str(RequestLine.get(f"/{REPOSITORY.pull_request_path(7)}"))
    ] = CannedResponse(body)

    assert client.get(REPOSITORY.pull_request_path(7)) == body


def test_paging_asks_for_each_page_by_number_until_no_next_page_is_linked(
    api_server, client
):
    first, second = [{"number": 1}, {"number": 2}], [{"number": 3}]
    api_server.responses[str(LISTING.page(1))] = CannedResponse(
        first, next_page_link=True
    )
    api_server.responses[str(LISTING.page(2))] = CannedResponse(second)

    assert client.get_pages(LISTING.target) == [first, second]
    assert [request.target for request in api_server.requests] == [
        LISTING.page(1).target,
        LISTING.page(2).target,
    ]


def test_paging_a_path_with_no_query_adds_the_page_as_the_only_parameter(
    api_server, client
):
    page = {"total_count": 0, "check_runs": []}
    api_server.responses["GET /repos/o/r/commits/abc/check-runs?page=1"] = (
        CannedResponse(page)
    )

    assert client.get_pages("/repos/o/r/commits/abc/check-runs") == [page]


# %% writing


def test_a_write_sends_its_payload_and_returns_the_body(api_server, client):
    created = {"html_url": "https://github.com/o/r/pull/1#issuecomment-1"}
    api_server.responses[str(COMMENTS)] = CannedResponse(created, HTTPStatus.CREATED)

    assert client.send(COMMENT) == created
    assert api_server.requests[0].body == COMMENT.to_json()


def test_a_write_is_sent_with_its_own_method_to_its_own_path(api_server, client):
    """
    The write alone decides where it goes and how.
    """
    api_server.responses[str(COMMENTS)] = CannedResponse({}, HTTPStatus.CREATED)

    client.send(COMMENT)

    received = api_server.requests[0]
    assert (received.method, received.target) == (COMMENTS.method, COMMENTS.target)


def test_a_write_answered_with_no_content_returns_none(api_server, client):
    replacement = LabelReplacement(REPOSITORY, 1, [])
    api_server.responses[f"{replacement.method} /{replacement.path}"] = CannedResponse(
        None, HTTPStatus.NO_CONTENT
    )

    assert client.send(replacement) is None


# %% asking again after a server error


@pytest.fixture
def quick_client(api_server):
    """
    :return: A client that asks again without waiting between the attempts.
    """
    return GitHubRestClient(
        TOKEN,
        api_root=api_server.root,
        retry_policy=RetryPolicy(first_delay=timedelta(0)),
    )


def test_a_read_answered_with_a_server_error_is_asked_again(api_server, quick_client):
    body = {"state": "pending"}
    api_server.queued_responses[str(USER)] = [CannedResponse.bad_gateway()]
    api_server.responses[str(USER)] = CannedResponse(body)

    assert quick_client.get(USER.target) == body
    assert len(api_server.requests) == 2


def test_a_page_answered_with_a_server_error_is_asked_again(api_server, quick_client):
    page = [{"number": 1}]
    first_page = LISTING.page(1)
    api_server.queued_responses[str(first_page)] = [CannedResponse.bad_gateway()]
    api_server.responses[str(first_page)] = CannedResponse(page)

    assert quick_client.get_pages(LISTING.target) == [page]


def test_a_read_that_keeps_failing_is_asked_again_only_as_often_as_the_policy_allows(
    api_server, quick_client
):
    api_server.responses[str(USER)] = CannedResponse.bad_gateway()

    with pytest.raises(GitHubRequestFailed) as refused:
        quick_client.get(USER.target)

    assert refused.value.status == HTTPStatus.BAD_GATEWAY
    assert len(api_server.requests) == 1 + quick_client.retry_policy.retries


def test_a_refusal_that_is_not_a_server_error_is_not_asked_again(
    api_server, quick_client
):
    with pytest.raises(GitHubRequestFailed):
        quick_client.get(MISSING_PULL_REQUEST_PATH)

    assert len(api_server.requests) == 1


def test_a_write_answered_with_a_server_error_is_not_sent_again(
    api_server, quick_client
):
    api_server.responses[str(COMMENTS)] = CannedResponse.bad_gateway()

    response = quick_client.attempt_send(COMMENT)

    assert response.failure.status == HTTPStatus.BAD_GATEWAY
    assert len(api_server.requests) == 1


def test_the_wait_between_attempts_grows_by_the_policys_factor():
    policy = RetryPolicy(retries=3, first_delay=timedelta(seconds=1), delay_factor=2.0)

    assert policy.delays() == [
        timedelta(seconds=1),
        timedelta(seconds=2),
        timedelta(seconds=4),
    ]


# %% refusals


def test_a_refused_call_raises_with_its_status_and_request_line(api_server, client):
    with pytest.raises(GitHubRequestFailed) as refused:
        client.get(MISSING_PULL_REQUEST_PATH)

    assert (refused.value.status, refused.value.method, refused.value.path) == (
        HTTPStatus.NOT_FOUND,
        HttpMethod.GET,
        MISSING_PULL_REQUEST_PATH,
    )


def test_a_rejected_credential_is_its_own_failure(api_server, client):
    """
    A 401 is a :class:`GitHubCredentialRejected`, not only a refused call.
    """
    api_server.responses["GET /user"] = CannedResponse(
        None, status=HTTPStatus.UNAUTHORIZED
    )

    with pytest.raises(GitHubCredentialRejected):
        client.get("/user")


def test_a_read_of_a_moved_repository_raises_that_it_moved(api_server, client):
    api_server.responses[str(LISTING)] = MOVED

    with pytest.raises(GitHubRepositoryMoved):
        client.get(LISTING.target)


def test_a_listing_of_a_moved_repository_raises_that_it_moved(api_server, client):
    api_server.responses[str(LISTING.page(1))] = MOVED

    with pytest.raises(GitHubRepositoryMoved):
        client.get_pages(LISTING.target)


def test_a_refusal_names_a_given_credential(client):
    """
    A refusal of a client given its token says the request used that token.
    """
    response = client.attempt_get(MISSING_PULL_REQUEST_PATH)

    assert response.failure.credential_origin is CredentialProvider.CALLER


def test_a_refusal_names_the_variable_the_credential_came_from(
    monkeypatch, no_token_variables, api_server
):
    """
    A refusal says which variable held the token the request used.
    """
    monkeypatch.setenv(GitHubCredentialVariable.GH_TOKEN, TOKEN)
    client = GitHubRestClient(api_root=api_server.root)

    response = client.attempt_get(MISSING_PULL_REQUEST_PATH)

    assert response.failure.credential_origin is GitHubCredentialVariable.GH_TOKEN


@pytest.mark.parametrize(
    "origin",
    [*GitHubCredentialVariable, *CredentialProvider],
)
def test_every_place_a_token_comes_from_is_a_credential_origin(origin):
    """
    Variables and the other providers are all origins a refusal can name.
    """
    assert isinstance(origin, CredentialOrigin)


def test_a_rejected_token_from_a_variable_suggests_setting_that_variable(
    monkeypatch, no_token_variables, api_server
):
    """
    A rejected token read from a variable is renewed by setting that variable.
    """
    monkeypatch.setenv(GitHubCredentialVariable.GH_TOKEN, TOKEN)
    api_server.responses["GET /user"] = CannedResponse(
        None, status=HTTPStatus.UNAUTHORIZED
    )

    response = GitHubRestClient(api_root=api_server.root).attempt_get("/user")

    assert GitHubCredentialVariable.GH_TOKEN in response.failure.suggest_correction()


# %% the credential


def test_a_write_that_gets_no_answer_carries_why_instead_of_raising():
    with RecordingApiServer().serving() as stopped_server:
        root = stopped_server.root
    client = GitHubRestClient(TOKEN, api_root=root)

    response = client.attempt_send(COMMENT)

    assert type(response.failure) is GitHubUnreachableError
    assert (response.failure.method, response.failure.path) == (
        COMMENT.method,
        COMMENT.path,
    )


def test_a_read_that_gets_no_answer_raises():
    with RecordingApiServer().serving() as stopped_server:
        root = stopped_server.root

    with pytest.raises(GitHubUnreachableError):
        GitHubRestClient(TOKEN, api_root=root).get("/user")


@pytest.fixture
def no_token_variables(monkeypatch):
    for variable in GitHubCredentialVariable:
        monkeypatch.delenv(variable, raising=False)


def test_the_credential_comes_from_the_first_token_variable_set(
    monkeypatch, no_token_variables
):
    """
    The credential is the first token variable set, and names that variable.
    """
    monkeypatch.setenv(GitHubCredentialVariable.GITHUB_TOKEN, TOKEN)

    assert GitHubRestClient().credential == GitHubCredential(
        TOKEN, GitHubCredentialVariable.GITHUB_TOKEN
    )


def test_with_no_token_variable_the_credential_comes_from_gh(
    monkeypatch, no_token_variables, stub_bin
):
    """
    Without a token variable, the credential is gh's login.
    """
    stub_bin.install(GitHubExecutable.COMMAND_LINE)
    monkeypatch.setenv(SearchPathVariable.EXECUTABLE_SEARCH_PATH, str(stub_bin.path))
    monkeypatch.setenv(StubEnvironmentVariable.AUTH_TOKEN, TOKEN)

    assert GitHubRestClient().credential == GitHubCredential(
        TOKEN, CredentialProvider.GH_LOGIN
    )


def test_with_no_token_variable_and_gh_logged_out_there_is_no_credential(
    monkeypatch, no_token_variables, stub_bin
):
    stub_bin.install(GitHubExecutable.COMMAND_LINE)
    monkeypatch.setenv(SearchPathVariable.EXECUTABLE_SEARCH_PATH, str(stub_bin.path))
    monkeypatch.delenv(StubEnvironmentVariable.AUTH_TOKEN, raising=False)

    with pytest.raises(GitHubCredentialUnavailableError):
        GitHubRestClient().credential


def test_with_no_token_variable_and_no_gh_there_is_no_credential(
    monkeypatch, no_token_variables, tmp_path
):
    monkeypatch.setenv(SearchPathVariable.EXECUTABLE_SEARCH_PATH, str(tmp_path))

    with pytest.raises(GitHubCredentialUnavailableError):
        GitHubRestClient().credential


def test_a_client_is_built_with_no_credential_and_asks_for_one_at_its_first_request(
    monkeypatch, no_token_variables, tmp_path, api_server
):
    monkeypatch.setenv(SearchPathVariable.EXECUTABLE_SEARCH_PATH, str(tmp_path))
    client = GitHubRestClient(api_root=api_server.root)

    with pytest.raises(GitHubCredentialUnavailableError):
        client.get("/user")
    assert api_server.requests == []
