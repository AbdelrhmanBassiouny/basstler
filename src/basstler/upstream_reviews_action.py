#!/usr/bin/env python3
"""
Read an upstream pull request through the fork's own Actions, from a branch of its own.

The fork carries one branch, :attr:`ActionBranch.NAME`, sharing no history with its
other branches and holding nothing but a workflow calling basstler's reusable one, a
short README, the latest request and the latest result. Pushing a new request is what
starts a run - a push runs the workflow file on the pushed branch, so the fork's default
branch never carries a basstler file, and nothing needs a dispatch permission. The run
reads the upstream over GraphQL, records every response, and commits the recording back
to the same branch; the session fetches it and replays it through
:class:`UpstreamPullRequestReader`, so the report is exactly what a direct read renders.

Commands::

    # once, and again after each basstler upgrade (setup_steps runs it)
    python -m basstler.upstream_reviews_action install --branch-or-tag vX.Y.Z
    # what check-setup.sh reports: missing, stale <branch or tag> or current
    python -m basstler.upstream_reviews_action status --branch-or-tag vX.Y.Z
    # request a read, wait for the run, print the report
    python -m basstler.upstream_reviews_action read --upstream O/N --fork-owner F \\
        (--pull-request N | --branch B) [--failure-logs] [--include-resolved]
    # on the runner: answer the branch's request
    python -m basstler.upstream_reviews_action run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from abc import ABC
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from basstler.exit_codes import ExitCode
from basstler.repository import MalformedRepositoryError, Repository
from basstler.standard_streams import StandardStreamHandler
from basstler.upstream_reviews import (
    FailureLogReader,
    GitHubCommandFailed,
    GitHubCommandLineClient,
    GraphQLClient,
    JobLogReader,
    JSONModel,
    RestClient,
    UpstreamPullRequestReader,
    UpstreamPullRequestReport,
    UpstreamReadError,
)
from basstler.upstream_reviews_helper import HelperRequest, RecordedJobLog

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its commands print through.
"""

INSTALL_COMMAND = (
    "python -m basstler.setup_steps install-upstream-reviews-action "
    "--branch-or-tag <the basstler release the session runs> (/setup-personal-notes "
    "runs it)"
)
"""
How a reader is told to install or update the Action.
"""


class ActionExitCode(ExitCode):
    """
    What ``read``'s exit status tells the skill.
    """

    SUCCESS = 0
    """
    The report was printed.
    """

    READ_FAILED = 1
    """
    The read itself failed - the branch was never promoted, say - which is the answer.
    """

    USAGE = 2
    """
    The wrong arguments.
    """

    UNAVAILABLE = 3
    """
    The fork's Action could not answer, so the skill reads the upstream another way.
    """


# %% errors


class ActionUnavailable(UpstreamReadError, ABC):
    """
    Raised when the fork's Action cannot answer at all, as opposed to answering that
    the read failed.
    """


@dataclass
class GitCommandFailed(UpstreamReadError):
    """
    Raised when a git command this module runs exits non-zero.
    """

    arguments: list[str]
    """
    What git was given.
    """

    error_output: str
    """
    What it wrote to standard error.
    """

    def describe(self) -> str:
        """:return: The message a caller should see."""
        return f"git {' '.join(self.arguments)} failed: {self.error_output}"


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
            f"{INSTALL_COMMAND}"
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

    nonce: str
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
            f"no result for request {self.nonce} after {self.waited} s. Either Actions "
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
            f"basstler release differs from this one; re-run {INSTALL_COMMAND}"
        )


# %% the branch


class ActionBranch(StrEnum):
    """
    Where the Action lives in the fork.
    """

    NAME = "basstler/upstream-reviews"
    """
    The branch, outside both the fork's default branch and the ``claude/`` branches
    stack maintenance owns.
    """

    LOCAL_REFERENCE = "refs/basstler/upstream-reviews"
    """
    Where a fetch of it is kept, so it never moves ``FETCH_HEAD`` under anyone else.
    """


class ActionFile(StrEnum):
    """
    Every file on the branch.
    """

    WORKFLOW = ".github/workflows/upstream-reviews.yml"
    README = "README.md"
    REQUEST = "request.json"
    RESULT = "result.json"

    @property
    def file_name(self) -> str:
        """:return: The file's own name, without its directory."""
        return Path(self.value).name


class BasstlerSource(StrEnum):
    """
    Where the reusable workflow and the package a run installs come from.
    """

    REPOSITORY = "AbdelrhmanBassiouny/basstler"
    REUSABLE_WORKFLOW = ".github/workflows/upstream-reviews-action.yml"


