"""
A pull request source answering from a fixed record, for tests that must not reach
GitHub.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from basstler.pull_request_source import PullRequestSource
from basstler.pull_request_state import PullRequestRecord
from basstler.repository import PullRequestReference, Repository

# %% recorded pull request state


@dataclass
class RecordedPullRequestSource(PullRequestSource):
    """
    Pull request state answered from a fixed record, noting every lookup made.
    """

    records: dict[PullRequestReference, PullRequestRecord] = field(default_factory=dict)
    """
    The pull requests that exist, by reference.
    """

    issue_urls: dict[PullRequestReference, str] = field(default_factory=dict)
    """
    The issue pages that exist, by repository and number.
    """

    looked_up: list[PullRequestReference] = field(default_factory=list)
    """
    Every pull request asked for, in order.
    """

    def pull_request(self, reference: PullRequestReference) -> PullRequestRecord | None:
        self.looked_up.append(reference)
        return self.records.get(reference)

    def issue_url(self, repository: Repository, number: int) -> str | None:
        return self.issue_urls.get(PullRequestReference(repository, number))
