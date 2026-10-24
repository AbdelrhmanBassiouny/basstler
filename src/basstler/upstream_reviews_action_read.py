"""
One read through the fork's Action, from the session's side: request it, wait for its
result, replay it.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from basstler.repository import Repository
from basstler.upstream_reviews_action_branch import (
    RemoteBranch,
)
from basstler.upstream_reviews_vocabulary import (
    ActionBranch,
    ActionFile,
)
from basstler.upstream_reviews_action_recording import (
    ActionResult,
    ReplayingGraphQLClient,
    read_upstream,
)
from basstler.upstream_reviews_clients import (
    RestClient,
)
from basstler.upstream_reviews_errors import (
    ActionNotInstalled,
    ActionResultMissing,
    ActionRunFailed,
    ActionRunNotStarted,
    GitHubCommandFailed,
)
from basstler.upstream_reviews_request import (
    UpstreamReadRequest,
)
from basstler.upstream_reviews_vocabulary import (
    JSONModel,
)

# %% the session's side


class WorkflowRunJSONKey(StrEnum):
    """
    Every field read out of the fork's workflow-run listing.
    """

    WORKFLOW_RUNS = "workflow_runs"
    HEAD_SHA = "head_sha"
    HTML_URL = "html_url"
    CONCLUSION = "conclusion"


@dataclass(frozen=True)
class WorkflowRun(JSONModel):
    """
    One run of the fork's workflow.
    """

    head_sha: str
    """
    The commit it ran on - the request's, for the run answering it.
    """

    url: str
    """
    Its page.
    """

    conclusion: str | None
    """
    How it ended, ``None`` while it runs.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> WorkflowRun:
        """
        :param data: One listed run.
        :return: The parsed run.
        """
        return cls(
            data[WorkflowRunJSONKey.HEAD_SHA],
            data[WorkflowRunJSONKey.HTML_URL],
            data[WorkflowRunJSONKey.CONCLUSION],
        )

    @property
    def failed(self) -> bool:
        """:return: Whether it ended without succeeding."""
        return self.conclusion not in (None, "success")


@dataclass(frozen=True)
class WorkflowRunPage(JSONModel):
    """
    The fork's latest runs on the Action branch.
    """

    runs: list[WorkflowRun]
    """
    The runs, newest first.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> WorkflowRunPage:
        """
        :param data: The listing.
        :return: The parsed page.
        """
        return cls(
            [
                WorkflowRun.from_json(run)
                for run in data[WorkflowRunJSONKey.WORKFLOW_RUNS]
            ]
        )

    @staticmethod
    def path(fork: Repository) -> str:
        """
        :param fork: The fork.
        :return: The REST path listing its latest runs on the Action branch.
        """
        return f"{fork.api_path}/actions/runs?branch={ActionBranch.NAME}&per_page=10"

    def run_for(self, commit: str) -> WorkflowRun | None:
        """
        :param commit: A pushed request.
        :return: The run answering it, if GitHub started one.
        """
        return next((run for run in self.runs if run.head_sha == commit), None)


@dataclass(frozen=True)
class ActionRead:
    """
    One read through the fork's Action: request it, wait for its result, replay it.
    """

    branch: RemoteBranch
    """
    The fork's Action branch.
    """

    request: UpstreamReadRequest
    """
    The read.
    """

    runs: RestClient | None = None
    """
    What lists the fork's runs, so a run that never started or already failed is told
    apart from one still going; ``None`` waits for the result alone.
    """

    poll_interval: float = 5.0
    """
    How many seconds to wait between fetches.
    """

    start_allowance: float = 60.0
    """
    How many seconds GitHub gets to start the run before it is looked for.
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
            {ActionFile.REQUEST: json.dumps(self.request.to_json(), indent=2) + "\n"},
            f"Request upstream reviews {self.request.identifier}",
        )

    def wait(self, timeout: float, commit: str | None = None) -> ActionResult:
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
                    self.request.identifier, self.branch.fork, int(timeout)
                )
            time.sleep(self.poll_interval)

    def collect(self) -> ActionResult | None:
        """:return: The result on the branch, when it answers this request."""
        tip = self.branch.fetch()
        text = self.branch.read(tip, ActionFile.RESULT) if tip else None
        if text is None:
            return None
        result = ActionResult.from_json(json.loads(text))
        return result if result.request_identifier == self.request.identifier else None

    def check_run(self, commit: str, elapsed: int) -> None:
        """
        Stop waiting early when there is nothing to wait for.

        :param commit: The pushed request.
        :param elapsed: How many seconds have passed since it was pushed.
        :raises ActionRunNotStarted: If GitHub started no run for it.
        :raises ActionRunFailed: If its run failed - but only once a last look finds
            no result, since a run may fail after committing one.
        """
        fork = self.branch.fork
        if self.runs is None or fork is None:
            return
        try:
            page = WorkflowRunPage.from_json(self.runs.get(WorkflowRunPage.path(fork)))
        except GitHubCommandFailed:
            return
        run = page.run_for(commit)
        if run is None:
            raise ActionRunNotStarted(fork, elapsed)
        if run.failed and self.collect() is None:
            raise ActionRunFailed(f"its run ended {run.conclusion}: {run.url}")

    def report(self, result: ActionResult, include_resolved: bool) -> str:
        """
        :param result: The run's result.
        :param include_resolved: Whether to list resolved threads too.
        :return: The rendered markdown.
        :raises ActionRunFailed: If the run reported an error instead.
        """
        if result.error is not None:
            raise ActionRunFailed(result.error)
        return read_upstream(
            ReplayingGraphQLClient(result), self.request, include_resolved
        )
