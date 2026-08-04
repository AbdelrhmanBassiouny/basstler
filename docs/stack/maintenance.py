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
    python .claude/stack/maintenance.py restack           # integrate every moved parent, report every conflict
    python .claude/stack/maintenance.py promote           # record the upstream link on every ready branch
    python .claude/stack/maintenance.py run-report --json # the whole pass as one document

It executes an already-derived plan: structure still comes from ``stack.py`` and from
GitHub's own stack object. Retargeting a pull request's **base branch** is the one write
GitHub refuses to the credential this runs on - probed directly, alongside the label,
comment and description writes it does allow - so that step alone is reported for the
caller to perform through the GitHub MCP server.

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
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Protocol

from stack import (
    BOARD_PATH,
    AmbiguousForkRemoteError,
    BoardUnavailable,
    Branch,
    BranchStatus,
    CommitMoveAction,
    Configuration,
    ContradictoryLabelWriteError,
    ForkRemoteNotFoundError,
    IntegrationStrategy,
    LabelWrite,
    PreFlight,
    PromotionLink,
    PromotionLinkTooLongError,
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


# %% reading and writing the fork's pull requests


@dataclass
class GitHubCredentialUnavailableError(RuntimeError):
    """Raised when no token is available to authenticate the API calls with."""

    variables: tuple[str, ...]
    """The environment variables that were consulted."""

    def __str__(self) -> str:
        """:return: What was looked for, so the caller can supply it."""
        return (
            f"no GitHub token: set one of {', '.join(self.variables)}, or run this "
            f"with a caller that has one"
        )


class PullRequestReader(Protocol):
    """Reading the pull-request state a pass derives from."""

    def open_pull_requests(self) -> list[Mapping[str, object]]:
        """:return: Every open pull request on the fork."""

    def pull_request(self, number: int) -> Mapping[str, object]:
        """:param number: The pull request to read.
        :return: That pull request."""


class PullRequestWriter(Protocol):
    """The three writes a pass makes, each one probed against the live API first.

    Every one of them is available to the credential a session carries; a pull request's
    *base branch* is the single write that is not, which is why reparenting is the
    caller's job and none of this is.
    """

    def replace_labels(self, number: int, labels: Sequence[str]) -> None:
        """:param number: The pull request to write.
        :param labels: The complete label set it must end up with."""

    def add_comment(self, number: int, body: str) -> str:
        """:param number: The pull request to comment on.
        :param body: The comment.
        :return: The comment's URL."""

    def set_description(self, number: int, body: str) -> None:
        """:param number: The pull request to write.
        :param body: The new description."""


@dataclass
class GitHubRequestFailed(RuntimeError):
    """Raised when the API refuses a call this module depends on."""

    method: str
    """The HTTP method used."""

    path: str
    """The API path called, without the host."""

    status: int
    """The status the API answered with."""

    detail: str
    """What the API said about it."""

    def __str__(self) -> str:
        """:return: The call, its status, and the reason given."""
        return f"{self.method} {self.path} answered {self.status}: {self.detail}"


@dataclass(frozen=True)
class GitHubRepository:
    """Every pull-request call this executor makes, against one repository.

    ``gh`` is absent from the environment this normally runs in, so the calls are plain
    authenticated requests rather than a CLI wrapper.
    """

    repository: Repository
    """The repository to read and write."""

    token: str
    """The credential the requests authenticate with."""

    page_size: int = 100
    """How many pull requests to ask for per request."""

    @classmethod
    def from_environment(cls, repository: Repository) -> GitHubRepository:
        """Build a client from whichever credential the environment carries.

        :param repository: The repository to read and write.
        :return: The client.
        :raises GitHubCredentialUnavailableError: If no token is set.
        """
        for variable in CREDENTIAL_VARIABLES:
            token = os.environ.get(variable)
            if token:
                return cls(repository, token)
        raise GitHubCredentialUnavailableError(CREDENTIAL_VARIABLES)

    def open_pull_requests(self) -> list[Mapping[str, object]]:
        """:return: Every open pull request on the repository, oldest page first."""
        collected: list[Mapping[str, object]] = []
        page = 1
        while True:
            query = urllib.parse.urlencode(
                {"state": "open", "per_page": self.page_size, "page": page}
            )
            fetched = self._call("GET", f"/pulls?{query}")
            collected.extend(fetched)
            if len(fetched) < self.page_size:
                return collected
            page += 1

    def pull_request(self, number: int) -> Mapping[str, object]:
        """:param number: The pull request to read.
        :return: That pull request."""
        return self._call("GET", f"/pulls/{number}")

    def replace_labels(self, number: int, labels: Sequence[str]) -> None:
        """Write a pull request's complete label set.

        :param number: The pull request to write.
        :param labels: The complete set it must end up with, computed by
            :meth:`stack.LabelWrite.replacing` - this call replaces rather than adds.
        """
        self._call("PUT", f"/issues/{number}/labels", {"labels": list(labels)})

    def add_comment(self, number: int, body: str) -> str:
        """:param number: The pull request to comment on.
        :param body: The comment.
        :return: The comment's URL."""
        created = self._call("POST", f"/issues/{number}/comments", {"body": body})
        return str(created["html_url"])

    def set_description(self, number: int, body: str) -> None:
        """Rewrite a pull request's description and nothing else.

        :param number: The pull request to write.
        :param body: The new description.
        """
        self._call("PATCH", f"/pulls/{number}", {"body": body})

    def _call(
        self, method: str, path: str, payload: Mapping[str, object] | None = None
    ) -> object:
        """Make one authenticated API call.

        :param method: The HTTP method.
        :param path: The path below the repository, starting with a slash.
        :param payload: The JSON body, absent for a read.
        :return: The decoded response.
        :raises GitHubRequestFailed: If the API answers with an error status.
        """
        request = urllib.request.Request(
            f"{GITHUB_API_ROOT}/repos/{self.repository}{path}",
            method=method,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as refused:
            raise GitHubRequestFailed(
                method, path, refused.code, refused.read().decode(errors="replace")
            ) from refused


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

    WITHHELD = "withheld"
    """It is still conflicted against its base from a previous pass, so it was left
    untouched rather than re-reported."""


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

    reported_at: str | None = None
    """URL of the comment telling this branch's owner about it, absent unless one was
    posted."""


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


CONFLICT_COMMENT_PREFIX = "🔴 ROUTINE - NEEDS RESOLUTION:"
"""Opens the comment a conflict is reported in, so the branch's owner can find every one
of them at a glance."""

MERGEABLE_STATE_WITH_CONFLICTS = "dirty"
"""The one ``mergeable_state`` meaning a branch genuinely conflicts with its base.
Everything else - ``clean``, ``unstable``, ``blocked``, ``behind``, ``has_hooks``,
``unknown`` - means there are no conflicts, whatever else may be true of it."""


def conflict_report(
    branch: Branch, conflicting_paths: Sequence[str], parent: str
) -> str:
    """Write the comment telling a branch's owner that their branch needs them.

    :param branch: The branch that could not be integrated.
    :param conflicting_paths: The paths that conflicted.
    :param parent: The branch whose tip was being integrated.
    :return: The comment body.
    """
    files = "\n".join(f"- `{path}`" for path in conflicting_paths)
    addressed = (
        f"\n\n{branch.session}"
        if branch.session
        else "\n\nThis pull request's description names no session to address."
    )
    return (
        f"{CONFLICT_COMMENT_PREFIX} integrating `{parent}` into `{branch.name}` "
        f"conflicts, so this branch was left untouched and skipped.\n\n"
        f"Conflicting files:\n{files}\n\n"
        f"Please resolve and push. This branch is labelled "
        f"`needs-resolution` so later passes skip it rather than re-reporting the same "
        f"conflict; the label is cleared automatically once it merges cleanly again, "
        f"and the branch rejoins the pass.{addressed}"
    )


def restack(
    stack: Stack, git: GitCommandRunner, fork: PullRequestReader | PullRequestWriter
) -> list[BranchOutcome]:
    """Integrate every moved parent, bottom up, and publish what integrated cleanly.

    Pre-flight runs before every push without exception, and a branch is only ever
    force-pushed when its own pull request carries the rebase label - which is what
    makes the strategy, rather than this module's judgement, the thing that authorises
    rewriting somebody's published history.

    A conflict is never resolved here - it is a change to somebody else's branch. It is
    reported to that branch's owner in a comment and labelled, so the next pass skips it
    instead of re-reporting it, and the label is cleared again as soon as the branch
    merges cleanly.

    :param stack: The derived stack, whose plan this executes.
    :param git: The runner to execute through.
    :param fork: The fork, read for conflict state and written to when reporting.
    :return: One outcome per branch in the plan, parent before child.
    """
    configuration = stack.configuration
    pre_flight = PreFlight(
        stack=stack,
        checked_out_branch="",
        is_ancestor=ancestry_predicate(configuration, git),
    )
    by_name = {branch.name: branch for branch in stack.branches}
    outcomes: list[BranchOutcome] = []
    for entry in restack_plan(stack):
        outcomes.append(_restack_branch(entry, stack, by_name, pre_flight, git, fork))
    return outcomes


def _withhold(
    branch: Branch, stack: Stack, fork: PullRequestReader | PullRequestWriter
) -> bool:
    """Decide whether a branch delegated for conflict resolution is still conflicted.

    Clears the label as a side effect when it is not, since that is what lets the branch
    rejoin the pass without anybody remembering to remove it by hand.

    :param branch: The branch to judge.
    :param stack: The derived stack, for the label name.
    :param fork: The fork, read for the conflict state and written to clear the label.
    :return: Whether to leave the branch alone this pass.
    """
    label = stack.configuration.needs_resolution_label
    if label not in branch.labels:
        return False
    state = fork.pull_request(branch.pull_request_number).get("mergeable_state")
    if state == MERGEABLE_STATE_WITH_CONFLICTS:
        return True
    fork.replace_labels(
        branch.pull_request_number,
        LabelWrite.replacing(branch.labels, removed=[label]).labels,
    )
    return False


def _report_conflict(
    branch: Branch,
    parent: str,
    conflicting_paths: Sequence[str],
    stack: Stack,
    fork: PullRequestReader | PullRequestWriter,
) -> str:
    """Tell a branch's owner about a conflict, and label it so the next pass skips it.

    :param branch: The branch that could not be integrated.
    :param parent: The branch whose tip was being integrated.
    :param conflicting_paths: The paths that conflicted.
    :param stack: The derived stack, for the label name.
    :param fork: The fork to write to.
    :return: The URL of the comment posted.
    """
    fork.replace_labels(
        branch.pull_request_number,
        LabelWrite.replacing(
            branch.labels, added=[stack.configuration.needs_resolution_label]
        ).labels,
    )
    return fork.add_comment(
        branch.pull_request_number, conflict_report(branch, conflicting_paths, parent)
    )


def _restack_branch(
    entry: Mapping[str, str],
    stack: Stack,
    by_name: Mapping[str, Branch],
    pre_flight: PreFlight,
    git: GitCommandRunner,
    fork: PullRequestReader | PullRequestWriter,
) -> BranchOutcome:
    """Integrate one branch's parent and publish the result.

    :param entry: One ``restack_plan`` entry: branch, parent and strategy.
    :param stack: The derived stack.
    :param by_name: Every branch in the stack, keyed by name.
    :param pre_flight: The checks every push is put through.
    :param git: The runner to execute through.
    :param fork: The fork, read for conflict state and written to when reporting.
    :return: What became of the branch.
    """
    configuration = stack.configuration
    branch, parent = entry["branch"], entry["parent"]
    strategy = IntegrationStrategy(entry["strategy"])
    node = by_name[branch]
    branch_reference = resolve_ref(configuration, branch)
    parent_reference = resolve_ref(configuration, parent)

    if _withhold(node, stack, fork):
        return BranchOutcome(
            branch,
            parent,
            strategy,
            RestackOutcome.WITHHELD,
            explanation="still conflicted against its base since a previous pass",
        )

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
            reported_at=_report_conflict(node, parent, conflicting, stack, fork),
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


# %% promoting every approved unblocked branch

PROMOTION_HEADING = "## Promote"
"""Heading the compare-and-create link is written under, in the fork pull request's own
description - the summary that carried it is delivered once and then gone, and the
description is still there a week later."""

PROMOTION_LINK_LABEL = "cram2-link-sent"
"""Marks a branch whose link has been built, so a later pass does not rebuild it."""


@dataclass(frozen=True)
class Promotion:
    """One branch's compare-and-create link, and where it was recorded."""

    branch: str
    """The branch promoted."""

    pull_request_number: int
    """Its fork pull request."""

    url: str
    """The compare-and-create link opening the upstream pull request."""

    body_was_truncated: bool
    """Whether the prefilled description had to be shortened to fit the URL limit."""


def description_with_promotion_link(description: str, url: str) -> str:
    """Put a promotion link into a description, replacing any already there.

    :param description: The pull request's current description.
    :param url: The link to record.
    :return: The description to write back.
    """
    before, _, _ = description.partition(PROMOTION_HEADING)
    return f"{before.rstrip()}\n\n{PROMOTION_HEADING}\n\n{url}\n"


def promotion_summary(description: str) -> str:
    """Take the one paragraph of a description that prefills the upstream pull request.

    A compare URL discards an over-long prefill silently, so the whole description is
    never sent - the link back to the fork pull request carries the rest.

    :param description: The fork pull request's description.
    :return: Its first paragraph, empty if it has none.
    """
    before, _, _ = description.partition(PROMOTION_HEADING)
    paragraphs = [block.strip() for block in before.split("\n\n") if block.strip()]
    return paragraphs[0] if paragraphs else ""


def promote(
    stack: Stack, fork: PullRequestReader | PullRequestWriter
) -> list[Promotion]:
    """Build and record the upstream link for every branch ready to be promoted.

    The upstream pull request is not opened here - the app has no write access there, so
    that call fails every time. What is written is the link that opens it prefilled, into
    the fork pull request's own description, plus the label stopping a later pass
    rebuilding it. The ``in-review`` label stays the developer's to add, since the
    upstream pull request does not exist until they click Create.

    :param stack: The derived stack.
    :param fork: The fork to read descriptions from and write links back to.
    :return: One entry per branch promoted, in dependency order.
    """
    promoted: list[Promotion] = []
    for branch in promotion_order(stack):
        if PROMOTION_LINK_LABEL in branch.labels:
            continue
        pull_request = fork.pull_request(branch.pull_request_number)
        description = str(pull_request.get("body") or "")
        link = PromotionLink.build(
            stack.configuration,
            branch.name,
            str(pull_request.get("title") or branch.name),
            _prefilled_description(description, branch.pull_request_number, stack),
        )
        fork.set_description(
            branch.pull_request_number,
            description_with_promotion_link(description, link.url),
        )
        fork.replace_labels(
            branch.pull_request_number,
            LabelWrite.replacing(branch.labels, added=[PROMOTION_LINK_LABEL]).labels,
        )
        promoted.append(
            Promotion(
                branch=branch.name,
                pull_request_number=branch.pull_request_number,
                url=link.url,
                body_was_truncated=link.body_was_truncated,
            )
        )
    return promoted


def _prefilled_description(
    description: str, pull_request_number: int, stack: Stack
) -> str:
    """Build what the upstream pull request opens with.

    :param description: The fork pull request's description.
    :param pull_request_number: The fork pull request, to link back to.
    :param stack: The derived stack, naming the fork.
    :return: One paragraph plus a link back to the full detail.
    """
    summary = promotion_summary(description)
    detail = (
        f"Full detail: https://github.com/{stack.configuration.fork_repository}"
        f"/pull/{pull_request_number}"
    )
    return f"{summary}\n\n{detail}" if summary else detail


def clear_spent_promotion_labels(
    stack: Stack, fork: PullRequestWriter
) -> tuple[str, ...]:
    """Drop the link label from every branch whose link has already been acted on.

    :param stack: The derived stack.
    :param fork: The fork to write to.
    :return: The branches whose label was cleared.
    """
    spent = [
        branch
        for branch in stack.branches
        if PROMOTION_LINK_LABEL in branch.labels
        and branch.status in {BranchStatus.IN_REVIEW, BranchStatus.MERGED}
    ]
    for branch in spent:
        fork.replace_labels(
            branch.pull_request_number,
            LabelWrite.replacing(branch.labels, removed=[PROMOTION_LINK_LABEL]).labels,
        )
    return tuple(branch.name for branch in spent)


# %% the report a caller renders or emits


@dataclass(frozen=True)
class MaintenanceReport:
    """Everything one pass did, and the one thing it leaves for its caller.

    ``reparents`` is that one thing: retargeting a base is the single write GitHub
    refuses to the credential this runs on, so it is reported rather than performed.
    """

    fast_forward: FastForwardReport | None
    """What became of the fork's base branch, absent when it was not attempted."""

    restacked: tuple[BranchOutcome, ...]
    """What became of each branch in the restack plan."""

    promoted: tuple[Promotion, ...]
    """The branches whose upstream link was built and recorded this pass."""

    promotion_labels_cleared: tuple[str, ...]
    """The branches whose spent link label was removed this pass."""

    reparents: tuple[Reparent, ...]
    """The children whose base has landed, for the caller to retarget - the one step
    this cannot perform itself."""

    landed: tuple[str, ...]
    """The branches whose own commits are already in the upstream base."""

    promotable: tuple[str, ...]
    """The branches approved and unblocked, whether or not a link was built this pass."""

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
    promoted: Sequence[Promotion] = (),
    promotion_labels_cleared: Sequence[str] = (),
) -> MaintenanceReport:
    """Assemble one pass's outcomes and its leftovers into a single report.

    :param stack: The derived stack, read for what the caller still has to do.
    :param fast_forward_report: What became of the fork's base branch, if attempted.
    :param restacked: What became of each branch in the restack plan.
    :param promoted: The branches whose upstream link was built this pass.
    :param promotion_labels_cleared: The branches whose spent link label was removed.
    :return: The report.
    """
    return MaintenanceReport(
        fast_forward=fast_forward_report,
        restacked=tuple(restacked),
        promoted=tuple(promoted),
        promotion_labels_cleared=tuple(promotion_labels_cleared),
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


def print_promotions(promoted: Sequence[Promotion], cleared: Sequence[str]) -> None:
    """:param promoted: The branches whose link was built this pass.
    :param cleared: The branches whose spent link label was removed."""
    for promotion in promoted:
        print(f"{promotion.branch}\t#{promotion.pull_request_number}\t{promotion.url}")
        if promotion.body_was_truncated:
            print(
                f"{promotion.branch}: the prefilled description was shortened to fit "
                f"the URL limit",
                file=sys.stderr,
            )
    for branch in cleared:
        print(f"{branch}\tlink-label-cleared\t")


# %% entry point


class Command(StrEnum):
    """Every command this executor answers, named once so no caller spells one out."""

    BOARD = "board"
    FAST_FORWARD = "fast-forward"
    RESTACK = "restack"
    PROMOTE = "promote"
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
    """No GitHub token is set, so the fork cannot be read or written."""

    GITHUB_REQUEST_FAILED = 9
    """The API refused a call this pass depends on; its status and reason are on
    stderr."""


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
    commands.add_parser(
        Command.PROMOTE, help="record the upstream link on every promotable branch"
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


def _run_board(fork: PullRequestReader, write: bool) -> MaintenanceExitCode:
    """Fetch the fork's open pull requests and export them.

    :param fork: The fork to read.
    :param write: Whether to write ``board.json`` rather than print the export.
    :return: The process exit code.
    """
    export = BoardExport.from_api_records(fork.open_pull_requests())
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


def _run_restack(
    stack: Stack, git: GitCommandRunner, fork: GitHubRepository
) -> MaintenanceExitCode:
    """:param stack: The derived stack.
    :param git: The runner to execute through.
    :param fork: The fork to read conflict state from and report back to.
    :return: The process exit code."""
    outcomes = restack(stack, git, fork)
    print_restack(outcomes)
    if any(outcome.outcome is RestackOutcome.REFUSED for outcome in outcomes):
        return MaintenanceExitCode.PREFLIGHT_REFUSED
    return MaintenanceExitCode.SUCCESS


def _run_promote(stack: Stack, fork: GitHubRepository) -> MaintenanceExitCode:
    """:param stack: The derived stack.
    :param fork: The fork to write links and labels to.
    :return: The process exit code."""
    print_promotions(promote(stack, fork), clear_spent_promotion_labels(stack, fork))
    return MaintenanceExitCode.SUCCESS


def _run_report(
    stack: Stack, git: GitCommandRunner, fork: GitHubRepository, as_json: bool
) -> MaintenanceExitCode:
    """Perform the whole pass and report it.

    :param stack: The derived stack.
    :param git: The runner to execute through.
    :param fork: The fork to read from and write to.
    :param as_json: Whether to emit the machine-readable document.
    :return: The process exit code.
    """
    fast_forward_report = fast_forward(stack.configuration, git)
    report = build_report(
        stack,
        fast_forward_report,
        restack(stack, git, fork),
        promote(stack, fork),
        clear_spent_promotion_labels(stack, fork),
    )
    if as_json:
        print(report.as_json())
    else:
        print_fast_forward(fast_forward_report)
        print_restack(report.restacked)
        print_promotions(report.promoted, report.promotion_labels_cleared)
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
        if command is Command.FAST_FORWARD:
            return _run_fast_forward(configuration, git)
        fork = GitHubRepository.from_environment(configuration.fork_repository)
        if command is Command.BOARD:
            return _run_board(fork, arguments.write)
        stack = load_stack()
        if command is Command.RESTACK:
            return _run_restack(stack, git, fork)
        if command is Command.PROMOTE:
            return _run_promote(stack, fork)
        return _run_report(stack, git, fork, arguments.json)
    except (ForkRemoteNotFoundError, AmbiguousForkRemoteError) as error:
        print(f"{error}", file=sys.stderr)
        return MaintenanceExitCode.REMOTES_UNRESOLVED
    except BoardUnavailable as error:
        print(f"{error}", file=sys.stderr)
        return MaintenanceExitCode.BOARD_UNAVAILABLE
    except GitHubCredentialUnavailableError as error:
        print(f"{error}", file=sys.stderr)
        return MaintenanceExitCode.CREDENTIAL_UNAVAILABLE
    except (
        MissingPullRequestFieldError,
        ContradictoryLabelWriteError,
        PromotionLinkTooLongError,
    ) as error:
        print(f"{error}", file=sys.stderr)
        return MaintenanceExitCode.USAGE
    except GitCommandFailed as error:
        print(f"{error}", file=sys.stderr)
        return MaintenanceExitCode.GIT_COMMAND_FAILED
    except GitHubRequestFailed as error:
        print(f"{error}", file=sys.stderr)
        return MaintenanceExitCode.GITHUB_REQUEST_FAILED


if __name__ == "__main__":
    sys.exit(main())
