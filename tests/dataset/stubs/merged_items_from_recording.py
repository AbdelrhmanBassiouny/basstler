"""
Stands in for :mod:`basstler.plan.merged_items`'s command, reading the pull requests
from the ``pr_data.json``-shaped file ``STUB_PULL_REQUESTS`` names instead of from
GitHub.

With the variable unset, no pull request exists; naming a missing file, every read gets
no answer.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from basstler.github.client import HttpMethod
from basstler.github.exceptions import GitHubUnreachableError
from basstler.plan.merged_items import MergedItems
from basstler.pull_request_source import PullRequestSource
from basstler.pull_request_state import PullRequestRecord
from basstler.repository import PullRequestReference, Repository

# %% recorded pull requests


@dataclass(frozen=True)
class RecordingPullRequestSource(PullRequestSource):
    """
    Pull requests answered from a recording file.
    """

    recording: Path | None
    """
    The recording, ``None`` when no pull request exists.
    """

    def pull_request(self, reference: PullRequestReference) -> PullRequestRecord | None:
        if self.recording is None:
            return None
        if not self.recording.is_file():
            raise GitHubUnreachableError(
                HttpMethod.GET, f"repos/{reference.repository}/pulls", "no recording"
            )
        recorded = PullRequestRecord.parse_by_repository(
            json.loads(self.recording.read_text())
        )
        return recorded.get(str(reference.repository), {}).get(str(reference.number))

    def issue_url(self, repository: Repository, number: int) -> str | None:
        return None


# %% the command

recording = os.environ.get("STUB_PULL_REQUESTS")
sys.exit(
    MergedItems.record(
        Path(sys.argv[1]), RecordingPullRequestSource(recording and Path(recording))
    )
)
