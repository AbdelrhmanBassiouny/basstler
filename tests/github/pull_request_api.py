"""
Pull request objects, paths and refusals shaped like GitHub's REST API's, for tests that
record its answers.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from basstler.github.client import HttpMethod
from basstler.github.credential import CredentialProvider
from basstler.github.exceptions import GitHubRequestFailed
from basstler.github.pull_request_record import (
    PullRequestField,
)
from basstler.github.pull_request_state import PullRequestState
from basstler.github.repository import PullRequestReference, Repository
from basstler.github.repository_access import GitHubRepository, PullRequestListState

from ..constants.paths import DatasetLocation

# %% pull request objects


def api_pull_request(
    reference: PullRequestReference,
    overrides: Mapping[PullRequestField, Any] | None = None,
) -> dict[str, Any]:
    """
    Build one pull request object shaped like the pulls API's.

    :param reference: The pull request to describe.
    :param overrides: Fields to replace.
    """
    record = {
        PullRequestField.NUMBER: reference.number,
        PullRequestField.STATE: PullRequestState.OPEN.value,
        PullRequestField.DRAFT: False,
        PullRequestField.MERGED_AT: None,
        PullRequestField.LABELS: [],
        PullRequestField.HTML_URL: reference.url,
        PullRequestField.BASE: "main",
        PullRequestField.TITLE: f"A pull request #{reference.number}",
    }
    record.update(overrides or {})
    return {
        pull_request_field.key: value for pull_request_field, value in record.items()
    }


# %% paths and answers


def listing_path(repository: Repository) -> str:
    """
    :param repository: The repository whose pull requests are listed.
    :return: The path every pull request of it is listed from.
    """
    return (
        f"/{repository.api_path}/pulls?state={PullRequestListState.ALL.query}"
        f"&per_page={GitHubRepository.page_size}"
    )


def details_of(repository: Repository) -> dict[str, Any]:
    """
    :param repository: A repository the source can read.
    :return: The recorded response to the read of its details.
    """
    return {
        f"/{repository.api_path}": json.loads(
            DatasetLocation.REPOSITORY_NOT_FORK.read_text()
        )
    }


def pull_request_path(reference: PullRequestReference) -> str:
    """
    :param reference: The pull request to read.
    :return: The path it is read from on its own.
    """
    return f"/{reference.repository.pull_request_path(reference.number)}"


def refusal(repository: Repository, status: HTTPStatus) -> GitHubRequestFailed:
    """
    :param repository: The repository whose details are read.
    :param status: The status GitHub answers with.
    :return: The refused read of its details.
    """
    return GitHubRequestFailed.for_status(
        status=status,
        detail="",
        method=HttpMethod.GET,
        path=f"/{repository.api_path}",
        credential_origin=CredentialProvider.CALLER,
    )
