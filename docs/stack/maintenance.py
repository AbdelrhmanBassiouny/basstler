#!/usr/bin/env python3
"""Deterministic executor for the stacked-PR maintenance pass.

``stack.py`` derives what a pass should do and prints it; nothing in it moves a commit.
Every fetch, merge, rebase and push in the workflow was therefore performed by a session
following prose, and ``board.json`` was hand-assembled from whatever the caller happened
to fetch - the same class of hand-assembled input that let a dropped ``merged_at`` field
read as a legitimate value.

This module performs those steps instead, and reports what it did::

    python .claude/stack/maintenance.py board --write     # export the fork's open pull requests
    python .claude/stack/maintenance.py fast-forward      # move the fork's base onto the upstream
    python .claude/stack/maintenance.py restack           # integrate every moved parent
    python .claude/stack/maintenance.py run-report --json # the whole pass as one document

It executes an already-derived plan: structure still comes from ``stack.py`` and from
GitHub's own stack object, and every write GitHub refuses to a session's credential -
a pull request's base branch - stays with the caller.

The exit status is the result. ``run-report --json`` is the machine-readable form, so a
scheduled job with no model in the loop can emit it directly.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import IntEnum, StrEnum
from pathlib import Path

from stack import (
    BOARD_PATH,
    BoardUnavailable,
    CommitMoveAction,
    Configuration,
    AmbiguousForkRemoteError,
    ForkRemoteNotFoundError,
    IntegrationStrategy,
    PreFlight,
    ProposedCommitMove,
    PullRequest,
    RefusalReason,
    Reparent,
    Repository,
    Stack,
    landed_branches,
    load_configuration,
    load_stack,
    promotion_order,
    reparents,
    resolve_ref,
    restack_plan,
)

GITHUB_API_ROOT = "https://api.github.com"
"""Base URL every REST call in this module is built on."""

CREDENTIAL_VARIABLES = ("GH_TOKEN", "GITHUB_TOKEN")
"""Environment variables read, in order, for the token the API calls authenticate with."""

SESSION_LINK_PATTERN = re.compile(r"https://claude\.ai/code/session_[A-Za-z0-9_-]+")
"""Matches the session link a pull request description carries, which is the only
channel for telling a branch's owner that their branch needs them."""


# %% running git


@dataclass
class GitCommandFailed(RuntimeError):
    """Raised when a git command this module depends on the result of fails."""

    arguments: tuple[str, ...]
    """The git subcommand and its arguments, as invoked."""

    exit_status: int
    """The status git exited with."""

    error_output: str
    """What git wrote to stderr."""

    def __str__(self) -> str:
        """:return: The command, its status, and what git said about it."""
        return (
            f"git {' '.join(self.arguments)} exited {self.exit_status}: "
            f"{self.error_output}"
        )


@dataclass(frozen=True)
class GitCommandResult:
    """One finished git command, whether or not it succeeded."""

    exit_status: int
    """The status git exited with."""

    output: str
    """Git's stripped stdout."""

    error_output: str
    """Git's stripped stderr."""

    @property
    def succeeded(self) -> bool:
        """:return: Whether git exited zero."""
        return self.exit_status == 0


