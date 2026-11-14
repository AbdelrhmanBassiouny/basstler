"""
The run on a request's branch that answers the request a session pushed there.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from basstler.git.commands import GitCommandRunner
from basstler.git.remote_branch import RemoteBranch
from basstler.github.repository_access import GitHubRepository
from basstler.maintenance.upstream_action import (
    OpenPullRequestsAnswer,
    OpenPullRequestsRequest,
)
from basstler.upstream_reviews.action.branch import ActionBranch, ActionFile
from basstler.upstream_reviews.action.exchange import (
    ActionAnswer,
    ActionRequest,
    ActionRequestKind,
)
from basstler.upstream_reviews.action.recording import ActionResult
from basstler.upstream_reviews.clients import GitHubCommandLineClient
from basstler.upstream_reviews.request import UpstreamReadRequest

# %% the run


@dataclass(frozen=True)
class ActionRun:
    """
    One run answering the request pushed on its own branch, with the runner's
    credential.
    """

    request_file: Path
    """
    The pushed request.
    """

    git: GitCommandRunner
    """
    The checkout of the request's branch.
    """

    remote: str
    """
    The fork's remote in :attr:`git`.
    """

    def answer(self) -> ActionAnswer:
        """
        :return: The upstream read as the pushed request asks.
        """
        data = json.loads(self.request_file.read_text())
        if ActionRequest.kind_of(data) is ActionRequestKind.OPEN_PULL_REQUESTS:
            request = OpenPullRequestsRequest.from_json(data)
            return OpenPullRequestsAnswer.answering(
                request, GitHubRepository.from_environment(request.upstream)
            )
        return ActionResult.answering(
            UpstreamReadRequest.from_json(data), GitHubCommandLineClient()
        )

    def publish_answer(self) -> str:
        """
        Answer the pushed request and commit the answer onto the request's branch.

        :return: The pushed commit.
        :raises GitCommandFailed: If the fork refuses the push.
        """
        answer = self.answer()
        return RemoteBranch(
            ActionBranch.for_request(answer.request_identifier), self.git, self.remote
        ).write(
            {ActionFile.RESULT: answer},
            ActionBranch.request_commit_message("Answer", answer.request_identifier),
        )
