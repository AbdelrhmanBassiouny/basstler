"""
A stand-in for GitHub that answers a site repository's resource and records writes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from http import HTTPStatus

from basstler.github.client import (
    GitHubAttemptClient,
    GitHubResponse,
    GitHubWrite,
    HttpMethod,
)
from basstler.github.credential import CredentialProvider
from basstler.github.exceptions import GitHubRequestFailed

from ..constants.paths import DatasetLocation

SITE_DETAILS = json.loads(
    DatasetLocation.REPOSITORY_TRUNK_DEFAULT_BRANCH.read_text(encoding="utf-8")
)
"""
The resource the stand-in site repository answers with.
"""

# %% a site repository answering from memory


@dataclass
class SiteAnsweringClient(GitHubAttemptClient):
    """
    Answers the site repository's resource, or refuses it with :attr:`refusal`, and
    accepts and records every write.
    """

    refusal: HTTPStatus | None = None
    """
    The status reading the site repository is refused with, ``None`` to answer it.
    """

    writes: list[GitHubWrite] = field(default_factory=list)
    """
    Every write sent, oldest first.
    """

    def attempt_get(self, path: str) -> GitHubResponse:
        if self.refusal is None:
            return GitHubResponse(SITE_DETAILS)
        return GitHubResponse(
            None,
            failure=GitHubRequestFailed(
                status=self.refusal,
                detail="",
                method=HttpMethod.GET,
                path=path,
                credential_origin=CredentialProvider.CALLER,
            ),
        )

    def attempt_send(self, write: GitHubWrite) -> GitHubResponse:
        self.writes.append(write)
        return GitHubResponse(None)
