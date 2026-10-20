#!/usr/bin/env python3
"""
Read an upstream pull request through a helper session, for a Claude Code cloud session
that cannot attach the upstream itself.

A cloud session checks every attached repository out at a directory named after it, so
a session working in a fork can never attach the fork's same-named upstream beside it.
The read then happens in a helper session that has only the upstream attached. That
helper checks basstler out at the exact version this session runs - it needs nothing
beyond the standard library, so no installation - and runs :class:`RestPullRequestReader`
through a client that records every response. The recording reaches this session's
transcript when its events are read, and the report replays it through the same reader,
so every request, the branch choice and every failure match a direct read by
construction.

Three commands::

    # here: record the request and print the helper session's first message
    python -m basstler.upstream_reviews_helper prompt --upstream O/N --fork-owner F \\
        (--pull-request N | --branch B) [--failure-logs] [--reference REF]
    # in the helper: read and print the recording
    python -m basstler.upstream_reviews_helper fetch --nonce X --upstream O/N ...
    # here, once the helper's events are read: render the report
    python -m basstler.upstream_reviews_helper report [--include-resolved]
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import re
import secrets
import shlex
import sys
import tempfile
import zlib
from dataclasses import dataclass, field
from enum import StrEnum
from importlib import metadata
from pathlib import Path
from typing import Any

from basstler.class_property import classproperty
from basstler.locations import ClaudeCodeVariable
from basstler.repository import Repository
from basstler.standard_streams import StandardStreamHandler
from basstler.upstream_reviews import (
    FailureLogReader,
    GitHubCommandFailed,
    GitHubCommandLineClient,
    JobLogReader,
    JSONModel,
    PullRequestJSONKey,
    RestClient,
    RestJSONKey,
    RestPullRequestReader,
    UpstreamPullRequestReport,
    UpstreamPullRequestSnapshot,
    UpstreamReadError,
)

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its commands print through.
"""

BASSTLER_REPOSITORY = Repository("AbdelrhmanBassiouny", "basstler")
"""
Where the helper checks basstler out from; ``BASSTLER_REPOSITORY_URL`` in
``resolve-personal-notes-config.sh`` names the same repository.
"""


# %% errors


@dataclass
class HelperOutputMissing(UpstreamReadError):
    """
    Raised when this session's transcript holds none of the helper's output.
    """

    nonce: str
    """
    The request whose output was looked for.
    """

    def describe(self) -> str:
        """:return: The message a caller should see."""
        return (
            f"no output of helper request {self.nonce} in this session's transcript - "
            'read the helper session\'s events (list_events, kinds ["user"]) first'
        )


@dataclass
class HelperOutputIncomplete(UpstreamReadError):
    """
    Raised when only some of the helper's output chunks reached the transcript.
    """

    nonce: str
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
            f"helper request {self.nonce} is missing chunks {self.missing} - read the "
            "helper session's earlier events"
        )


@dataclass
class HelperOutputUnreadable(UpstreamReadError):
    """
    Raised when the helper's output does not decode into a recording.
    """

    nonce: str
    """
    The request whose output was read.
    """

    reason: str
    """
    What failed.
    """

    def describe(self) -> str:
        """:return: The message a caller should see."""
        return f"helper request {self.nonce}'s output is unreadable: {self.reason}"


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
class NoHelperRequest(UpstreamReadError):
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


@dataclass
class UnknownBasstlerVersion(UpstreamReadError):
    """
    Raised when the version for the helper to check out cannot be told.
    """

    def describe(self) -> str:
        """:return: The message a caller should see."""
        return "basstler is not installed as a distribution - pass --reference"


# %% the request