@dataclass(frozen=True)
class GitCommandRunner:
    """Runs git in one checkout, reporting failures rather than swallowing them.

    ``stack.py`` reads git through a helper that returns an empty string when a command
    fails. That is right for derivation, where a missing ref simply means "no answer",
    and wrong here: a push that silently did nothing would be indistinguishable from one
    that worked.
    """

    working_directory: Path
    """The checkout every command runs in."""

    def attempt(self, *arguments: str) -> GitCommandResult:
        """Run a command whose failure is an expected outcome.

        :param arguments: The git subcommand and its arguments.
        :return: The finished command.
        """
        completed = subprocess.run(
            ["git", *arguments],
            cwd=self.working_directory,
            capture_output=True,
            text=True,
        )
        return GitCommandResult(
            exit_status=completed.returncode,
            output=completed.stdout.strip(),
            error_output=completed.stderr.strip(),
        )

    def run(self, *arguments: str) -> str:
        """Run a command this module depends on the result of.

        :param arguments: The git subcommand and its arguments.
        :return: Git's stripped stdout.
        :raises GitCommandFailed: If git exits non-zero.
        """
        result = self.attempt(*arguments)
        if not result.succeeded:
            raise GitCommandFailed(arguments, result.exit_status, result.error_output)
        return result.output

    def succeeds(self, *arguments: str) -> bool:
        """Run a command asked only as a question.

        :param arguments: The git subcommand and its arguments.
        :return: Whether git exited zero.
        """
        return self.attempt(*arguments).succeeded


def ancestry_predicate(
    configuration: Configuration, git: GitCommandRunner
) -> Callable[[str, str], bool]:
    """Build the containment test :class:`PreFlight` asks its questions through.

    :param configuration: The resolved configuration naming the fork remote.
    :param git: The runner to ask git through.
    :return: A predicate testing whether a fork branch is contained in a local branch.
    """

    def is_ancestor(candidate: str, descendant: str) -> bool:
        return git.succeeds(
            "merge-base",
            "--is-ancestor",
            resolve_ref(configuration, candidate),
            descendant,
        )

    return is_ancestor


# %% the board export


class PullRequestField(StrEnum):
    """The fields a board entry cannot be derived without.

    Named rather than spelled out at each use so a rejection reports which field was
    missing in the same terms the fetch doc requires it in.
    """

    NUMBER = "number"
    HEAD = "head"
    BASE = "base"
    DRAFT = "draft"
    LABELS = "labels"


@dataclass
class MissingPullRequestFieldError(ValueError):
    """Raised when a fetched pull request omits a field the board is derived from.

    A fetch that drops a field is not partially correct: absent and legitimately empty
    are different facts, and defaulting one to the other is what makes bad board data
    indistinguishable from good.
    """

    field_name: PullRequestField
    """The field that was absent."""

    pull_request_number: int | None
    """The pull request it was absent from, or ``None`` when the number itself is."""

    def __str__(self) -> str:
        """:return: Which field is missing, and from where."""
        subject = (
            f"pull request {self.pull_request_number}"
            if self.pull_request_number is not None
            else "a fetched pull request"
        )
        return (
            f"{subject} has no '{self.field_name}'; the board cannot be derived from a "
            f"fetch that omits it"
        )


def session_link_in(body: str | None) -> str | None:
    """Read the session link out of a pull request description.

    :param body: The description to search, which may be absent.
    :return: The first session link, or ``None`` if the description names none.
    """
    if not body:
        return None
    found = SESSION_LINK_PATTERN.search(body)
    return found.group(0) if found else None


def _required(
    record: Mapping[str, object],
    field_name: PullRequestField,
    pull_request_number: int | None,
) -> object:
    """Read a field that must be present.

    :param record: The fetched pull request.
    :param field_name: The field to read.
    :param pull_request_number: The pull request being read, for the error.
    :return: The field's value.
    :raises MissingPullRequestFieldError: If it is absent or null.
    """
    value = record.get(field_name)
    if value is None:
        raise MissingPullRequestFieldError(field_name, pull_request_number)
    return value


