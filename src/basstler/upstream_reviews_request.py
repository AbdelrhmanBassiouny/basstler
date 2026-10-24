"""
One read of an upstream pull request, as a session hands it to a helper session or to
the fork's Action.
"""

from __future__ import annotations

import argparse
import json
import secrets
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from basstler.class_property import classproperty
from basstler.repository import Repository
from basstler.upstream_reviews_errors import (
    NoRecordedReadRequest,
)
from basstler.upstream_reviews_vocabulary import (
    JSONModel,
)

# %% the request


class HelperJSONKey(StrEnum):
    """
    Every field name in a recorded request and in the recording the helper prints.
    """

    REQUEST_IDENTIFIER = "request_identifier"
    UPSTREAM = "upstream"
    FORK_OWNER = "fork_owner"
    PULL_REQUEST = "pull_request"
    BRANCH = "branch"
    FAILURE_LOGS = "failure_logs"
    RESPONSES = "responses"
    JOB_LOGS = "job_logs"
    PATH = "path"
    BODY = "body"
    JOB = "job"
    LOG = "log"


@dataclass(frozen=True)
class UpstreamReadRequest(JSONModel):
    """
    One read handed to a helper session, recorded so the report can be built from its
    output later.
    """

    identifier: str
    """
    A random token telling this request's output apart from any other's.
    """

    upstream: Repository
    """
    The repository to read.
    """

    fork_owner: str
    """
    Whose branches to claim.
    """

    pull_request: int | None
    """
    The upstream pull request to read, when given by number.
    """

    branch: str | None
    """
    The fork branch whose upstream pull request to read, when given by branch.
    """

    failure_logs: bool
    """
    Whether to read the log behind each check that did not pass.
    """

    @classproperty
    def location(cls) -> Path:
        """
        Where the latest request is recorded: scratch state of this container only.
        """
        return (
            Path(tempfile.gettempdir()) / "basstler-upstream-reviews" / "request.json"
        )

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> UpstreamReadRequest:
        """
        :param data: A recorded request.
        :return: The parsed request.
        """
        return cls(
            identifier=data[HelperJSONKey.REQUEST_IDENTIFIER],
            upstream=Repository.parse(data[HelperJSONKey.UPSTREAM]),
            fork_owner=data[HelperJSONKey.FORK_OWNER],
            pull_request=data[HelperJSONKey.PULL_REQUEST],
            branch=data[HelperJSONKey.BRANCH],
            failure_logs=data[HelperJSONKey.FAILURE_LOGS],
        )

    @classmethod
    def from_arguments(cls, arguments: argparse.Namespace) -> UpstreamReadRequest:
        """
        :param arguments: A ``prompt`` command line.
        :return: The request it describes, with a fresh identifier.
        """
        return cls(
            secrets.token_hex(8),
            arguments.upstream,
            arguments.fork_owner,
            arguments.pull_request,
            arguments.branch,
            arguments.failure_logs,
        )

    def to_json(self) -> dict[str, Any]:
        """:return: The request as recorded."""
        return {
            HelperJSONKey.REQUEST_IDENTIFIER: self.identifier,
            HelperJSONKey.UPSTREAM: str(self.upstream),
            HelperJSONKey.FORK_OWNER: self.fork_owner,
            HelperJSONKey.PULL_REQUEST: self.pull_request,
            HelperJSONKey.BRANCH: self.branch,
            HelperJSONKey.FAILURE_LOGS: self.failure_logs,
        }

    def save(self) -> None:
        """
        Record this as the latest request.
        """
        self.location.parent.mkdir(parents=True, exist_ok=True)
        self.location.write_text(json.dumps(self.to_json()))

    @classmethod
    def load(cls) -> UpstreamReadRequest:
        """
        :return: The latest recorded request.
        :raises NoRecordedReadRequest: If none was recorded.
        """
        if not cls.location.is_file():
            raise NoRecordedReadRequest(cls.location)
        return cls.from_json(json.loads(cls.location.read_text()))