class HelperJSONKey(StrEnum):
    """
    Every field name in a recorded request and in the recording the helper prints.
    """

    NONCE = "nonce"
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
class HelperRequest(JSONModel):
    """
    One read handed to a helper session, recorded so the report can be built from its
    output later.
    """

    nonce: str
    """
    Marks this request's output apart from any other in the transcript.
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
    def from_json(cls, data: dict[str, Any]) -> HelperRequest:
        """
        :param data: A recorded request.
        :return: The parsed request.
        """
        return cls(
            nonce=data[HelperJSONKey.NONCE],
            upstream=Repository.parse(data[HelperJSONKey.UPSTREAM]),
            fork_owner=data[HelperJSONKey.FORK_OWNER],
            pull_request=data[HelperJSONKey.PULL_REQUEST],
            branch=data[HelperJSONKey.BRANCH],
            failure_logs=data[HelperJSONKey.FAILURE_LOGS],
        )

    @classmethod
    def from_arguments(cls, arguments: argparse.Namespace) -> HelperRequest:
        """
        :param arguments: A ``prompt`` or ``fetch`` command line.
        :return: The request it describes, with a fresh nonce unless it names one.
        """
        return cls(
            getattr(arguments, "nonce", None) or secrets.token_hex(8),
            arguments.upstream,
            arguments.fork_owner,
            arguments.pull_request,
            arguments.branch,
            arguments.failure_logs,
        )

    def to_json(self) -> dict[str, Any]:
        """:return: The request as recorded."""
        return {
            HelperJSONKey.NONCE: self.nonce,
            HelperJSONKey.UPSTREAM: str(self.upstream),
            HelperJSONKey.FORK_OWNER: self.fork_owner,
            HelperJSONKey.PULL_REQUEST: self.pull_request,
            HelperJSONKey.BRANCH: self.branch,
            HelperJSONKey.FAILURE_LOGS: self.failure_logs,
        }

    @property
    def fetch_arguments(self) -> list[str]:
        """:return: The ``fetch`` command line performing this request."""
        target = (
            ["--pull-request", str(self.pull_request)]
            if self.pull_request
            else ["--branch", self.branch or ""]
        )
        flags = ["--failure-logs"] if self.failure_logs else []
        return [
            HelperCommand.FETCH,
            "--nonce",
            self.nonce,
            "--upstream",
            str(self.upstream),
            "--fork-owner",
            self.fork_owner,
            *target,
            *flags,
        ]

    def save(self) -> None:
        """Record this as the latest request."""
        self.location.parent.mkdir(parents=True, exist_ok=True)
        self.location.write_text(json.dumps(self.to_json()))

    @classmethod
    def load(cls) -> HelperRequest:
        """
        :return: The latest recorded request.
        :raises NoHelperRequest: If none was recorded.
        """
        if not cls.location.is_file():
            raise NoHelperRequest(cls.location)
        return cls.from_json(json.loads(cls.location.read_text()))


# %% what the helper is told


@dataclass(frozen=True)
class HelperPrompt:
    """
    The whole first message a helper session is started with.
    """

    request: HelperRequest
    """
    The read to perform.
    """

    reference: str
    """
    The basstler tag or commit the helper runs: the one this session runs, so both
    sides read and replay with the same code.
    """

    @classmethod
    def own_reference(cls) -> str:
        """
        :return: The release tag of the basstler this runs.
        :raises UnknownBasstlerVersion: If it is not installed as a distribution.
        """
        try:
            return f"v{metadata.version(BASSTLER_REPOSITORY.name)}"
        except metadata.PackageNotFoundError as missing:
            raise UnknownBasstlerVersion() from missing

    @property
    def command(self) -> str:
        """
        :return: The one shell command the helper runs: check basstler out at
            :attr:`reference` into a scratch directory, and run ``fetch`` from it.
        """
        fetch = shlex.join(
            ["python3", "-m", __spec__.name if __spec__ else __name__]
            + self.request.fetch_arguments
        )
        return (
            'cd "$(mktemp -d)" && git init -q && git fetch -q --depth 1 '
            f"{shlex.quote(BASSTLER_REPOSITORY.url)} {shlex.quote(self.reference)} "
            f"&& git checkout -q FETCH_HEAD && PYTHONPATH=src {fetch}"
        )

    def render(self) -> str:
        """:return: The message."""
        return "\n".join(
            [
                "Read-only helper for another session: change nothing on GitHub or in "
                "git. Run this in one Bash call, exactly as written:",
                "",
                self.command,
                "",
                "If it prints `cat` commands, run each as its own Bash call. Never "
                "repeat or summarize output; the other session reads it from your "
                "transcript. Then reply with exactly DONE, or with the error text if "
                "a command failed.",
            ]
        )


# %% the recording


class RecordedFields:
    """
    The REST fields the models read, which are all a recording keeps.
    """

    @classproperty
    def names(cls) -> frozenset[str]:
        """
        Every field name a REST model reads, at any depth.
        """
        return frozenset(key.value for key in RestJSONKey) | {
            PullRequestJSONKey.LOGIN.value
        }

    @classmethod
    def kept(cls, value: Any) -> Any:
        """
        :param value: A parsed response, or any part of one.
        :return: The value with every other field of every object dropped.
        """
        if isinstance(value, dict):
            return {
                name: cls.kept(entry)
                for name, entry in value.items()
                if name in cls.names
            }
        if isinstance(value, list):
            return [cls.kept(entry) for entry in value]
        return value


@dataclass(frozen=True)
class RecordedRestResponse(JSONModel):
    """
    One REST response the helper read.
    """

    path: str
    """
    The path it answers, exactly as the reader asked for it.
    """

    body: Any
    """
    The response, or every page of it for a paged path, with only the read fields.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RecordedRestResponse:
        """
        :param data: One recorded response.
        :return: The parsed response.
        """
        return cls(data[HelperJSONKey.PATH], data[HelperJSONKey.BODY])

    def to_json(self) -> dict[str, Any]:
        """:return: The response as recorded."""
        return {HelperJSONKey.PATH: self.path, HelperJSONKey.BODY: self.body}