def _branch_reference(
    value: object, field_name: PullRequestField, pull_request_number: int
) -> str:
    """Read a branch name from either the nested API shape or a plain string.

    :param value: The field's value.
    :param field_name: Which field it is, for the error.
    :param pull_request_number: The pull request being read, for the error.
    :return: The branch name.
    :raises MissingPullRequestFieldError: If no branch name can be read from it.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping) and value.get("ref"):
        return str(value["ref"])
    raise MissingPullRequestFieldError(field_name, pull_request_number)


def _label_names(value: object) -> list[str]:
    """Read label names from either the nested API shape or plain strings.

    :param value: The ``labels`` field's value.
    :return: The label names.
    """
    return [
        label if isinstance(label, str) else str(label["name"])
        for label in value  # type: ignore[union-attr]
    ]


@dataclass(frozen=True)
class BoardExport:
    """The fork's open pull requests, in the shape the derived stack is read from."""

    pull_requests: tuple[PullRequest, ...]
    """The exported pull requests."""

    @classmethod
    def from_api_records(cls, records: Iterable[Mapping[str, object]]) -> BoardExport:
        """Build the export from what the REST API returned.

        :param records: The fetched pull requests.
        :return: The export.
        :raises MissingPullRequestFieldError: If any record omits a required field.
        """
        return cls(tuple(cls._pull_request(record) for record in records))

    @staticmethod
    def _pull_request(record: Mapping[str, object]) -> PullRequest:
        """Read one fetched pull request into a board entry.

        :param record: The fetched pull request.
        :return: The board entry.
        :raises MissingPullRequestFieldError: If a required field is absent.
        """
        number = int(_required(record, PullRequestField.NUMBER, None))  # type: ignore[arg-type]
        return PullRequest(
            number=number,
            head=_branch_reference(
                _required(record, PullRequestField.HEAD, number),
                PullRequestField.HEAD,
                number,
            ),
            base=_branch_reference(
                _required(record, PullRequestField.BASE, number),
                PullRequestField.BASE,
                number,
            ),
            draft=bool(_required(record, PullRequestField.DRAFT, number)),
            labels=_label_names(record.get(PullRequestField.LABELS) or []),
            ci=record.get("ci"),  # type: ignore[arg-type]
            session=session_link_in(record.get("body")),  # type: ignore[arg-type]
        )

    def as_json(self) -> str:
        """:return: The export, in the document :func:`stack.load_board` parses."""
        return json.dumps(
            {"pull_requests": [asdict(entry) for entry in self.pull_requests]},
            indent=2,
        )

    def write(self, path: Path = BOARD_PATH) -> Path:
        """Write the export where the derived stack is read from.

        :param path: Where to write it.
        :return: The path written to.
        """
        path.write_text(self.as_json() + "\n")
        return path


# %% fetching the fork's open pull requests


@dataclass
class GitHubCredentialUnavailableError(RuntimeError):
    """Raised when no token is available to authenticate the API calls with."""

    variables: tuple[str, ...]
    """The environment variables that were consulted."""

    def __str__(self) -> str:
        """:return: What was looked for, so the caller can supply it."""
        return (
            f"no GitHub token: set one of {', '.join(self.variables)}, or export the "
            f"board with a caller that has one"
        )


@dataclass(frozen=True)
class OpenPullRequests:
    """Reads a repository's open pull requests straight from the REST API.

    ``gh`` is absent from the environment this normally runs in, so the calls are plain
    authenticated requests rather than a CLI wrapper.
    """

    repository: Repository
    """The repository to read."""

    token: str
    """The credential the requests authenticate with."""

    page_size: int = 100
    """How many pull requests to ask for per request."""

    @classmethod
    def from_environment(cls, repository: Repository) -> OpenPullRequests:
        """Build a reader from whichever credential the environment carries.

        :param repository: The repository to read.
        :return: The reader.
        :raises GitHubCredentialUnavailableError: If no token is set.
        """
        for variable in CREDENTIAL_VARIABLES:
            token = os.environ.get(variable)
            if token:
                return cls(repository, token)
        raise GitHubCredentialUnavailableError(CREDENTIAL_VARIABLES)

    def __call__(self) -> list[Mapping[str, object]]:
        """:return: Every open pull request on the repository, oldest page first."""
        collected: list[Mapping[str, object]] = []
        page = 1
        while True:
            fetched = self._page(page)
            collected.extend(fetched)
            if len(fetched) < self.page_size:
                return collected
            page += 1

    def _page(self, page: int) -> list[Mapping[str, object]]:
        """:param page: Which page to fetch, counting from one.
        :return: That page of open pull requests."""
        query = urllib.parse.urlencode(
            {"state": "open", "per_page": self.page_size, "page": page}
        )
        request = urllib.request.Request(
            f"{GITHUB_API_ROOT}/repos/{self.repository}/pulls?{query}",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())


