"""
A GitHub client answering from recorded responses instead of calling GitHub.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any

from basstler.github.client import (
    GitHubFullClient,
    GitHubResponse,
    GitHubWrite,
    HttpMethod,
)
from basstler.github.credential import CredentialProvider
from basstler.github.exceptions import GitHubRequestFailed

# %% the client


@dataclass
class RecordedGitHubClient(GitHubFullClient):
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

    writes: list[GitHubWrite] = field(default_factory=list)
    """
    Every write sent, oldest first.
    """

    def get(self, path: str) -> Any:
        return self.attempt_get(path).raise_if_failed()

    def attempt_get(self, path: str) -> GitHubResponse:
        if path not in self.responses:
            return GitHubResponse(None, failure=self._refusal_of(HttpMethod.GET, path))
        return GitHubResponse(self.responses[path])

    def get_pages(self, path: str) -> list[Any]:
        if path not in self.pages:
            raise self._refusal_of(HttpMethod.GET, path)
        return self.pages[path]

    def attempt_send(self, write: GitHubWrite) -> GitHubResponse:
        self.writes.append(write)
        return GitHubResponse(write.to_json())

    def _refusal_of(self, method: HttpMethod, path: str) -> GitHubRequestFailed:
        """
        :return: The refusal of a call with no recording, with :attr:`refusal`.
        """
        return GitHubRequestFailed(
            status=self.refusal,
            detail="",
            method=method,
            path=path,
            credential_origin=CredentialProvider.CALLER,
        )