WORKFLOW_TEMPLATE = """\
# Written by basstler's /setup-personal-notes (python -m basstler.setup_steps
# install-upstream-reviews-action); re-run that to update it rather than editing it here.
name: Upstream reviews

on:
  push:
    branches: [{branch}]
    paths: [{request}]

permissions:
  contents: write

concurrency:
  group: basstler-upstream-reviews
  cancel-in-progress: false

jobs:
  read:
    uses: {repository}/{reusable_workflow}@{branch_or_tag}
    with:
      basstler_branch_or_tag: {branch_or_tag}
"""
"""
The caller workflow, filled in by :meth:`ActionInstallation.workflow`.
"""

README_TEXT = f"""\
# basstler upstream reviews

Kept by basstler's `/upstream-reviews` skill. Pushing a new `{ActionFile.REQUEST}` runs
`{ActionFile.WORKFLOW}`, which reads the upstream pull request it names and commits
`{ActionFile.RESULT}`. Nothing on this branch is ever merged anywhere.

Install or update it with `/setup-personal-notes`, which runs
`python -m basstler.setup_steps install-upstream-reviews-action`.
"""
"""
What a reader browsing the fork's branches finds there.
"""

WORKFLOW_REFERENCE = re.compile(
    r"^\s*basstler_branch_or_tag:\s*(?P<branch_or_tag>\S+)\s*$", re.MULTILINE
)
"""
The line of an installed workflow naming the basstler branch or tag it runs.
"""


@dataclass(frozen=True)
class Git:
    """
    Runs git in one clone.
    """

    project_root: Path
    """
    The clone.
    """

    def run(
        self,
        *arguments: str,
        environment: dict[str, str] | None = None,
        check: bool = True,
    ) -> str:
        """
        :param arguments: What to pass git.
        :param environment: Variables to add to the process's own.
        :param check: Whether a non-zero exit is an error.
        :return: What git printed, stripped.
        :raises GitCommandFailed: If it exits non-zero and *check* is set.
        """
        completed = subprocess.run(
            ["git", *arguments],
            cwd=self.project_root,
            capture_output=True,
            text=True,
            env={**os.environ, **(environment or {})},
        )
        if check and completed.returncode != 0:
            raise GitCommandFailed(list(arguments), completed.stderr.strip())
        return completed.stdout.strip() if completed.returncode == 0 else ""


@dataclass(frozen=True)
class RemoteBranch:
    """
    The Action branch on one remote, read and written without touching the working tree.
    """

    git: Git
    """
    The clone to work in.
    """

    remote: str
    """
    The fork's remote.
    """

    @property
    def fork(self) -> Repository | None:
        """
        :return: The repository the remote points at, ``None`` when it names none - a
            remote given as a local path.
        """
        url = self.git.run("remote", "get-url", self.remote, check=False) or self.remote
        try:
            return Repository.from_remote_url(url)
        except MalformedRepositoryError:
            return None

    @property
    def description(self) -> str:
        """:return: The fork's name, or the remote's where it names none."""
        fork = self.fork
        return fork.full_name if fork else self.remote

    def fetch(self) -> str | None:
        """
        :return: The branch's tip commit, or ``None`` when the remote has no such branch.
        """
        if not self.git.run(
            "ls-remote", "--heads", self.remote, ActionBranch.NAME, check=False
        ):
            return None
        self.git.run(
            "fetch",
            "--quiet",
            "--no-tags",
            self.remote,
            f"+refs/heads/{ActionBranch.NAME}:{ActionBranch.LOCAL_REFERENCE}",
        )
        return self.git.run("rev-parse", ActionBranch.LOCAL_REFERENCE)

    def read(self, commit: str, path: ActionFile) -> str | None:
        """
        :param commit: The commit to read from.
        :param path: The file.
        :return: Its text, or ``None`` when the commit has no such file.
        """
        shown = subprocess.run(
            ["git", "show", f"{commit}:{path}"],
            cwd=self.git.project_root,
            capture_output=True,
            text=True,
        )
        return shown.stdout if shown.returncode == 0 else None

    def commit(
        self, parent: str | None, files: dict[ActionFile, str], message: str
    ) -> str:
        """
        Commit files on top of the branch, keeping every file not given.

        :param parent: The commit to build on, ``None`` for the branch's first.
        :param files: What to write, by path.
        :param message: The commit message.
        :return: The new commit.
        """
        with tempfile.TemporaryDirectory() as scratch:
            index = {"GIT_INDEX_FILE": str(Path(scratch) / "index")}
            if parent is None:
                self.git.run("read-tree", "--empty", environment=index)
            else:
                self.git.run("read-tree", parent, environment=index)
            for path, text in files.items():
                blob_file = Path(scratch) / "blob"
                blob_file.write_text(text)
                blob = self.git.run("hash-object", "-w", str(blob_file))
                self.git.run(
                    "update-index",
                    "--add",
                    "--cacheinfo",
                    f"100644,{blob},{path}",
                    environment=index,
                )
            tree = self.git.run("write-tree", environment=index)
        parents = ["-p", parent] if parent else []
        return self.git.run("commit-tree", tree, *parents, "-m", message)

    def push(self, commit: str) -> None:
        """
        Move the branch to *commit*, which has to descend from where it is now.

        :param commit: The new tip.
        """
        self.git.run(
            "push", "--quiet", self.remote, f"{commit}:refs/heads/{ActionBranch.NAME}"
        )

    def write(self, files: dict[ActionFile, str], message: str) -> str:
        """
        Commit files onto the branch's latest tip and push them, once more if a run's
        own commit landed first.

        :param files: What to write, by path.
        :param message: The commit message.
        :return: The pushed commit.
        """
        for attempt in range(3):
            commit = self.commit(self.fetch(), files, message)
            try:
                self.push(commit)
                return commit
            except GitCommandFailed:
                if attempt == 2:
                    raise
        raise AssertionError("unreachable")