# %% fast-forwarding the fork's copy of the upstream base


class FastForwardOutcome(StrEnum):
    """What became of the fork's base branch."""

    PUSHED = "pushed"
    """It was moved onto the upstream's tip."""

    ALREADY_CURRENT = "already-current"
    """It already pointed at the upstream's tip."""

    REFUSED_NOT_FAST_FORWARD = "refused-not-fast-forward"
    """It carries commits the upstream does not, so moving it would discard them."""


@dataclass(frozen=True)
class FastForwardReport:
    """What the fast-forward did, and to what."""

    outcome: FastForwardOutcome
    """What became of the fork's base branch."""

    upstream_reference: str
    """The upstream ref the fork's base was compared against."""

    fork_reference: str
    """The fork ref that was to be moved."""

    commit: str
    """The commit the fork's base points at now."""

    explanation: str | None = None
    """Why a refusal was refused, absent when nothing was refused."""


def fast_forward(
    configuration: Configuration, git: GitCommandRunner
) -> FastForwardReport:
    """Move the fork's copy of the upstream base onto the upstream's tip.

    This is what closes the pull requests whose work has landed: GitHub marks one merged
    the moment its head becomes an ancestor of its base. A move that is not a
    fast-forward is refused rather than forced - the fork's base is a mirror of the
    upstream trunk, and anything else on it would flow into every branch above.

    :param configuration: The resolved configuration.
    :param git: The runner to execute through.
    :return: What was done.
    """
    upstream_reference = (
        f"{configuration.upstream_remote}/{configuration.upstream_base}"
    )
    fork_reference = resolve_ref(configuration, configuration.upstream_base)
    git.run(
        "fetch", "--quiet", configuration.upstream_remote, configuration.upstream_base
    )
    git.run("fetch", "--quiet", configuration.fork_remote, configuration.upstream_base)
    upstream_commit = git.run("rev-parse", upstream_reference)
    fork_commit = git.run("rev-parse", fork_reference)

    if upstream_commit == fork_commit:
        return FastForwardReport(
            FastForwardOutcome.ALREADY_CURRENT,
            upstream_reference,
            fork_reference,
            fork_commit,
        )
    if not git.succeeds("merge-base", "--is-ancestor", fork_commit, upstream_commit):
        return FastForwardReport(
            FastForwardOutcome.REFUSED_NOT_FAST_FORWARD,
            upstream_reference,
            fork_reference,
            fork_commit,
            explanation=(
                f"'{fork_reference}' is not contained in '{upstream_reference}', so "
                f"moving it would discard commits; resolve this by hand rather than "
                f"forcing"
            ),
        )
    git.run(
        "push",
        "--quiet",
        configuration.fork_remote,
        f"{upstream_commit}:refs/heads/{configuration.upstream_base}",
    )
    git.run("fetch", "--quiet", configuration.fork_remote, configuration.upstream_base)
    return FastForwardReport(
        FastForwardOutcome.PUSHED,
        upstream_reference,
        fork_reference,
        upstream_commit,
    )


# %% restacking every branch whose parent moved


class RestackOutcome(StrEnum):
    """What became of one branch during a restack."""

    PUSHED = "pushed"
    """Its parent was integrated and the result published."""

    UP_TO_DATE = "up-to-date"
    """Its parent's tip was already contained in it."""

    CONFLICT = "conflict"
    """Its parent could not be integrated cleanly; nothing was published."""

    REFUSED = "refused"
    """Pre-flight refused the push; nothing was published."""

    PUSH_REJECTED = "push-rejected"
    """The fork rejected the push, so the branch moved under this pass; nothing was
    published, and nothing was forced over whatever moved it."""


