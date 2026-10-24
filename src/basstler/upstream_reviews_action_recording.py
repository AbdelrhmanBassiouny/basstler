"""
What the fork's Action recorded of the upstream, and replaying it in place of GitHub.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from basstler.repository import Repository
from basstler.upstream_reviews_clients import (
    GitHubCommandLineClient,
    GraphQLClient,
    JobLogReader,
)
from basstler.upstream_reviews_errors import (
    ActionResponseMissing,
    UpstreamReadError,
)
from basstler.upstream_reviews_failure_logs import (
    FailureLogReader,
)
from basstler.upstream_reviews_helper_recording import (
    RecordedJobLog,
)
from basstler.upstream_reviews_readers import (
    UpstreamPullRequestReader,
)
from basstler.upstream_reviews_report import (
    UpstreamPullRequestReport,
)
from basstler.upstream_reviews_request import (
    UpstreamReadRequest,
)
from basstler.upstream_reviews_vocabulary import (
    JSONModel,
)

# %% the recording


class ActionJSONKey(StrEnum):
    """
    Every field name in a result.
    """

    REQUEST_IDENTIFIER = "request_identifier"
    ERROR = "error"
    RESPONSES = "responses"
    JOB_LOGS = "job_logs"
    QUERY = "query"
    VARIABLES = "variables"
    DATA = "data"


def query_digest(query: str) -> str:
    """
    :param query: A GraphQL document.
    :return: A short name for it, the same in any release that sends the same text.
    """
    return hashlib.sha256(query.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class RecordedGraphQLResponse(JSONModel):
    """
    One GraphQL response the run read.
    """

    query: str
    """
    The digest of the document sent.
    """

    variables: dict[str, Any]
    """
    Its variables.
    """

    data: dict[str, Any]
    """
    The response's data.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RecordedGraphQLResponse:
        """
        :param data: One recorded response.
        :return: The parsed response.
        """
        return cls(
            data[ActionJSONKey.QUERY],
            data[ActionJSONKey.VARIABLES],
            data[ActionJSONKey.DATA],
        )

    def to_json(self) -> dict[str, Any]:
        """:return: The response as recorded."""
        return {
            ActionJSONKey.QUERY: self.query,
            ActionJSONKey.VARIABLES: self.variables,
            ActionJSONKey.DATA: self.data,
        }


@dataclass(frozen=True)
class ActionResult(JSONModel):
    """
    Everything the run read for one request, or why it could not.
    """

    request_identifier: str
    """
    The request it answers.
    """

    error: str | None = None
    """
    What stopped the read, when something did.
    """

    responses: list[RecordedGraphQLResponse] = field(default_factory=list)
    """
    The GraphQL responses, in the order read.
    """

    job_logs: list[RecordedJobLog] = field(default_factory=list)
    """
    The ends of the logs read behind the checks that did not pass.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ActionResult:
        """
        :param data: A result.
        :return: The parsed result.
        """
        return cls(
            request_identifier=data[ActionJSONKey.REQUEST_IDENTIFIER],
            error=data[ActionJSONKey.ERROR],
            responses=[
                RecordedGraphQLResponse.from_json(entry)
                for entry in data[ActionJSONKey.RESPONSES]
            ],
            job_logs=[
                RecordedJobLog.from_json(entry)
                for entry in data[ActionJSONKey.JOB_LOGS]
            ],
        )

    def to_json(self) -> dict[str, Any]:
        """:return: The result as committed."""
        return {
            ActionJSONKey.REQUEST_IDENTIFIER: self.request_identifier,
            ActionJSONKey.ERROR: self.error,
            ActionJSONKey.RESPONSES: [
                response.to_json() for response in self.responses
            ],
            ActionJSONKey.JOB_LOGS: [
                {"job": log.job, "log": log.log} for log in self.job_logs
            ],
        }


@dataclass
class RecordingClient(GraphQLClient, JobLogReader):
    """
    Reads GitHub through another client, keeping everything it answers.
    """

    client: GitHubCommandLineClient
    """
    The client that reads.
    """

    responses: list[RecordedGraphQLResponse] = field(default_factory=list)
    """
    What was read so far.
    """

    job_logs: list[RecordedJobLog] = field(default_factory=list)
    """
    The ends of the logs read so far.
    """

    def execute(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """
        See :meth:`GraphQLClient.execute`.
        """
        data = self.client.execute(query, variables)
        self.responses.append(
            RecordedGraphQLResponse(query_digest(query), variables, data)
        )
        return data

    def read_job_log(self, repository: Repository, job_identifier: int) -> str:
        """
        See :meth:`JobLogReader.read_job_log`.
        """
        log = self.client.read_job_log(repository, job_identifier)
        kept = "\n".join(log.splitlines()[-RecordedJobLog.line_limit :])
        self.job_logs.append(RecordedJobLog(job_identifier, kept))
        return log


@dataclass
class ReplayingGraphQLClient(GraphQLClient, JobLogReader):
    """
    Answers the reader from what the run recorded, instead of GitHub.
    """

    result: ActionResult
    """
    The run's recording.
    """

    def execute(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """
        See :meth:`GraphQLClient.execute`.
        """
        digest = query_digest(query)
        for response in self.result.responses:
            if response.query == digest and response.variables == variables:
                return response.data
        raise ActionResponseMissing(digest)

    def read_job_log(self, repository: Repository, job_identifier: int) -> str:
        """
        See :meth:`JobLogReader.read_job_log`.
        """
        for log in self.result.job_logs:
            if log.job == job_identifier:
                return log.log
        raise ActionResponseMissing(repository.job_log_path(job_identifier))


def read_upstream(
    client: GraphQLClient | JobLogReader,
    request: UpstreamReadRequest,
    include_resolved: bool,
) -> str:
    """
    Read the requested pull request through *client* and render its report.

    :param client: What answers the reader: GitHub, recorded or replayed.
    :param request: The read.
    :param include_resolved: Whether to list resolved threads too.
    :return: The rendered markdown.
    """
    reader = UpstreamPullRequestReader(client, request.upstream, request.fork_owner)
    number = request.pull_request or reader.resolve_pull_request_number(
        request.branch or ""
    )
    snapshot = reader.read_current_state(number)
    failure_logs = (
        FailureLogReader(client, request.upstream).read(snapshot.checks)
        if request.failure_logs
        else []
    )
    return UpstreamPullRequestReport(
        snapshot, include_resolved=include_resolved, failure_logs=failure_logs
    ).render()


def answer(
    request: UpstreamReadRequest, client: GitHubCommandLineClient
) -> ActionResult:
    """
    What the run commits: the recording of a read, or what stopped it.

    :param request: The branch's request.
    :param client: What reads GitHub.
    :return: The result.
    """
    recording = RecordingClient(client)
    try:
        read_upstream(recording, request, include_resolved=False)
    except UpstreamReadError as failure:
        return ActionResult(request.identifier, error=str(failure))
    return ActionResult(
        request.identifier, None, recording.responses, recording.job_logs
    )