@dataclass(frozen=True)
class RecordedJobLog(JSONModel):
    """
    The end of one job's log, as the helper read it.
    """

    job: int
    """
    The Actions job.
    """

    log: str
    """
    Its last lines.
    """

    @classproperty
    def line_limit(cls) -> int:
        """
        How many of a log's last lines are kept: where a failure's summary sits,
        without a whole log swelling the output.
        """
        return 2000

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RecordedJobLog:
        """
        :param data: One recorded log.
        :return: The parsed log.
        """
        return cls(data[HelperJSONKey.JOB], data[HelperJSONKey.LOG])

    def to_json(self) -> dict[str, Any]:
        """:return: The log as recorded."""
        return {HelperJSONKey.JOB: self.job, HelperJSONKey.LOG: self.log}


@dataclass(frozen=True)
class HelperRecording(JSONModel):
    """
    Everything the helper read for one request.
    """

    nonce: str
    """
    The request it answers.
    """

    responses: list[RecordedRestResponse]
    """
    The REST responses, in the order read.
    """

    job_logs: list[RecordedJobLog] = field(default_factory=list)
    """
    The logs read behind the checks that did not pass.
    """

    @classproperty
    def size_limit(cls) -> int:
        """
        The most bytes a decoded recording may take, so a corrupt one cannot exhaust
        memory.
        """
        return 64 * 1024 * 1024

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> HelperRecording:
        """
        :param data: The decoded recording.
        :return: The parsed recording.
        """
        return cls(
            nonce=data[HelperJSONKey.NONCE],
            responses=[
                RecordedRestResponse.from_json(entry)
                for entry in data[HelperJSONKey.RESPONSES]
            ],
            job_logs=[
                RecordedJobLog.from_json(entry)
                for entry in data[HelperJSONKey.JOB_LOGS]
            ],
        )

    def to_json(self) -> dict[str, Any]:
        """:return: The recording, as encoded."""
        return {
            HelperJSONKey.NONCE: self.nonce,
            HelperJSONKey.RESPONSES: [entry.to_json() for entry in self.responses],
            HelperJSONKey.JOB_LOGS: [entry.to_json() for entry in self.job_logs],
        }

    def output_lines(self) -> list[str]:
        """
        Encode the recording: compressed, then base64, so it is small and no escaping
        in any transcript layer can alter it, and split into marked chunks.

        :return: One line per chunk.
        """
        encoded = base64.b64encode(
            zlib.compress(json.dumps(self.to_json(), separators=(",", ":")).encode(), 9)
        ).decode()
        size = HelperChunk.size
        texts = [
            encoded[start : start + size] for start in range(0, len(encoded), size)
        ]
        return [
            HelperChunk(index, len(texts), text).line(self.nonce)
            for index, text in enumerate(texts, 1)
        ]

    @classmethod
    def assemble(cls, nonce: str, chunks: list[HelperChunk]) -> HelperRecording:
        """
        Join a request's chunks back into its recording.

        :param nonce: The request's nonce.
        :param chunks: Every chunk found, repeats included.
        :return: The recording.
        :raises HelperOutputMissing: If no chunk was found.
        :raises HelperOutputIncomplete: If some were not.
        :raises HelperOutputUnreadable: If they do not decode into this request's
            recording.
        """
        if not chunks:
            raise HelperOutputMissing(nonce)
        count = chunks[0].count
        by_index = {chunk.index: chunk.text for chunk in chunks}
        missing = [index for index in range(1, count + 1) if index not in by_index]
        if missing:
            raise HelperOutputIncomplete(nonce, missing)
        encoded = "".join(by_index[index] for index in range(1, count + 1))
        try:
            decompressor = zlib.decompressobj()
            decoded = decompressor.decompress(
                base64.b64decode(encoded, validate=True), cls.size_limit
            )
            if decompressor.unconsumed_tail:
                raise HelperOutputUnreadable(nonce, "larger than the size limit")
            recording = cls.from_json(json.loads(decoded))
        except (binascii.Error, zlib.error, ValueError, KeyError, TypeError) as failure:
            raise HelperOutputUnreadable(nonce, str(failure)) from failure
        if recording.nonce != nonce:
            raise HelperOutputUnreadable(nonce, f"it answers request {recording.nonce}")
        return recording