@dataclass(frozen=True)
class BranchOutcome:
    """What became of one branch, in terms its owner can act on."""

    branch: str
    """The branch this is about."""

    parent: str
    """The branch whose tip was to be integrated into it."""

    strategy: IntegrationStrategy
    """How the parent was to be integrated."""

    outcome: RestackOutcome
    """What became of it."""

    conflicting_paths: tuple[str, ...] = ()
    """The paths that conflicted, empty unless the outcome is a conflict."""

    refusals: tuple[RefusalReason, ...] = ()
    """Why the push was refused, empty unless the outcome is a refusal."""

    pushed_commit: str | None = None
    """The commit published, absent unless the outcome is a push."""

    explanation: str | None = None
    """What the fork said when it rejected the push, absent unless it did."""


def _conflicting_paths(git: GitCommandRunner) -> tuple[str, ...]:
    """:param git: The runner to ask git through.
    :return: The paths left unmerged by the integration that just failed."""
    unmerged = git.attempt("diff", "--name-only", "--diff-filter=U")
    return tuple(path for path in unmerged.output.splitlines() if path)


def _abandon_integration(git: GitCommandRunner, strategy: IntegrationStrategy) -> None:
    """Return the checkout to the state the failed integration started from.

    :param git: The runner to execute through.
    :param strategy: Which integration was attempted.
    """
    git.attempt(
        "rebase" if strategy is IntegrationStrategy.REBASE else "merge", "--abort"
    )


def restack(stack: Stack, git: GitCommandRunner) -> list[BranchOutcome]:
    """Integrate every moved parent, bottom up, and publish what integrated cleanly.

    Pre-flight runs before every push without exception, and a branch is only ever
    force-pushed when its own pull request carries the rebase label - which is what
    makes the strategy, rather than this module's judgement, the thing that authorises
    rewriting somebody's published history. A conflict is reported and left alone: it is
    a change to somebody else's branch, so it is never resolved silently here.

    :param stack: The derived stack, whose plan this executes.
    :param git: The runner to execute through.
    :return: One outcome per branch in the plan, parent before child.
    """
    configuration = stack.configuration
    pre_flight = PreFlight(
        stack=stack,
        checked_out_branch="",
        is_ancestor=ancestry_predicate(configuration, git),
    )
    outcomes: list[BranchOutcome] = []
    for entry in restack_plan(stack):
        outcomes.append(_restack_branch(entry, stack, pre_flight, git))
    return outcomes


def _restack_branch(
    entry: Mapping[str, str],
    stack: Stack,
    pre_flight: PreFlight,
    git: GitCommandRunner,
) -> BranchOutcome:
    """Integrate one branch's parent and publish the result.

    :param entry: One ``restack_plan`` entry: branch, parent and strategy.
    :param stack: The derived stack.
    :param pre_flight: The checks every push is put through.
    :param git: The runner to execute through.
    :return: What became of the branch.
    """
    configuration = stack.configuration
    branch, parent = entry["branch"], entry["parent"]
    strategy = IntegrationStrategy(entry["strategy"])
    branch_reference = resolve_ref(configuration, branch)
    parent_reference = resolve_ref(configuration, parent)

    if git.succeeds("merge-base", "--is-ancestor", parent_reference, branch_reference):
        return BranchOutcome(branch, parent, strategy, RestackOutcome.UP_TO_DATE)

    git.run("checkout", "--quiet", "-B", branch, branch_reference)
    integration = (
        git.attempt("rebase", parent_reference)
        if strategy is IntegrationStrategy.REBASE
        else git.attempt("merge", "--no-edit", parent_reference)
    )
    if not integration.succeeded:
        conflicting = _conflicting_paths(git)
        _abandon_integration(git, strategy)
        return BranchOutcome(
            branch,
            parent,
            strategy,
            RestackOutcome.CONFLICT,
            conflicting_paths=conflicting,
        )

    refusals = pre_flight_refusals(pre_flight, configuration, branch, git)
    if refusals:
        return BranchOutcome(
            branch, parent, strategy, RestackOutcome.REFUSED, refusals=refusals
        )

    push = git.attempt(*push_arguments(configuration, branch, strategy))
    if not push.succeeded:
        return BranchOutcome(
            branch,
            parent,
            strategy,
            RestackOutcome.PUSH_REJECTED,
            explanation=push.error_output,
        )
    git.run("fetch", "--quiet", configuration.fork_remote, branch)
    return BranchOutcome(
        branch,
        parent,
        strategy,
        RestackOutcome.PUSHED,
        pushed_commit=git.run("rev-parse", "HEAD"),
    )