# %% installing


class InstallationState(StrEnum):
    """
    How the fork's Action compares with the release installing it.
    """

    MISSING = "missing"
    STALE = "stale"
    CURRENT = "current"


@dataclass(frozen=True)
class ActionInstallation:
    """
    The Action as one basstler release writes it.
    """

    branch_or_tag: str
    """
    The basstler branch or release tag the workflow runs.
    """

    @property
    def workflow(self) -> str:
        """:return: The caller workflow."""
        return WORKFLOW_TEMPLATE.format(
            branch=ActionBranch.NAME,
            request=ActionFile.REQUEST,
            repository=BasstlerSource.REPOSITORY,
            reusable_workflow=BasstlerSource.REUSABLE_WORKFLOW,
            branch_or_tag=self.branch_or_tag,
        )

    @property
    def files(self) -> dict[ActionFile, str]:
        """:return: What installing writes."""
        return {ActionFile.WORKFLOW: self.workflow, ActionFile.README: README_TEXT}

    def state(self, branch: RemoteBranch) -> tuple[InstallationState, str | None]:
        """
        :param branch: The fork's branch.
        :return: How it compares, and the branch or tag it runs when it is installed at
            all.
        """
        tip = branch.fetch()
        workflow = branch.read(tip, ActionFile.WORKFLOW) if tip else None
        if workflow is None:
            return InstallationState.MISSING, None
        match = WORKFLOW_REFERENCE.search(workflow)
        installed = match["branch_or_tag"] if match else None
        if workflow == self.workflow:
            return InstallationState.CURRENT, installed
        return InstallationState.STALE, installed

    def install(self, branch: RemoteBranch) -> bool:
        """
        :param branch: The fork's branch.
        :return: Whether anything had to be pushed.
        """
        if self.state(branch)[0] is InstallationState.CURRENT:
            return False
        branch.write(
            self.files, f"Run basstler {self.branch_or_tag}'s upstream-reviews Action"
        )
        return True


# %% the recording


class ActionJSONKey(StrEnum):
    """
    Every field name in a result.
    """

    NONCE = "nonce"
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

    nonce: str
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
            nonce=data[ActionJSONKey.NONCE],
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
            ActionJSONKey.NONCE: self.nonce,
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
        """See :meth:`GraphQLClient.execute`."""
        data = self.client.execute(query, variables)
        self.responses.append(
            RecordedGraphQLResponse(query_digest(query), variables, data)
        )
        return data

    def read_job_log(self, repository: Repository, job_identifier: int) -> str:
        """See :meth:`JobLogReader.read_job_log`."""
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
        """See :meth:`GraphQLClient.execute`."""
        digest = query_digest(query)
        for response in self.result.responses:
            if response.query == digest and response.variables == variables:
                return response.data
        raise ActionResponseMissing(digest)

    def read_job_log(self, repository: Repository, job_identifier: int) -> str:
        """See :meth:`JobLogReader.read_job_log`."""
        for log in self.result.job_logs:
            if log.job == job_identifier:
                return log.log
        raise ActionResponseMissing(repository.job_log_path(job_identifier))


