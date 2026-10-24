"""
Every error reading an upstream pull request can end in, whichever way it is read.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from basstler.repository import Repository
from basstler.upstream_reviews_vocabulary import ActionBranch, ActionFile

# %% errors


@dataclass
class UpstreamReadError(Exception, ABC):
    """
    Base class for every failure this script raises.
    """

    def __post_init__(self) -> None:
        Exception.__init__(self, self.describe())

    @abstractmethod
    def describe(self) -> str:
        """:return: The message a caller should see."""


@dataclass
class GitHubCommandFailed(UpstreamReadError):
    """
    Raised when the ``gh`` invocation itself exits non-zero.
    """

    executable: str
    """
    The command that was run.
    """

    exit_code: int
    """
    The status it exited with.
    """

    error_output: str
    """
    Whatever it wrote to standard error.
    """

    def describe(self) -> str:
        """:return: The message a caller should see."""
        return f"{self.executable} exited {self.exit_code}: {self.error_output}"


@dataclass
class GraphQLErrorsReturned(UpstreamReadError):
    """
    Raised when GitHub answers with an ``errors`` array instead of data.
    """

    messages: list[str]
    """
    Every message GitHub reported.
    """

    def describe(self) -> str:
        """:return: The message a caller should see."""
        return "; ".join(self.messages)


@dataclass
class UpstreamPullRequestNotFound(UpstreamReadError):
    """
    Raised when a branch has no pull request open on the upstream.
    """

    branch: str
    """
    The fork branch that was looked up.
    """

    upstream: Repository
    """
    The repository that was searched.
    """

    fork_owner: str
    """
    The owner whose head branches were being claimed.
    """

    def describe(self) -> str:
        """:return: The message a caller should see."""
        return (
            f"no pull request on {self.upstream} has head "
            f"'{self.fork_owner}:{self.branch}' - the branch has most likely not "
            "been promoted upstream yet"
        )


# %% reading through a helper session


@dataclass
class HelperOutputMissing(UpstreamReadError):
    """
    Raised when this session's transcript holds none of the helper's output.
    """

    request_identifier: str
    """
    The request whose output was looked for.
    """

    def describe(self) -> str:
        """:return: The message a caller should see."""
        return (
            f"no output of helper request {self.request_identifier} in this session's transcript - "
            'read the helper session\'s events (list_events, kinds ["user"]) first'
        )


@dataclass
class HelperOutputIncomplete(UpstreamReadError):
    """
    Raised when only some of the helper's output chunks reached the transcript.
    """

    request_identifier: str
    """
    The request whose output was looked for.
    """

    missing: list[int]
    """
    The chunks not found.
    """

    def describe(self) -> str:
        """:return: The message a caller should see."""
        return (
            f"helper request {self.request_identifier} is missing chunks {self.missing} - read the "
            "helper session's earlier events"
        )


@dataclass
class HelperOutputUnreadable(UpstreamReadError):
    """
    Raised when the helper's output does not decode into a recording.
    """

    request_identifier: str
    """
    The request whose output was read.
    """

    reason: str
    """
    What failed.
    """

    def describe(self) -> str:
        """:return: The message a caller should see."""
        return f"helper request {self.request_identifier}'s output is unreadable: {self.reason}"


@dataclass
class HelperResponseMissing(UpstreamReadError):
    """
    Raised when the report asks for a response the helper did not record.
    """

    path: str
    """
    The REST path asked for.
    """

    def describe(self) -> str:
        """:return: The message a caller should see."""
        return f"the helper's recording holds no response for {self.path}"


@dataclass
class NoRecordedReadRequest(UpstreamReadError):
    """
    Raised when ``report`` runs before any ``prompt`` recorded a request.
    """

    location: Path
    """
    Where the request was looked for.
    """

    def describe(self) -> str:
        """:return: The message a caller should see."""
        return f"no helper request recorded at {self.location} - run 'prompt' first"


# %% reading through the fork's Action


class ActionUnavailable(UpstreamReadError, ABC):
    """
    Raised when the fork's Action cannot answer at all, as opposed to answering that the
    read failed.
    """


@dataclass
class ActionNotInstalled(ActionUnavailable):
    """
    Raised when a read is requested from a fork whose Action branch does not exist.
    """

    remote: str
    """
    The remote that was looked at.
    """

    def describe(self) -> str:
        """:return: The message a caller should see."""
        return (
            f"'{self.remote}' has no {ActionBranch.NAME} branch - install it with "
            f"{ActionBranch.install_command}"
        )


@dataclass
class ActionRunNotStarted(ActionUnavailable):
    """
    Raised when GitHub started no run for the pushed request.
    """

    fork: Repository | None
    """
    The fork whose Actions were to run it, when its remote names one.
    """

    waited: int
    """
    How many seconds passed without one.
    """

    def describe(self) -> str:
        """:return: The message a caller should see."""
        actions = f"{self.fork.url}/actions" if self.fork else "the fork's Actions page"
        return (
            f"no run started within {self.waited} s of the request: Actions are most "
            f"likely disabled on the fork, as GitHub starts every fork - enable them "
            f"at {actions}"
        )


@dataclass
class ActionResultMissing(ActionUnavailable):
    """
    Raised when no run answered the request in time.
    """

    request_identifier: str
    """
    The request no result answered.
    """

    fork: Repository | None
    """
    The fork whose Actions were to run it, when its remote names one.
    """

    waited: int
    """
    How many seconds were spent waiting.
    """

    def describe(self) -> str:
        """:return: The message a caller should see."""
        actions = f"{self.fork.url}/actions" if self.fork else "the fork's Actions page"
        return (
            f"no result for request {self.request_identifier} after {self.waited} s. Either Actions "
            f"are disabled on the fork (a fork starts with them off - enable them at "
            f"{actions}), or the run failed: see "
            f"{actions}/workflows/{ActionFile.WORKFLOW.file_name}"
        )


@dataclass
class ActionRunFailed(UpstreamReadError):
    """
    Raised when the run answered the request with an error rather than a recording.
    """

    error: str
    """
    What the run reported.
    """

    def describe(self) -> str:
        """:return: The message a caller should see."""
        return f"the Action could not read the upstream: {self.error}"


@dataclass
class ActionResponseMissing(UpstreamReadError):
    """
    Raised when the replay asks for a response the run did not record - the run used a
    different basstler release from this one.
    """

    query: str
    """
    The digest of the query asked for.
    """

    def describe(self) -> str:
        """:return: The message a caller should see."""
        return (
            f"the Action's recording holds no response for query {self.query} - its "
            f"basstler release differs from this one; re-run {ActionBranch.install_command}"
        )