def pre_flight_refusals(
    pre_flight: PreFlight,
    configuration: Configuration,
    branch: str,
    git: GitCommandRunner,
) -> tuple[RefusalReason, ...]:
    """Ask pre-flight whether this branch's push may be made.

    :param pre_flight: The checks, built once for the whole pass.
    :param configuration: The resolved configuration.
    :param branch: The branch about to be pushed.
    :param git: The runner to read the checked-out branch through.
    :return: Every reason to refuse, empty when the push is clear.
    """
    checked_out = PreFlight(
        stack=pre_flight.stack,
        checked_out_branch=git.run("branch", "--show-current"),
        is_ancestor=pre_flight.is_ancestor,
    )
    return tuple(
        refusal.reason
        for refusal in checked_out.refusals(
            ProposedCommitMove(
                action=CommitMoveAction.RESTACK,
                source=branch,
                destination=branch,
                destination_remote=configuration.fork_remote,
            )
        )
    )


def push_arguments(
    configuration: Configuration, branch: str, strategy: IntegrationStrategy
) -> list[str]:
    """Build the push, forcing only where the rebase label authorised it.

    :param configuration: The resolved configuration.
    :param branch: The branch to publish.
    :param strategy: How its parent was integrated.
    :return: The git arguments.
    """
    forcing = ["--force-with-lease"] if strategy is IntegrationStrategy.REBASE else []
    return [
        "push",
        "--quiet",
        *forcing,
        configuration.fork_remote,
        f"{branch}:{branch}",
    ]


# %% the report a caller renders or emits


@dataclass(frozen=True)
class MaintenanceReport:
    """Everything one pass did and everything it leaves for its caller.

    The lists at the end are not this module's work: reparenting needs a base change,
    and promoting needs a description write and a judgement about what to say. They are
    reported here so one document describes the whole pass.
    """

    fast_forward: FastForwardReport | None
    """What became of the fork's base branch, absent when it was not attempted."""

    restacked: tuple[BranchOutcome, ...]
    """What became of each branch in the restack plan."""

    reparents: tuple[Reparent, ...]
    """The children whose base has landed, for the caller to retarget."""

    landed: tuple[str, ...]
    """The branches whose own commits are already in the upstream base."""

    promotable: tuple[str, ...]
    """The branches approved and unblocked, for the caller to promote."""

    def as_json(self) -> str:
        """:return: The report as one machine-readable document."""
        return json.dumps(asdict(self), indent=2)

    @property
    def needs_attention(self) -> bool:
        """:return: Whether any branch was left unpublished for somebody to look at."""
        return any(
            outcome.outcome is not RestackOutcome.PUSHED
            and outcome.outcome is not RestackOutcome.UP_TO_DATE
            for outcome in self.restacked
        )