@dataclass(frozen=True)
class HelperChunk:
    """
    One piece of the helper's encoded output.
    """

    index: int
    """
    Its position, from 1.
    """

    count: int
    """
    How many pieces the output was split into.
    """

    text: str
    """
    Its share of the encoded output.
    """

    size = 20000
    """
    How many characters each chunk carries, under what a session keeps of one
    command's output.
    """

    @classmethod
    def marker(cls, nonce: str) -> str:
        """
        :param nonce: The request's nonce.
        :return: What each chunk's line starts with, before its index and count.
        """
        return f"BASSTLER-UPSTREAM-REVIEWS-{nonce}"

    def line(self, nonce: str) -> str:
        """
        :param nonce: The request's nonce.
        :return: The chunk as printed.
        """
        return f"{self.marker(nonce)}-{self.index}-{self.count}:{self.text}"

    @classmethod
    def pattern(cls, nonce: str) -> re.Pattern[str]:
        """
        :param nonce: The request's nonce.
        :return: What one chunk looks like, wherever it is quoted.
        """
        return re.compile(
            rf"{re.escape(cls.marker(nonce))}-(?P<index>\d+)-(?P<count>\d+)"
            r":(?P<text>[A-Za-z0-9+/=]+)"
        )

    @classmethod
    def found_in(cls, nonce: str, text: str) -> list[HelperChunk]:
        """
        :param nonce: The request's nonce.
        :param text: Where to look.
        :return: Every chunk quoted there, repeats included.
        """
        return [
            cls(int(match["index"]), int(match["count"]), match["text"])
            for match in cls.pattern(nonce).finditer(text)
        ]


# %% reading through the recording


