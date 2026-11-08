"""
A GitHub client answering from recorded responses instead of calling GitHub.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any

from basstler.github.client import (
    GitHubClient,
    GitHubResponse,
    HttpMethod,
    RequestBody,
)
from basstler.github.credential import CredentialProvider
from basstler.github.exceptions import GitHubRequestFailed

# %% the client


@dataclass(frozen=True)
class SentWrite:
    """
    One write a client was asked to send.
    """

    method: HttpMethod
    """
    How the resource is written.
    """

    path: str
    """
    The resource's path.
    """

    body: RequestBody
    """
    What the write sends.
    """


@dataclass
class RecordedGitHubClient(GitHubClient):
    """
    Answers each read from :attr:`responses` or :attr:`pages`, refusing any other path
    with :attr:`refusal`, and records every write.
    """

    responses: Mapping[str, Any] = field(default_factory=dict)
    """
    The response to each read path.
    """

    pages: Mapping[str, list[Any]] = field(default_factory=dict)
    """
    Every page of each listing, by the listing's path.
    """

    refusal: HTTPStatus = HTTPStatus.NOT_FOUND
    """
    The status a path with no recording is refused with.
    """

    writes: list[SentWrite] = field(default_factory=list)
    """
    Every write sent, oldest first.
    """

    def get(self, path: str) -> Any:
        if path not in self.responses:
            self._refuse(HttpMethod.GET, path)
        return self.responses[path]

    def get_pages(self, path: str) -> list[Any]:
        if path not in self.pages:
            self._refuse(HttpMethod.GET, path)
        return self.pages[path]

    def attempt_send(
        self, method: HttpMethod, path: str, body: RequestBody
    ) -> GitHubResponse:
        self.writes.append(SentWrite(method, path, body))
        return GitHubResponse(body.to_json())

    def _refuse(self, method: HttpMethod, path: str) -> None:
        """
        :raises GitHubRequestFailed: Always, with :attr:`refusal`.
        """
        raise GitHubRequestFailed(
            status=self.refusal,
            detail="",
            method=method,
            path=path,
            credential_origin=CredentialProvider.CALLER,
        )