def read_upstream(
    client: GraphQLClient | JobLogReader, request: HelperRequest, include_resolved: bool
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


def answer(request: HelperRequest, client: GitHubCommandLineClient) -> ActionResult:
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
        return ActionResult(request.nonce, error=str(failure))
    return ActionResult(request.nonce, None, recording.responses, recording.job_logs)


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

    request: HelperRequest
    """
    The read.
    """

    runs: RestClient | None = None
    """
    What lists the fork's runs, so a run that never started or already failed is
    told apart from one still going; ``None`` waits for the result alone.
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
            f"Request upstream reviews {self.request.nonce}",
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
                    self.request.nonce, self.branch.fork, int(timeout)
                )
            time.sleep(self.poll_interval)

    def collect(self) -> ActionResult | None:
        """:return: The result on the branch, when it answers this request."""
        tip = self.branch.fetch()
        text = self.branch.read(tip, ActionFile.RESULT) if tip else None
        if text is None:
            return None
        result = ActionResult.from_json(json.loads(text))
        return result if result.nonce == self.request.nonce else None

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


# %% command line


class ActionCommand(StrEnum):
    """
    The module's commands.
    """

    INSTALL = "install"
    """
    Write the Action branch, or bring it to this release.
    """

    STATUS = "status"
    """
    Print whether the Action branch is missing, stale or current.
    """

    READ = "read"
    """
    Request a read, wait for its result and print the report.
    """

    RUN = "run"
    """
    On the runner: answer the branch's request.
    """


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    """
    Parse the command line.

    :param argv: The arguments to parse, defaulting to the process's own.
    :return: The parsed arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--remote", default="origin", help="the fork's remote")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in (ActionCommand.INSTALL, ActionCommand.STATUS):
        subcommand = commands.add_parser(command)
        subcommand.add_argument(
            "--branch-or-tag",
            required=True,
            help="the basstler branch or release tag the workflow runs",
        )
    read = commands.add_parser(ActionCommand.READ)
    target = read.add_mutually_exclusive_group(required=True)
    target.add_argument("--pull-request", type=int)
    target.add_argument("--branch")
    read.add_argument("--upstream", required=True, type=Repository.parse)
    read.add_argument("--fork-owner", required=True)
    read.add_argument("--failure-logs", action="store_true")
    read.add_argument("--include-resolved", action="store_true")
    read.add_argument(
        "--timeout", type=float, default=480, help="seconds to wait for the run"
    )
    run = commands.add_parser(ActionCommand.RUN)
    run.add_argument("--request", type=Path, default=Path(ActionFile.REQUEST))
    run.add_argument("--result", type=Path, default=Path(ActionFile.RESULT))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """
    Run one command.

    :param argv: The arguments to parse, defaulting to the process's own.
    :return: The process exit status.
    """
    arguments = _parse_arguments(argv)
    try:
        if arguments.command == ActionCommand.RUN:
            request = HelperRequest.from_json(json.loads(arguments.request.read_text()))
            result = answer(request, GitHubCommandLineClient())
            arguments.result.write_text(json.dumps(result.to_json()) + "\n")
            return 0
        branch = RemoteBranch(Git(arguments.project_root), arguments.remote)
        if arguments.command == ActionCommand.INSTALL:
            installation = ActionInstallation(arguments.branch_or_tag)
            changed = installation.install(branch)
            logger.info(
                f"{ActionBranch.NAME} on {branch.description} "
                f"{'now runs' if changed else 'already runs'} basstler {arguments.branch_or_tag}"
            )
            return 0
        if arguments.command == ActionCommand.STATUS:
            state, installed = ActionInstallation(arguments.branch_or_tag).state(branch)
            logger.info(f"{state} {installed}" if installed else state)
            return 0
        action_read = ActionRead(
            branch, HelperRequest.from_arguments(arguments), GitHubCommandLineClient()
        )
        commit = action_read.send()
        result = action_read.wait(arguments.timeout, commit)
        logger.info(action_read.report(result, arguments.include_resolved))
    except ActionUnavailable as failure:
        logger.error(failure)
        return ActionExitCode.UNAVAILABLE
    except UpstreamReadError as failure:
        logger.error(failure)
        return ActionExitCode.READ_FAILED
    return ActionExitCode.SUCCESS


if __name__ == "__main__":
    sys.exit(main())
