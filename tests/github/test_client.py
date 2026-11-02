"""
Tests for the owned GitHub REST client: authentication, paging by page number, writes,
refusals and where its credential comes from.
"""

from __future__ import annotations

from enum import StrEnum
from http import HTTPStatus

import pytest

from basstler.environment import GitHubCredentialVariable
from basstler.github.client import GitHubRestClient, HttpMethod
from basstler.github.exceptions import (
    GitHubCredentialUnavailableError,
    GitHubRequestFailed,
    GitHubUnreachableError,
)
from basstler.maintenance.constants import GitHubExecutable

from ..constants.environment import SearchPathVariable
from .api_stand_in import CannedResponse, ReceivedRequest, RecordingApiServer

TOKEN = "example-token"
LISTING = "/repos/example-owner/example-repo/pulls?state=open&per_page=2"


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
    api_server.responses["GET /repos/example-owner/example-repo/pulls/7"] = (
        CannedResponse(body)
    )

    assert client.get("repos/example-owner/example-repo/pulls/7") == body


def test_paging_asks_for_each_page_by_number_until_no_next_page_is_linked(
    api_server, client
):
    first, second = [{"number": 1}, {"number": 2}], [{"number": 3}]
    api_server.responses[f"GET {LISTING}&page=1"] = CannedResponse(
        first, next_page_link=True
    )
    api_server.responses[f"GET {LISTING}&page=2"] = CannedResponse(second)

    assert client.get_pages(LISTING) == [first, second]
    assert [request.target for request in api_server.requests] == [
        f"{LISTING}&page=1",
        f"{LISTING}&page=2",
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
    payload = {"body": "a comment"}
    created = {"html_url": "https://github.com/o/r/pull/1#issuecomment-1"}
    api_server.responses["POST /repos/o/r/issues/1/comments"] = CannedResponse(
        created, HTTPStatus.CREATED
    )

    assert client.send(HttpMethod.POST, "/repos/o/r/issues/1/comments", payload) == (
        created
    )
    assert api_server.requests[0].body == payload


def test_a_write_answered_with_no_content_returns_none(api_server, client):
    api_server.responses["PUT /repos/o/r/labels"] = CannedResponse(
        None, HTTPStatus.NO_CONTENT
    )

    assert client.send(HttpMethod.PUT, "/repos/o/r/labels", {}) is None


# %% refusals


def test_a_refused_call_raises_with_its_status_and_request_line(api_server, client):
    with pytest.raises(GitHubRequestFailed) as refused:
        client.get("/repos/o/r/pulls/404")

    assert (refused.value.status, refused.value.method, refused.value.path) == (
        HTTPStatus.NOT_FOUND,
        HttpMethod.GET,
        "/repos/o/r/pulls/404",
    )


# %% the credential


def test_a_write_that_gets_no_answer_carries_why_instead_of_raising():
    with RecordingApiServer().serving() as stopped_server:
        root = stopped_server.root
    client = GitHubRestClient(TOKEN, api_root=root)

    response = client.attempt_send(HttpMethod.POST, "/user", {})

    assert type(response.failure) is GitHubUnreachableError
    assert (response.failure.method, response.failure.path) == (
        HttpMethod.POST,
        "/user",
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
    monkeypatch.setenv(GitHubCredentialVariable.GITHUB_TOKEN, TOKEN)

    assert GitHubRestClient().credential == TOKEN


def test_with_no_token_variable_the_credential_comes_from_gh(
    monkeypatch, no_token_variables, stub_bin
):
    stub_bin.install(GitHubExecutable.COMMAND_LINE)
    monkeypatch.setenv(SearchPathVariable.EXECUTABLE_SEARCH_PATH, str(stub_bin.path))
    monkeypatch.setenv(StubEnvironmentVariable.AUTH_TOKEN, TOKEN)

    assert GitHubRestClient().credential == TOKEN


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