@dataclass
class RecordingClient(RestClient, JobLogReader):
    """
    Reads GitHub through ``gh`` like :class:`GitHubCommandLineClient`, keeping the
    read fields of every response: what the helper reads through.
    """

    client: RestClient | JobLogReader = field(default_factory=GitHubCommandLineClient)
    """
    What actually reaches GitHub.
    """

    responses: list[RecordedRestResponse] = field(default_factory=list)
    """
    Every response read, in order.
    """

    job_logs: list[RecordedJobLog] = field(default_factory=list)
    """
    Every log read, in order.
    """

    def get(self, path: str) -> Any:
        """See :meth:`RestClient.get`."""
        body = self.client.get(path)  # type: ignore[union-attr]
        self.responses.append(RecordedRestResponse(path, RecordedFields.kept(body)))
        return body

    def get_pages(self, path: str) -> list[Any]:
        """See :meth:`RestClient.get_pages`."""
        pages = self.client.get_pages(path)  # type: ignore[union-attr]
        self.responses.append(RecordedRestResponse(path, RecordedFields.kept(pages)))
        return pages

    def read_job_log(self, repository: Repository, job_identifier: int) -> str:
        """See :meth:`JobLogReader.read_job_log`."""
        log = self.client.read_job_log(repository, job_identifier)  # type: ignore[union-attr]
        kept = "\n".join(log.splitlines()[-RecordedJobLog.line_limit :])
        self.job_logs.append(RecordedJobLog(job_identifier, kept))
        return kept

    def recording(self, nonce: str) -> HelperRecording:
        """
        :param nonce: The request read.
        :return: Everything read.
        """
        return HelperRecording(nonce, self.responses, self.job_logs)


@dataclass
class ReplayingClient(RestClient, JobLogReader):
    """
    Answers the reader from what the helper recorded, instead of GitHub.
    """

    recording: HelperRecording
    """
    The helper's output.
    """

    def _response(self, path: str) -> Any:
        """
        :param path: The REST path asked for.
        :return: The response recorded for it.
        :raises HelperResponseMissing: If the helper recorded no such path.
        """
        for response in self.recording.responses:
            if response.path == path:
                return response.body
        raise HelperResponseMissing(path)

    def get(self, path: str) -> Any:
        """See :meth:`RestClient.get`."""
        return self._response(path)

    def get_pages(self, path: str) -> list[Any]:
        """See :meth:`RestClient.get_pages`."""
        return self._response(path)

    def read_job_log(self, repository: Repository, job_identifier: int) -> str:
        """See :meth:`JobLogReader.read_job_log`."""
        for log in self.recording.job_logs:
            if log.job == job_identifier:
                return log.log
        raise HelperResponseMissing(repository.job_log_path(job_identifier))


def read(
    request: HelperRequest, client: RestClient | JobLogReader
) -> tuple[UpstreamPullRequestSnapshot, list]:
    """
    Read the requested pull request the way a direct read does, through any client.

    :param request: The read.
    :param client: What answers it: GitHub while recording, the recording on replay.
    :return: The snapshot and, when asked for, the failed checks' log excerpts.
    """
    reader = RestPullRequestReader(client, request.upstream, request.fork_owner)  # type: ignore[arg-type]
    number = request.pull_request or reader.resolve_pull_request_number(
        request.branch or ""
    )
    snapshot = reader.read_current_state(number)
    failure_logs = (
        FailureLogReader(client, request.upstream).read(snapshot.checks)  # type: ignore[arg-type]
        if request.failure_logs
        else []
    )
    return snapshot, failure_logs


def build_report(
    request: HelperRequest, recording: HelperRecording, include_resolved: bool
) -> str:
    """
    Render the report a direct read would, from the helper's recording.

    :param request: The read the helper performed.
    :param recording: What it recorded.
    :param include_resolved: Whether to list resolved threads too.
    :return: The rendered markdown.
    """
    snapshot, failure_logs = read(request, ReplayingClient(recording))
    return UpstreamPullRequestReport(
        snapshot, include_resolved=include_resolved, failure_logs=failure_logs
    ).render()


def fetch(request: HelperRequest, client: RecordingClient) -> list[str]:
    """
    Read the request through the recording client, as the helper does.

    A read that ends in this module's own error - a branch never promoted upstream -
    still yields its recording, so the replay reaches the same error and reports it
    the same way. Only ``gh`` itself failing leaves nothing to replay.

    :param request: The read.
    :param client: The recording client.
    :return: The output lines to print.
    :raises GitHubCommandFailed: If ``gh`` fails.
    """
    try:
        read(request, client)
    except GitHubCommandFailed:
        raise
    except UpstreamReadError:
        pass
    return client.recording(request.nonce).output_lines()