def build_report(
    stack: Stack,
    fast_forward_report: FastForwardReport | None,
    restacked: Sequence[BranchOutcome],
) -> MaintenanceReport:
    """Assemble one pass's outcomes and its leftovers into a single report.

    :param stack: The derived stack, read for what the caller still has to do.
    :param fast_forward_report: What became of the fork's base branch, if attempted.
    :param restacked: What became of each branch in the restack plan.
    :return: The report.
    """
    return MaintenanceReport(
        fast_forward=fast_forward_report,
        restacked=tuple(restacked),
        reparents=tuple(reparents(stack)),
        landed=tuple(branch.name for branch in landed_branches(stack)),
        promotable=tuple(branch.name for branch in promotion_order(stack)),
    )


# %% printing


def print_board_export(export: BoardExport, written_to: Path | None) -> None:
    """Report what the export contains, and where it went.

    :param export: The export.
    :param written_to: Where it was written, or ``None`` when it was only printed.
    """
    if written_to is None:
        print(export.as_json())
        return
    print(f"{len(export.pull_requests)} open pull request(s) -> {written_to}")


def print_fast_forward(report: FastForwardReport) -> None:
    """:param report: What became of the fork's base branch."""
    print(f"{report.fork_reference}\t{report.outcome}\t{report.commit}")
    if report.explanation:
        print(report.explanation, file=sys.stderr)


def print_restack(outcomes: Sequence[BranchOutcome]) -> None:
    """:param outcomes: What became of each branch."""
    for outcome in outcomes:
        detail = (
            ",".join(outcome.conflicting_paths)
            or ",".join(outcome.refusals)
            or outcome.pushed_commit
            or outcome.explanation
            or ""
        )
        print(f"{outcome.branch}\t{outcome.outcome}\t{detail}")


# %% entry point


class Command(StrEnum):
    """Every command this executor answers, named once so no caller spells one out."""

    BOARD = "board"
    FAST_FORWARD = "fast-forward"
    RESTACK = "restack"
    RUN_REPORT = "run-report"

    @property
    def needs_a_board(self) -> bool:
        """Whether answering this command means reading the derived stack.

        :return: Whether ``board.json`` must exist.
        """
        return self is not Command.BOARD


class MaintenanceExitCode(IntEnum):
    """What this executor's exit status tells a caller.

    The first five match :class:`stack.ExitCode` value for value and meaning, so a
    caller acting on the two tools' statuses never has to remember which produced one.
    """

    SUCCESS = 0
    """The command ran and did what it reports."""

    USAGE = 2
    """No such command, or the wrong arguments."""

    BOARD_UNAVAILABLE = 3
    """``board.json`` is missing, so the stack cannot be derived."""

    REMOTES_UNRESOLVED = 4
    """The fork could not be identified from this checkout's remotes."""

    PREFLIGHT_REFUSED = 5
    """A push was refused; the reasons are in the report."""

    GIT_COMMAND_FAILED = 6
    """A git command the run depended on failed; nothing further was attempted."""

    NOT_FAST_FORWARD = 7
    """The fork's base carries commits the upstream does not."""

    CREDENTIAL_UNAVAILABLE = 8
    """No GitHub token is set, so the board cannot be fetched."""


def _argument_parser() -> argparse.ArgumentParser:
    """:return: The parser for every command and its own flags."""
    parser = argparse.ArgumentParser(
        prog="maintenance.py",
        description="Stacked-PR maintenance: perform the pass, report what happened.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    board = commands.add_parser(
        Command.BOARD, help="export the fork's open pull requests"
    )
    board.add_argument(
        "--write",
        action="store_true",
        help="write board.json rather than printing the export",
    )
    commands.add_parser(
        Command.FAST_FORWARD, help="move the fork's base branch onto the upstream"
    )
    commands.add_parser(
        Command.RESTACK, help="integrate every moved parent and publish the result"
    )
    report = commands.add_parser(
        Command.RUN_REPORT, help="perform the whole pass and report it"
    )
    report.add_argument(
        "--json",
        action="store_true",
        help="emit the machine-readable document rather than a summary",
    )
    return parser


