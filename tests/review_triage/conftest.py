"""
Fixtures the review triage suites share: the sample rename and the sample pull request
committed to a scratch repository.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from basstler.github.client import (
    GitHubReader,
    GitHubResponse,
    GitHubWrite,
    GitHubWriter,
)
from basstler.repository import Repository
from basstler.review_triage.pull_request import PullRequestChanges, PullRequestReader
from basstler.review_triage.renames import Rename, RenameMap

from ..scratch_repository import ScratchRepository
from .samples import DescriptionSample, PullRequestSample

# %% stand-ins for GitHub

SAMPLE_REPOSITORY = Repository("example", "project")
"""
The repository the sample pull request is opened on.
"""


@dataclass(frozen=True)
class OnePullRequestReader(GitHubReader):
    """
    Answers every read with one pull request's payload.
    """

    payload: dict[str, Any]
    """
    The pull request's REST payload.
    """

    def get(self, path: str) -> Any:
        return self.payload

    def get_pages(self, path: str) -> list[Any]:
        return [self.payload]


@dataclass
class RecordingWriter(GitHubWriter):
    """
    Records every write and answers each with the same body.
    """

    answer: dict[str, Any]
    """
    The body every write is answered with.
    """

    sent: list[GitHubWrite] = field(default_factory=list)
    """
    Every write sent, oldest first.
    """

    def attempt_send(self, write: GitHubWrite) -> GitHubResponse:
        self.sent.append(write)
        return GitHubResponse(self.answer)


# %% fixtures


@pytest.fixture
def old_name_renamed() -> RenameMap:
    """
    :return: The renames of the samples: ``old_name`` to ``new_name``.
    """
    return RenameMap((Rename("old_name", "new_name", "test"),))


@pytest.fixture
def sample_payload(scratch_repository: ScratchRepository) -> dict[str, Any]:
    """
    Commit the sample pull request's base tree, then its head tree on top.

    :param scratch_repository: The repository to commit in.
    :return: The pull request's payload, naming the two commits.
    """
    for path, text in PullRequestSample.BASE_TREE.files().items():
        scratch_repository.write(path, text)
    scratch_repository.commit_everything("base")
    base_commit = scratch_repository.git.commit_at("HEAD")
    scratch_repository.run_git("rm", "-r", "--quiet", ".")
    for path, text in PullRequestSample.HEAD_TREE.files().items():
        scratch_repository.write(path, text)
    scratch_repository.commit_everything("head")
    payload = PullRequestSample.PAYLOAD.payload()
    payload["base"]["sha"] = base_commit
    payload["head"]["sha"] = scratch_repository.git.commit_at("HEAD")
    return payload


def read_sample(
    scratch_repository: ScratchRepository,
    payload: dict[str, Any],
    description: DescriptionSample,
) -> PullRequestChanges:
    """
    :param scratch_repository: The repository the sample is committed in.
    :param payload: The sample's payload.
    :param description: The description the pull request carries.
    :return: The sample pull request read with that description.
    """
    payload["body"] = description.read()
    return PullRequestReader(
        scratch_repository.git, OnePullRequestReader(payload)
    ).read(SAMPLE_REPOSITORY, payload["number"])


@pytest.fixture
def sample_changes(
    scratch_repository: ScratchRepository, sample_payload: dict[str, Any]
) -> PullRequestChanges:
    """
    :return: The sample pull request, its description declaring nothing.
    """
    return read_sample(
        scratch_repository, sample_payload, DescriptionSample.WITHOUT_DECLARATION
    )