@dataclass(frozen=True)
class SessionTranscript:
    """
    This session's own transcript, where every tool result it received is kept whole.
    """

    session_identifier: str
    """
    The session whose transcript to read.
    """

    configuration_directory: Path
    """
    Where Claude Code keeps its state.
    """

    @classmethod
    def current(cls) -> SessionTranscript:
        """:return: The transcript of the session running this."""
        configured = ClaudeCodeVariable.CONFIGURATION_DIRECTORY.read()
        return cls(
            ClaudeCodeVariable.SESSION_IDENTIFIER.read() or "",
            Path(configured) if configured else Path.home() / ".claude",
        )

    @property
    def files(self) -> list[Path]:
        """
        :return: Every file of it: one per project directory the session has run in.
        """
        if not self.session_identifier:
            return []
        return sorted(
            (self.configuration_directory / "projects").glob(
                f"*/{self.session_identifier}.jsonl"
            )
        )

    def chunks(self, nonce: str) -> list[HelperChunk]:
        """
        :param nonce: The request's nonce.
        :return: Every chunk of its output the transcript quotes.
        """
        return [
            chunk
            for path in self.files
            for chunk in HelperChunk.found_in(nonce, path.read_text(errors="replace"))
        ]


# %% command line


class HelperCommand(StrEnum):
    """
    The module's three commands.
    """

    PROMPT = "prompt"
    """
    Record a request and print the helper session's first message.
    """

    FETCH = "fetch"
    """
    In the helper: read the request and print its recording.
    """

    REPORT = "report"
    """
    Build the report from the helper's output in this session's transcript.
    """


def _add_request_arguments(parser: argparse.ArgumentParser) -> None:
    """
    :param parser: A ``prompt`` or ``fetch`` parser, given what a request needs.
    """
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--pull-request", type=int)
    target.add_argument("--branch")
    parser.add_argument("--upstream", required=True, type=Repository.parse)
    parser.add_argument("--fork-owner", required=True)
    parser.add_argument("--failure-logs", action="store_true")


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    """
    Parse the command line.

    :param argv: The arguments to parse, defaulting to the process's own.
    :return: The parsed arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prompt = commands.add_parser(HelperCommand.PROMPT)
    _add_request_arguments(prompt)
    prompt.add_argument(
        "--reference",
        help="the basstler tag or commit the helper runs, defaulting to this one's",
    )
    fetch_parser = commands.add_parser(HelperCommand.FETCH)
    _add_request_arguments(fetch_parser)
    fetch_parser.add_argument("--nonce", required=True)
    report = commands.add_parser(HelperCommand.REPORT)
    report.add_argument("--include-resolved", action="store_true")
    return parser.parse_args(argv)


def _print_output(lines: list[str]) -> None:
    """
    Print the output: a single chunk directly, several as files to print one command
    at a time, since a session keeps only so much of one command's output.

    :param lines: The chunk lines.
    """
    if len(lines) == 1:
        logger.info(lines[0])
        return
    directory = Path(tempfile.mkdtemp(prefix="basstler-upstream-reviews-"))
    commands = [f"{len(lines)} chunks; print each with its own command:"]
    for index, line in enumerate(lines, 1):
        chunk = directory / f"chunk-{index}"
        chunk.write_text(line + "\n")
        commands.append(f"cat {chunk}")
    logger.info("\n".join(commands))


def main(argv: list[str] | None = None) -> int:
    """
    Run one command.

    :param argv: The arguments to parse, defaulting to the process's own.
    :return: The process exit status.
    """
    arguments = _parse_arguments(argv)
    try:
        if arguments.command == HelperCommand.PROMPT:
            request = HelperRequest.from_arguments(arguments)
            prompt = HelperPrompt(
                request, arguments.reference or HelperPrompt.own_reference()
            )
            request.save()
            logger.info(prompt.render())
        elif arguments.command == HelperCommand.FETCH:
            _print_output(
                fetch(HelperRequest.from_arguments(arguments), RecordingClient())
            )
        else:
            request = HelperRequest.load()
            recording = HelperRecording.assemble(
                request.nonce, SessionTranscript.current().chunks(request.nonce)
            )
            logger.info(build_report(request, recording, arguments.include_resolved))
    except UpstreamReadError as failure:
        logger.error(failure)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
