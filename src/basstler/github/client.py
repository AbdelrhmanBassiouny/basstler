"""
Reading and writing GitHub through its REST API.

The reading and the writing halves are declared separately, so a caller that must not
write can be handed a reader and provably cannot.
"""

from __future__ import annotations

import itertools
import json
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from functools import cached_property
from enum import StrEnum
from http import HTTPStatus
from http.client import HTTPResponse
from typing import Any

from basstler.environment import GitHubCredentialVariable
from basstler.github.credential import CredentialProvider, GitHubCredential
from basstler.github.exceptions import (
    GitHubCredentialUnavailableError,
    GitHubCallFailed,
    GitHubRequestFailed,
    GitHubUnreachableError,
)
from basstler.maintenance.constants import GitHubExecutable
from basstler.repository import GitHubAddress

# %% the interface


class HttpMethod(StrEnum):
    """
    The HTTP methods the API is called with.
    """

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class GitHubReader(ABC):
    """
    Reading REST resources.

    A path is relative to the API root, query included, e.g.
    ``repos/<owner>/<name>/pulls?state=open``.
    """

    @abstractmethod
    def get(self, path: str) -> Any:
        """
        :param path: The resource's path.
        :return: The parsed response.
        """

    @abstractmethod
    def get_pages(self, path: str) -> list[Any]:
        """
        :param path: The listing's path, without a page number.
        :return: Each page's parsed response, first page first.
        """


class GitHubAttemptReader(ABC):
    """
    Reading a REST resource that may be refused, such as one that may not exist.
    """

    @abstractmethod
    def attempt_get(self, path: str) -> GitHubResponse:
        """
        Like :meth:`GitHubReader.get`, but a refusal or a call that got no answer is
        returned on the answer instead of raised.
        """


class GitHubWriter(ABC):
    """
    Writing REST resources.
    """

    @abstractmethod
    def attempt_send(
        self, method: HttpMethod, path: str, payload: Mapping[str, Any]
    ) -> GitHubResponse:
        """
        Like :meth:`send`, but a refusal or a call that got no answer is returned on the
        answer instead of raised.
        """

    def send(self, method: HttpMethod, path: str, payload: Mapping[str, Any]) -> Any:
        """
        :param method: How the resource is written.
        :param path: The resource's path.
        :param payload: The JSON body.
        :return: The parsed response, ``None`` when it has no body.
        :raises GitHubRequestFailed: If the API refuses the write.
        :raises GitHubUnreachableError: If the write gets no answer.
        """
        return self.attempt_send(method, path, payload).raise_if_failed()


class GitHubAttemptClient(GitHubAttemptReader, GitHubWriter, ABC):
    """
    Reading and writing REST resources, with a refusal returned on the answer.
    """


class GitHubClient(GitHubReader, GitHubWriter, ABC):
    """
    Reading and writing REST resources.
    """


# %% the implementation


class PageParameter(StrEnum):
    """
    The query parameter a page of a listing is asked for by.
    """

    PAGE = "page"
    """
    Which page to read, counting from one.
    """


class ResponseHeader(StrEnum):
    """
    The response headers the client reads.
    """

    LINK = "Link"
    """
    The links to the listing's other pages.
    """


NEXT_PAGE_RELATION = 'rel="next"'
"""
What a ``Link`` header carries when the listing has a page after this one.
"""


class ErrorResponsePassThrough(urllib.request.HTTPErrorProcessor):
    """
    Hands a response with an error status back like any other, so the client decides
    what a refusal means instead of :mod:`urllib` raising.
    """

    def http_response(
        self, request: urllib.request.Request, response: HTTPResponse
    ) -> HTTPResponse:
        return response

    https_response = http_response


SERVER_ERROR_STATUSES = range(HTTPStatus.INTERNAL_SERVER_ERROR, 600)
"""
Every status of the 5xx class, including those past the ones :class:`HTTPStatus` names.
"""


@dataclass(frozen=True)
class RetryPolicy:
    """
    How often, and after how long, a read that GitHub answered with a server error is
    asked again.
    """

    retries: int = 3
    """
    How many times a read is asked again after the first attempt.
    """

    first_delay: timedelta = timedelta(seconds=1)
    """
    The wait before the first retry.
    """

    delay_factor: float = 2.0
    """
    What each wait is multiplied by to give the next one.
    """

    def delays(self) -> list[timedelta]:
        """
        :return: The wait before each retry, first retry first.
        """
        return [
            self.first_delay * self.delay_factor**retry for retry in range(self.retries)
        ]


@dataclass(frozen=True)
class GitHubResponse:
    """
    One answer from the API.
    """

    body: Any
    """
    The parsed JSON body, ``None`` when it has none.
    """

    has_next_page: bool = False
    """
    Whether the answer is a page of a listing with a page after it.
    """

    failure: GitHubCallFailed | None = None
    """
    Why the call failed, ``None`` when it succeeded.
    """

    @property
    def is_server_error(self) -> bool:
        """
        :return: Whether GitHub answered with a 5xx status, which asking again may clear.
        """
        return (
            isinstance(self.failure, GitHubRequestFailed)
            and self.failure.status in SERVER_ERROR_STATUSES
        )

    def raise_if_failed(self) -> Any:
        """
        :return: :attr:`body`.
        :raises GitHubCallFailed: If the call did not succeed.
        """
        if self.failure is not None:
            raise self.failure
        return self.body


