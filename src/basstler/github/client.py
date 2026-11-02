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
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cached_property
from enum import StrEnum
from http import HTTPStatus
from http.client import HTTPResponse
from typing import Any

from basstler.environment import GitHubCredentialVariable
from basstler.github.exceptions import (
    GitHubCredentialUnavailableError,
    GitHubRequestFailed,
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


class GitHubWriter(ABC):
    """
    Writing REST resources.
    """

    @abstractmethod
    def send(self, method: HttpMethod, path: str, payload: Mapping[str, Any]) -> Any:
        """
        :param method: How the resource is written.
        :param path: The resource's path.
        :param payload: The JSON body.
        :return: The parsed response, ``None`` when it has no body.
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


@dataclass(frozen=True)
class GitHubResponse:
    """
    One answer from the API.
    """

    body: Any
    """
    The parsed JSON body, ``None`` when it has none.
    """

    has_next_page: bool
    """
    Whether the answer is a page of a listing with a page after it.
    """


@dataclass(frozen=True)
class GitHubRestClient(GitHubClient):
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

    @cached_property
    def credential(self) -> str:
        """
        :return: The token the requests authenticate with.
        :raises GitHubCredentialUnavailableError: If no token was given and neither the
            environment nor ``gh`` has one.
        """
        token = self.token or GitHubCredentialVariable.first_token()
        if token:
            return token
        executable = shutil.which(GitHubExecutable.COMMAND_LINE)
        if executable is None:
            raise GitHubCredentialUnavailableError(tuple(GitHubCredentialVariable))
        login = subprocess.run(
            [executable, "auth", "token"], capture_output=True, text=True
        )
        if login.returncode != 0 or not login.stdout.strip():
            raise GitHubCredentialUnavailableError(tuple(GitHubCredentialVariable))
        return login.stdout.strip()

    def get(self, path: str) -> Any:
        return self._exchange(HttpMethod.GET, path, None).body

    def get_pages(self, path: str) -> list[Any]:
        pages: list[Any] = []
        for page_number in itertools.count(1):
            response = self._exchange(
                HttpMethod.GET, self._page_path(path, page_number), None
            )
            pages.append(response.body)
            if not response.has_next_page:
                break
        return pages

    def send(self, method: HttpMethod, path: str, payload: Mapping[str, Any]) -> Any:
        return self._exchange(method, path, payload).body

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

    def _exchange(
        self, method: HttpMethod, path: str, payload: Mapping[str, Any] | None
    ) -> GitHubResponse:
        """
        Make one authenticated call.

        :param method: The HTTP method.
        :param path: The path below :attr:`api_root`.
        :param payload: The JSON body, ``None`` for a read.
        :return: The answer.
        :raises GitHubRequestFailed: If the API answers with an error status.
        :raises GitHubCredentialUnavailableError: If no token is available.
        """
        request = urllib.request.Request(
            f"{self.api_root}/{path.removeprefix('/')}",
            method=method,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self.credential}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            },
        )
        opener = urllib.request.build_opener(ErrorResponsePassThrough)
        with opener.open(request) as response:
            raw_body = response.read()
            if response.status >= HTTPStatus.BAD_REQUEST:
                raise GitHubRequestFailed(
                    status=response.status,
                    detail=raw_body.decode(errors="replace"),
                    method=method,
                    path=path,
                )
            return GitHubResponse(
                json.loads(raw_body) if raw_body else None,
                NEXT_PAGE_RELATION in (response.headers.get(ResponseHeader.LINK) or ""),
            )
