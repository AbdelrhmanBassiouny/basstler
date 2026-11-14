"""
One read through the fork's Action, from the session's side: request it on a branch of
its own, wait for its result there, then delete the branch.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from basstler.github.remote_branch import GitHubRemoteBranch
from basstler.github.client import GitHubReader
from basstler.github.exceptions import GitHubRequestFailed
from basstler.github.run_listing import RunListing
from basstler.standard_streams import StandardStreamHandler
from basstler.upstream_reviews.action.branch import ActionBranch, ActionFile
from basstler.upstream_reviews.action.exchange import (
    ActionAnswer,
    ActionRequest,
)
from basstler.upstream_reviews.action.recording import ActionResult
from basstler.upstream_reviews.exceptions import (
    ActionNotInstalled,
    ActionResultMissing,
    ActionRunFailed,
    ActionRunNotStarted,
)

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger.
"""

# %% the session's side


@dataclass(frozen=True)
class ActionRead[AnswerType: ActionAnswer]:
    """
    One read through the fork's Action: request it, then wait for its answer.
    """

    branch: GitHubRemoteBranch
    """
    The fork's Action branch, which every request's branch starts from.
    """

    request: ActionRequest
    """
    The read.
    """

    runs: GitHubReader | None = None
    """
    What lists the fork's runs, so a run that never started or already failed is told
    apart from one still going; ``None`` waits for the result alone.
    """

    poll_interval: float = 5.0
    """
    How many seconds to wait between fetches.
    """

    start_allowance: float = 20.0
    """
    How many seconds GitHub gets to start the run before it is looked for.
    """

    answer_type: type[AnswerType] = ActionResult
    """
    What the run answers the read with: a pull request's report unless named.
    """

    @property
    def request_branch(self) -> GitHubRemoteBranch:
        """
        :return: The branch carrying this request and, once its run answers, its result.
        """
        return GitHubRemoteBranch(
            ActionBranch.for_request(self.request.identifier),
            self.branch.git,
            self.branch.remote,
        )

    def send(self) -> str:
        """
        Push the request on :attr:`request_branch`, which starts the run.

        :return: The pushed commit.
        :raises ActionNotInstalled: If the fork has no Action branch.
        """
        installed = self.branch.fetch()
        if installed is None:
            raise ActionNotInstalled(self.branch.remote)
        return self.request_branch.create(
            installed,
            {ActionFile.REQUEST: self.request.as_sent()},
            ActionBranch.request_commit_message(
                f"Request {self.request.kind}", self.request.identifier
            ),
        )

    def wait(self, timeout: float, commit: str | None = None) -> AnswerType:
        """
        :param timeout: How many seconds to wait at most.
        :param commit: The pushed request, whose run is looked for once
            :attr:`start_allowance` has passed.
        :return: The result answering this request, whose branch is then deleted.
        :raises ActionRunNotStarted: If GitHub started no run for it.
        :raises ActionRunFailed: If its run failed before committing a result.
        :raises ActionResultMissing: If no result arrives in time.
        """
        started = time.monotonic()
        while True:
            result = self.collect()
            if result is not None:
                self.discard_request_branch()
                return result
            elapsed = time.monotonic() - started
            if commit is not None and elapsed >= self.start_allowance:
                self.check_run(commit, int(elapsed))
            if elapsed >= timeout:
                raise ActionResultMissing(
                    self.request.identifier, self.branch.repository, int(timeout)
                )
            time.sleep(self.poll_interval)

    def collect(self) -> AnswerType | None:
        """
        :return: The result on :attr:`request_branch`, ``None`` until its run commits one.
        """
        text = self.request_branch.read_latest(ActionFile.RESULT)
        if text is None:
            return None
        return self.answer_type.from_json(json.loads(text))

    def discard_request_branch(self) -> None:
        """
        Delete :attr:`request_branch` once its result is read; a branch the fork refuses
        to delete is only warned about, as it holds nothing a later read depends on.
        """
        deleted = self.request_branch.delete()
        if not deleted.succeeded:
            logger.warning(
                f"could not delete {self.request_branch.name} on "
                f"{self.branch.description}: {deleted.error_output}"
            )

    def check_run(self, commit: str, elapsed: int) -> None:
        """
        Stop waiting early when there is nothing to wait for.

        :param commit: The pushed request.
        :param elapsed: How many seconds have passed since it was pushed.
        :raises ActionRunNotStarted: If GitHub started no run for it.
        :raises ActionRunFailed: If its run failed - but only once a last look finds
            no result, since a run may fail after committing one.
        """
        fork = self.branch.repository
        if self.runs is None or fork is None:
            return
        try:
            listing = RunListing.read(self.runs, fork, self.request_branch.name)
        except GitHubRequestFailed:
            return
        run = listing.run_for_commit(commit)
        if run is None:
            raise ActionRunNotStarted(fork, elapsed)
        if run.failed and self.collect() is None:
            raise ActionRunFailed(f"its run ended {run.outcome}: {run.page_url}")