@dataclass(frozen=True)
class GitHubRestClient(GitHubClient, GitHubAttemptClient):
    """
    Plain authenticated HTTPS requests, through the proxy the environment names.

    A listing is read page by page with the ``page`` parameter on the path it was asked
    for. The URL a ``Link`` header names is never followed: GitHub writes it as a
    ``repositories/<id>/`` path, which the cloud session proxy refuses.
    """

    token: str | None = None
    """
    The credential the requests authenticate with; ``None`` reads it, at the first
    request, from the first token variable set, else from ``gh``'s login.
    """

    api_root: str = GitHubAddress.API
    """
    The URL every path is relative to.
    """

    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    """
    When a read answered with a server error is asked again.

    A write is never sent again, since GitHub may have applied it.
    """

    @cached_property
    def credential(self) -> GitHubCredential:
        """
        :return: The token the requests authenticate with, and where it came from.
        :raises GitHubCredentialUnavailableError: If no token was given and neither the
            environment nor ``gh`` has one.
        """
        if self.token:
            return GitHubCredential(self.token, CredentialProvider.CALLER)
        variable = GitHubCredentialVariable.first_set()
        if variable is not None:
            return GitHubCredential(variable.read(), variable)
        executable = shutil.which(GitHubExecutable.COMMAND_LINE)
        if executable is None:
            raise GitHubCredentialUnavailableError(tuple(GitHubCredentialVariable))
        login = subprocess.run(
            [executable, "auth", "token"], capture_output=True, text=True
        )
        if login.returncode != 0 or not login.stdout.strip():
            raise GitHubCredentialUnavailableError(tuple(GitHubCredentialVariable))
        return GitHubCredential(login.stdout.strip(), CredentialProvider.GH_LOGIN)

    def get(self, path: str) -> Any:
        return self.attempt_get(path).raise_if_failed()

    def attempt_get(self, path: str) -> GitHubResponse:
        return self._read(path)

    def get_pages(self, path: str) -> list[Any]:
        pages: list[Any] = []
        for page_number in itertools.count(1):
            response = self._read(self._page_path(path, page_number))
            pages.append(response.raise_if_failed())
            if not response.has_next_page:
                break
        return pages

    def attempt_send(
        self, method: HttpMethod, path: str, payload: Mapping[str, Any]
    ) -> GitHubResponse:
        return self._exchange(method, path, payload)

    @staticmethod
    def _page_path(path: str, page_number: int) -> str:
        """
        :param path: A listing's path.
        :param page_number: The page to ask for, counting from one.
        :return: The path asking for that page.
        """
        parts = urllib.parse.urlsplit(path)
        query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        query.append((PageParameter.PAGE, str(page_number)))
        return urllib.parse.urlunsplit(
            parts._replace(query=urllib.parse.urlencode(query, safe=":"))
        )

    def _read(self, path: str) -> GitHubResponse:
        """
        Read a resource, asking again as :attr:`retry_policy` says while GitHub answers
        with a server error.

        :param path: The path below :attr:`api_root`.
        :return: The last answer.
        """
        response = self._exchange(HttpMethod.GET, path, None)
        for delay in self.retry_policy.delays():
            if not response.is_server_error:
                return response
            time.sleep(delay.total_seconds())
            response = self._exchange(HttpMethod.GET, path, None)
        return response

    def _exchange(
        self, method: HttpMethod, path: str, payload: Mapping[str, Any] | None
    ) -> GitHubResponse:
        """
        Make one authenticated call.

        :param method: The HTTP method.
        :param path: The path below :attr:`api_root`.
        :param payload: The JSON body, ``None`` for a read.
        :return: The answer, carrying the failure when the API answers with an error
            status or does not answer.
        :raises GitHubCredentialUnavailableError: If no token is available.
        """
        request = urllib.request.Request(
            f"{self.api_root}/{path.removeprefix('/')}",
            method=method,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self.credential.token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            },
        )
        opener = urllib.request.build_opener(ErrorResponsePassThrough)
        try:
            with opener.open(request) as response:
                status = response.status
                raw_body = response.read()
                links = response.headers.get(ResponseHeader.LINK) or ""
        except OSError as error:
            return GitHubResponse(
                None, failure=GitHubUnreachableError(method, path, str(error))
            )
        if status >= HTTPStatus.BAD_REQUEST:
            return GitHubResponse(
                None,
                failure=GitHubRequestFailed.for_status(
                    status=status,
                    detail=raw_body.decode(errors="replace"),
                    method=method,
                    path=path,
                    credential_origin=self.credential.origin,
                ),
            )
        return GitHubResponse(
            json.loads(raw_body) if raw_body else None, NEXT_PAGE_RELATION in links
        )