def _run_board(configuration: Configuration, write: bool) -> MaintenanceExitCode:
    """Fetch the fork's open pull requests and export them.

    :param configuration: The resolved configuration naming the fork.
    :param write: Whether to write ``board.json`` rather than print the export.
    :return: The process exit code.
    """
    export = BoardExport.from_api_records(
        OpenPullRequests.from_environment(configuration.fork_repository)()
    )
    print_board_export(export, export.write() if write else None)
    return MaintenanceExitCode.SUCCESS


def _run_fast_forward(
    configuration: Configuration, git: GitCommandRunner
) -> MaintenanceExitCode:
    """:param configuration: The resolved configuration.
    :param git: The runner to execute through.
    :return: The process exit code."""
    report = fast_forward(configuration, git)
    print_fast_forward(report)
    if report.outcome is FastForwardOutcome.REFUSED_NOT_FAST_FORWARD:
        return MaintenanceExitCode.NOT_FAST_FORWARD
    return MaintenanceExitCode.SUCCESS


def _run_restack(stack: Stack, git: GitCommandRunner) -> MaintenanceExitCode:
    """:param stack: The derived stack.
    :param git: The runner to execute through.
    :return: The process exit code."""
    outcomes = restack(stack, git)
    print_restack(outcomes)
    if any(outcome.outcome is RestackOutcome.REFUSED for outcome in outcomes):
        return MaintenanceExitCode.PREFLIGHT_REFUSED
    return MaintenanceExitCode.SUCCESS


def _run_report(
    stack: Stack, git: GitCommandRunner, as_json: bool
) -> MaintenanceExitCode:
    """Perform the whole pass and report it.

    :param stack: The derived stack.
    :param git: The runner to execute through.
    :param as_json: Whether to emit the machine-readable document.
    :return: The process exit code.
    """
    fast_forward_report = fast_forward(stack.configuration, git)
    report = build_report(stack, fast_forward_report, restack(stack, git))
    if as_json:
        print(report.as_json())
    else:
        print_fast_forward(fast_forward_report)
        print_restack(report.restacked)
    if report.needs_attention:
        return MaintenanceExitCode.PREFLIGHT_REFUSED
    return MaintenanceExitCode.SUCCESS


def main() -> MaintenanceExitCode:
    """Dispatch the command-line invocation, mapping every refusal to its own status.

    :return: The process exit code.
    """
    arguments = _argument_parser().parse_args()
    command = Command(arguments.command)
    git = GitCommandRunner(working_directory=Path.cwd())
    try:
        configuration = load_configuration()
        if command is Command.BOARD:
            return _run_board(configuration, arguments.write)
        if command is Command.FAST_FORWARD:
            return _run_fast_forward(configuration, git)
        stack = load_stack()
        if command is Command.RESTACK:
            return _run_restack(stack, git)
        return _run_report(stack, git, arguments.json)
    except (ForkRemoteNotFoundError, AmbiguousForkRemoteError) as error:
        print(f"{error}", file=sys.stderr)
        return MaintenanceExitCode.REMOTES_UNRESOLVED
    except BoardUnavailable as error:
        print(f"{error}", file=sys.stderr)
        return MaintenanceExitCode.BOARD_UNAVAILABLE
    except GitHubCredentialUnavailableError as error:
        print(f"{error}", file=sys.stderr)
        return MaintenanceExitCode.CREDENTIAL_UNAVAILABLE
    except MissingPullRequestFieldError as error:
        print(f"{error}", file=sys.stderr)
        return MaintenanceExitCode.USAGE
    except GitCommandFailed as error:
        print(f"{error}", file=sys.stderr)
        return MaintenanceExitCode.GIT_COMMAND_FAILED


if __name__ == "__main__":
    sys.exit(main())
