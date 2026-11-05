"""
Tests for :mod:`basstler.plan_site.build_start`: starting the plan site's build with the
session's own credential.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any

from basstler.github.client import (
    GitHubAttemptReader,
    GitHubResponse,
    GitHubWriter,
    HttpMethod,
)
from basstler.github.credential import CredentialProvider
from basstler.github.exceptions import GitHubRequestFailed
from basstler.locations import WorkflowLocation
from basstler.plan_site.build_start import (
    BuildStart,
    DispatchKey,
    RepositoryKey,
    SessionTool,
)
from basstler.plan_site.site_repository import SiteRepository
from basstler.repository import Repository

from ..github.recorded_client import SentWrite

SITE = SiteRepository(Repository.parse("an-owner/plans"))
"""
The site repository whose build is started.
"""

SITE_DEFAULT_BRANCH = "main"
"""
The site repository's default branch.
"""

# %% a site repository answering from memory


@dataclass
class SiteAnsweringClient(GitHubAttemptReader, GitHubWriter):
    """
    Answers the site repository's resource, or refuses it with :attr:`refusal`, and
    accepts and records every write.
    """

    refusal: HTTPStatus | None = None
    """
    The status reading the site repository is refused with, ``None`` to answer it.
    """

    writes: list[SentWrite] = field(default_factory=list)
    """
    Every write sent, oldest first.
    """

    def attempt_get(self, path: str) -> GitHubResponse:
        if self.refusal is None:
            return GitHubResponse({RepositoryKey.DEFAULT_BRANCH: SITE_DEFAULT_BRANCH})
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

    def attempt_send(
        self, method: HttpMethod, path: str, payload: Mapping[str, Any]
    ) -> GitHubResponse:
        self.writes.append(SentWrite(method, path, payload))
        return GitHubResponse(None)


# %% starting the build


def test_the_build_is_dispatched_on_the_site_s_default_branch():
    client = SiteAnsweringClient()

    attempt = BuildStart.attempt(SITE, client, client)

    assert attempt.started
    assert client.writes == [
        SentWrite(
            HttpMethod.POST,
            f"{SITE.repository.api_path}/actions/workflows/"
            f"{WorkflowLocation.PLAN_SITE.name}/dispatches",
            {DispatchKey.REF: SITE_DEFAULT_BRANCH},
        )
    ]


def test_a_refused_site_repository_dispatches_nothing():
    client = SiteAnsweringClient(refusal=HTTPStatus.FORBIDDEN)

    attempt = BuildStart.attempt(SITE, client, client)

    assert not attempt.started
    assert client.writes == []


def test_a_cloud_session_is_told_to_attach_the_site_repository_and_ask_if_refused():
    client = SiteAnsweringClient(refusal=HTTPStatus.FORBIDDEN)

    description = BuildStart.attempt(SITE, client, client).describe(
        in_cloud_session=True
    )

    assert SessionTool.ATTACH_REPOSITORY in description
    assert SessionTool.ASK_USER in description
    assert SITE.repository.name in description


def test_a_local_session_is_not_told_to_attach_a_repository():
    client = SiteAnsweringClient(refusal=HTTPStatus.FORBIDDEN)

    description = BuildStart.attempt(SITE, client, client).describe(
        in_cloud_session=False
    )

    assert SessionTool.ATTACH_REPOSITORY not in description
