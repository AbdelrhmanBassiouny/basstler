"""
One read through the fork's Action, from the session's side: request it, wait for its
result, replay it.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from basstler.github.run_listing import RunListing
from basstler.maintenance.remote_branch import RemoteBranch
from basstler.upstream_reviews.action.branch import ActionBranch, ActionFile
from basstler.upstream_reviews.action.exchange import (
    ActionAnswer,
    ActionRequest,
)
from basstler.upstream_reviews.action.recording import (
    ActionJSONKey,
    ActionResult,
)
from basstler.github.client import GitHubReader
from basstler.github.exceptions import GitHubRequestFailed
from basstler.upstream_reviews.exceptions import (
    ActionNotInstalled,
    ActionResultMissing,
    ActionRunFailed,
    ActionRunNotStarted,
)

# %% the session's side


@dataclass(frozen=True)
class ActionRead[AnswerType: ActionAnswer]:
    """
    One read through the fork's Action: request it, then wait for its answer.
    """

    branch: RemoteBranch
    """
    The fork's Action branch.
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

    def send(self) -> str:
        """
        Push the request, which starts the run.

        :return: The pushed commit.
        :raises ActionNotInstalled: If the fork has no Action branch.
        """
        if self.branch.fetch() is None:
            raise ActionNotInstalled(self.branch.remote)
        return self.branch.write(
            {ActionFile.REQUEST: json.dumps(self.request.as_sent(), indent=2)},
            f"Request {self.request.kind} {self.request.identifier}",
        )

    def wait(self, timeout: float, commit: str | None = None) -> AnswerType:
        """
        :param timeout: How many seconds to wait at most.
        :param commit: The pushed request, whose run is looked for once
            :attr:`start_allowance` has passed.
        :return: The result answering this request.
        :raises ActionRunNotStarted: If GitHub started no run for it.
        :raises ActionRunFailed: If its run failed before committing a result.
        :raises ActionResultMissing: If no result arrives in time.
        """
        started = time.monotonic()
        while True:
            result = self.collect()
            if result is not None:
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
        :return: The result on the branch, when it answers this request; ``None`` for a
            result answering another request, including one from a release whose results
            named no request at all.
        """
        tip = self.branch.fetch()
        text = self.branch.git.file_at(tip, ActionFile.RESULT) if tip else None
        if text is None:
            return None
        data = json.loads(text)
        if data.get(ActionJSONKey.REQUEST_IDENTIFIER) != self.request.identifier:
            return None
        return self.answer_type.from_json(data)

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
            listing = RunListing.read(self.runs, fork, ActionBranch.NAME)
        except GitHubRequestFailed:
            return
        run = listing.run_for(commit)
        if run is None:
            raise ActionRunNotStarted(fork, elapsed)
        if run.failed and self.collect() is None:
            raise ActionRunFailed(f"its run ended {run.outcome}: {run.page_url}")
