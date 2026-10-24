"""
The interfaces through which GitHub is read, and the client implementing them through
``gh``.
"""

from __future__ import annotations

import json
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from basstler.class_property import classproperty
from basstler.maintenance_constants import GitHubClient
from basstler.repository import Repository
from basstler.upstream_reviews_errors import (
    GitHubCommandFailed,
)
from basstler.upstream_reviews_pull_request_models import (
    GraphQLResponse,
)
from basstler.upstream_reviews_vocabulary import (
    PullRequestJSONKey,
)

# %% client


class JobLogReader(ABC):
    """
    Reads the log one Actions job recorded.
    """

    @abstractmethod
    def read_job_log(self, repository: Repository, job_identifier: int) -> str:
        """
        Read one job's whole log.

        :param repository: The repository the job ran in.
        :param job_identifier: The job to read.
        :return: The log, exactly as the runner recorded it.
        """


class GraphQLClient(ABC):
    """
    Sends a GraphQL document to GitHub and returns its ``data`` data.
    """

    @abstractmethod
    def execute(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """
        Run one GraphQL query.

        :param query: The GraphQL document.
        :param variables: The document's variables.
        :return: The response's ``data`` data.
        """


class RestClient(ABC):
    """
    Reads REST responses from GitHub.
    """

    @abstractmethod
    def get(self, path: str) -> Any:
        """
        Read one response.

        :param path: The REST path, query included.
        :return: The parsed response.
        """

    @abstractmethod
    def get_pages(self, path: str) -> list[Any]:
        """
        Read every page of a paged response.

        :param path: The REST path of the first page, query included.
        :return: Each page's parsed response, in order.
        """


@dataclass
class GitHubCommandLineClient(GraphQLClient, RestClient, JobLogReader):
    """
    A client that shells out to ``gh api``.

    A runner ships ``gh`` and authenticates it from ``GITHUB_TOKEN``, and a Claude Code
    session's proxy authenticates it for the repositories the session has attached, so
    this holds no credential handling of its own.
    """

    executable: str = GitHubClient.COMMAND_LINE
    """
    The command to invoke, overridable for testing.
    """

    @classproperty
    def allow_escape_sequences(cls) -> str:
        """
        What ``gh`` wants before it will print a log at all: a test runner colours its
        own output, and ``gh`` refuses to write terminal escape sequences it was not
        asked for.
        """
        return "--allow-escape-sequences"

    def execute(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """
        Run one GraphQL query through ``gh``.

        :param query: The GraphQL document.
        :param variables: The document's variables.
        :return: The response's ``data`` data.
        :raises GitHubCommandFailed: If ``gh`` exits non-zero.
        :raises GraphQLErrorsReturned: If GitHub answers with errors.
        """
        request = json.dumps(
            {PullRequestJSONKey.QUERY: query, PullRequestJSONKey.VARIABLES: variables}
        )
        return GraphQLResponse.from_json(
            self._run(["api", "graphql", "--input", "-"], request)
        ).result()

    def get(self, path: str) -> Any:
        """
        Read one REST response through ``gh``.

        :param path: The REST path, query included.
        :return: The parsed response.
        :raises GitHubCommandFailed: If ``gh`` exits non-zero.
        """
        return json.loads(self._run(["api", path]))

    def get_pages(self, path: str) -> list[Any]:
        """
        Read every page of a REST response through ``gh``, which follows the pages and
        collects them into one list.

        :param path: The REST path of the first page, query included.
        :return: Each page's parsed response, in order.
        :raises GitHubCommandFailed: If ``gh`` exits non-zero.
        """
        return json.loads(self._run(["api", "--paginate", "--slurp", path]))

    def read_job_log(self, repository: Repository, job_identifier: int) -> str:
        """
        Read one job's log through ``gh``.

        The upstream is a different repository from the one the runner is running in,
        which its token reads as anyone else does.

        :param repository: The repository the job ran in.
        :param job_identifier: The job to read.
        :return: The log, exactly as the runner recorded it.
        :raises GitHubCommandFailed: If ``gh`` exits non-zero.
        """
        return self._run(
            [
                "api",
                self.allow_escape_sequences,
                repository.job_log_path(job_identifier),
            ]
        )

    def _run(self, arguments: list[str], standard_input: str | None = None) -> str:
        """
        Invoke ``gh`` once and hand back what it wrote.

        :param arguments: The arguments to pass.
        :param standard_input: What to write to its standard input, if anything.
        :return: Its standard output.
        :raises GitHubCommandFailed: If it exits non-zero.
        """
        completed = subprocess.run(
            [self.executable, *arguments],
            input=standard_input,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise GitHubCommandFailed(
                self.executable, completed.returncode, completed.stderr.strip()
            )
        return completed.stdout
