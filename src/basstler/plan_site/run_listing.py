"""
The workflow runs a repository's branch has had, read from GitHub.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from basstler.locations import WorkflowLocation
from basstler.repository import Repository
from basstler.standard_streams import StandardStreamHandler
from basstler.github.client import (
    GitHubReader,
)
from basstler.upstream_reviews.vocabulary import CheckOutcome, JSONModel

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

MAXIMUM_RUNS_PER_PAGE = 100
"""
The most runs GitHub lists on one page.
"""

# %% the runs that confirm a step


class WorkflowRunKey(StrEnum):
    """
    Every field read out of a repository's run listing.
    """

    WORKFLOW_RUNS = "workflow_runs"
    """
    The listed runs, newest first.
    """

    PATH = "path"
    """
    The path of the workflow file a run ran, relative to its repository's root.
    """

    CONCLUSION = "conclusion"
    """
    How a run ended, ``null`` while it runs.
    """

    URL = "html_url"
    """
    The address of the run's page on github.com.
    """

    CREATED_AT = "created_at"
    """
    When the run was started.
    """


class RunListingParameter(StrEnum):
    """
    The query parameters a run listing is narrowed by.
    """

    BRANCH = "branch"
    """
    The branch the runs ran on.
    """

    RUNS_PER_PAGE = "per_page"
    """
    How many runs the listing holds.
    """


@dataclass(frozen=True)
class ListedRun(JSONModel):
    """
    One run in a repository's run listing.
    """

    workflow: Path
    """
    The workflow file it ran, relative to its repository's root.
    """

    outcome: CheckOutcome
    """
    How it ended, :attr:`CheckOutcome.PENDING` while it runs.
    """

    url: str
    """
    The address of the run's page on github.com, where its log is.
    """

    created_at: datetime
    """
    When it was started.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ListedRun:
        """
        :param data: One listed run.
        :return: The parsed run.
        """
        return cls(
            Path(data[WorkflowRunKey.PATH]),
            CheckOutcome.from_conclusion(data[WorkflowRunKey.CONCLUSION]),
            data[WorkflowRunKey.URL],
            datetime.fromisoformat(data[WorkflowRunKey.CREATED_AT]),
        )


@dataclass(frozen=True)
class RunListing:
    """
    The latest runs on one branch of a repository, newest first.
    """

    runs: list[ListedRun]
    """
    The runs.
    """

    @staticmethod
    def path(
        repository: Repository, branch: str, runs_per_page: int = MAXIMUM_RUNS_PER_PAGE
    ) -> str:
        """
        :param repository: The repository.
        :param branch: The branch the runs ran on.
        :param runs_per_page: How many of the latest runs to list.
        :return: The REST path listing them.
        """
        query = urlencode(
            {
                RunListingParameter.BRANCH: branch,
                RunListingParameter.RUNS_PER_PAGE: runs_per_page,
            }
        )
        return f"{repository.api_path}/actions/runs?{query}"

    @classmethod
    def read(
        cls, client: GitHubReader, repository: Repository, branch: str
    ) -> RunListing:
        """
        :param client: What reads the listing.
        :param repository: The repository.
        :param branch: The branch the runs ran on.
        :return: The listing.
        """
        return cls.from_json(client.get(cls.path(repository, branch)))

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RunListing:
        """
        :param data: A run listing's REST response.
        :return: The parsed listing.
        """
        return cls(
            [ListedRun.from_json(run) for run in data[WorkflowRunKey.WORKFLOW_RUNS]]
        )

    def select(self, workflow: WorkflowLocation) -> RunListing:
        """
        :param workflow: The workflow.
        :return: The listing of its runs alone.
        """
        return RunListing([run for run in self.runs if run.workflow == workflow])

    def count(self, outcome: CheckOutcome) -> int:
        """
        :param outcome: How a run ended.
        :return: How many listed runs ended so.
        """
        return sum(run.outcome is outcome for run in self.runs)

    def latest(self, workflow: WorkflowLocation) -> ListedRun | None:
        """
        :param workflow: The workflow.
        :return: Its latest run, ``None`` when the listing holds none.
        """
        return next((run for run in self.runs if run.workflow == workflow), None)

    def latest_success(self, workflow: WorkflowLocation) -> ListedRun | None:
        """
        :param workflow: The workflow.
        :return: Its latest run that succeeded, ``None`` when the listing holds none.
        """
        return next(
            (
                run
                for run in self.runs
                if run.workflow == workflow and run.outcome is CheckOutcome.SUCCESS
            ),
            None,
        )

    def succeeded(self, workflow: WorkflowLocation) -> bool:
        """
        :param workflow: The workflow.
        :return: Whether its latest run succeeded.
        """
        latest = self.latest(workflow)
        return latest is not None and latest.outcome is CheckOutcome.SUCCESS
