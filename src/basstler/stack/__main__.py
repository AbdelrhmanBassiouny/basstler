#!/usr/bin/env python3
"""Stacked pull request helper for the fork-staging / upstream-review workflow.

GitHub is the single source of truth. The stack is **not** declared in a ledger: it is read from a
``board.json`` export of the fork's pull requests, combined with plain ``git``:

  * dependency tree = each fork pull request's **base branch** (base = parent);
  * ``draft`` <-> ``ready`` = the fork pull request's draft flag;
  * ``in-review`` = an upstream pull request opened from the branch is open, recorded on the board by the export;
  * ``merged`` = the branch is an ancestor of ``<upstream_remote>/<upstream_base>``.

``stack.toml`` carries the shipped defaults (label names, the base branch); the project's committed
``.claude/basstler/stack.toml`` names its upstream, and a ``.claude/personal/stack.toml`` on the
personal-notes branch, if present, layers per-user overrides on top of both (see
:meth:`basstler.stack.settings.Configuration.load`).

Commands (run from the repo root; ``--help`` on any of them for its flags)::

    python -m basstler.stack status         # the whole stack: parent, state, drift
    python -m basstler.stack check          # would each branch merge cleanly onto its parent now?
    python -m basstler.stack merge-probe    # does one branch merge into another, and where not?
    python -m basstler.stack next           # which branches to submit upstream next
    python -m basstler.stack next --porcelain    # machine-readable: one 'name<TAB>pull request' line per branch
    python -m basstler.stack restack-plan   # bottom-up restack plan as JSON
    python -m basstler.stack configuration  # every resolved setting, including the remotes
    python -m basstler.stack labels         # the complete label set a write must send
    python -m basstler.stack check-move      # may these commits move onto that branch?
    python -m basstler.stack promotion-link # the upstream compare-and-create URL for a branch
    python -m basstler.stack reparents      # children whose base has landed, and the base they need
    python -m basstler.stack landed         # open fork pull requests whose branch has landed

The last five exist so the steps most easily got wrong by hand are computed rather than recalled: a
label write replaces the whole set, a push whose two sides name different branches moves the wrong
commits, an unencoded compare URL loses its prefill, and a landed parent is decided by git ancestry
rather than by pull-request state. ``landed`` reports only - GitHub closes a pull request as merged
by itself once its head is contained in its base, so nothing here has to close one.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter, Token

from basstler.exit_codes import CommandFailure, ExitCode, StackExitCode
from basstler.git.commands import GitCommandRunner
from basstler.git.commit_move import (
    CommitMoveAction,
    CommitMoveChecks,
    ProposedCommitMove,
)
from basstler.github.repository import Repository
from basstler.locations import RepositoryStateLocation
from basstler.stack.label_write import LabelWrite
from basstler.stack.merge_probe import MergeProbe
from basstler.stack.model import Stack
from basstler.stack.promotion_link import PromotionLink
from basstler.stack.report import StackReport
from basstler.stack.settings import Configuration
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% commands


class Command(StrEnum):
    """Every command this tool answers, named once so no caller spells one out."""

    STATUS = "status"
    """Render the derived stack, one line per branch."""

    CHECK = "check"
    """Report every structural problem the derived stack has."""

    NEXT = "next"
    """Name the branches ready to be promoted upstream."""

    RESTACK_PLAN = "restack-plan"
    """Emit the bottom-up plan of which branch integrates which parent, and how."""

    REPARENTS = "reparents"
    """Name the children whose base has landed and must be retargeted."""

    LANDED = "landed"
    """Name the branches whose own commits are already in the upstream base."""

    CHECK_MOVE = "check-move"
    """Answer whether a proposed commit move may be made, and refuse it if not."""

    CONFIGURATION = "configuration"
    """Print the resolved configuration, one ``field<TAB>value`` line per setting."""

    LABELS = "labels"
    """Compute the complete label set a write must send, from the labels carried now."""

    PROMOTION_LINK = "promotion-link"
    """Build the upstream compare-and-create link for one branch."""

    MERGE_PROBE = "merge-probe"
    """Answer whether one branch merges into another, naming every conflicting path."""


class CommandOption(StrEnum):
    """Every option a command takes, named once so no caller spells one out."""

    PORCELAIN = "--porcelain"
    """Print only what a script reads, for :attr:`Command.NEXT`."""

    FORK = "--fork"
    """The fork, as ``owner/name``, when the caller already knows it."""

    UPSTREAM = "--upstream"
    """The upstream, as ``owner/name``, when the caller already knows it."""

    CURRENT = "--current"
    """A label the pull request carries now, repeated per label."""

    ADD = "--add"
    """A label to end up with."""

    REMOVE = "--remove"
    """A label to end up without."""

    BRANCH = "--branch"
    """The fork branch to build a promotion link for."""

    TITLE = "--title"
    """The title to prefill."""

    BODY = "--body"
    """The description to prefill."""

    ACTION = "--action"
    """What a commit move would do."""

    SOURCE = "--source"
    """The branch whose commits move."""

    DESTINATION = "--destination"
    """The branch they would land on."""

    DESTINATION_REMOTE = "--destination-remote"
    """The remote holding the destination."""

    REMOTE = "--remote"
    """The remote name or URL the probed branches are fetched from."""

    BASE = "--base"
    """The branch merged into."""

    HEAD = "--head"
    """The branch merged."""


# %% reading the inputs


def derived_stack() -> Stack:
    """
    :return: The stack derived from this checkout's ``board.json``.
    :raises CommandFailure: If the board is missing or unreadable.
    """
    return Stack.load(
        GitCommandRunner(Path.cwd()).repository_state_path(
            RepositoryStateLocation.BOARD
        )
    )


def parse_repository(_: type, tokens: tuple[Token, ...]) -> Repository:
    """
    Convert a command-line ``owner/name`` value.

    :param tokens: The one token given for the option.
    :return: The repository it names.
    :raises MalformedRepositoryError: If the value is not ``owner/name``.
    """
    return Repository.parse(tokens[0].value)


RepositoryOption = Annotated[
    Repository | None,
    Parameter(converter=parse_repository, n_tokens=1, accepts_keys=False),
]
"""
An optional ``owner/name`` repository given on the command line.
"""

# %% commands

stack_app = App(
    name="basstler.stack",
    help="Stacked pull request helper: read state, compute the writes.",
)
"""
This module's command line: one command per :class:`Command`.
"""


@stack_app.command(name=Command.STATUS)
def status() -> StackExitCode:
    """
    Print the whole stack: parent, state, drift.
    """
    StackReport(derived_stack()).print_status()
    return StackExitCode.SUCCESS


@stack_app.command(name=Command.CHECK)
def check() -> StackExitCode:
    """
    Print whether each branch would merge cleanly onto its parent.
    """
    StackReport(derived_stack()).print_check()
    return StackExitCode.SUCCESS


@stack_app.command(name=Command.NEXT)
def promotable(
    *, porcelain: Annotated[bool, Parameter(name=CommandOption.PORCELAIN)] = False
) -> StackExitCode:
    """
    Print which branches to submit upstream next.

    :param porcelain: Print only a ``name<TAB>pull request`` line per branch.
    """
    report = StackReport(derived_stack())
    if porcelain:
        report.print_next_porcelain()
    else:
        report.print_next()
    return StackExitCode.SUCCESS


@stack_app.command(name=Command.RESTACK_PLAN)
def restack_plan() -> StackExitCode:
    """
    Print the bottom-up restack plan as JSON.
    """
    StackReport(derived_stack()).print_restack_plan()
    return StackExitCode.SUCCESS


@stack_app.command(name=Command.REPARENTS)
def reparents() -> StackExitCode:
    """
    Print the children whose base has landed, and the base they need.
    """
    StackReport(derived_stack()).print_reparents()
    return StackExitCode.SUCCESS


@stack_app.command(name=Command.LANDED)
def landed() -> StackExitCode:
    """
    Print the open pull requests whose branch has landed.
    """
    StackReport(derived_stack()).print_landed()
    return StackExitCode.SUCCESS


@stack_app.command(name=Command.CONFIGURATION)
def configuration(
    *,
    fork: Annotated[RepositoryOption, Parameter(name=CommandOption.FORK)] = None,
    upstream: Annotated[
        RepositoryOption, Parameter(name=CommandOption.UPSTREAM)
    ] = None,
) -> StackExitCode:
    """
    Print every resolved setting, including the remotes.

    :param fork: The fork as ``owner/name``, when you already know it.
    :param upstream: The upstream as ``owner/name``, when you already know it.
    """
    Configuration.load(
        fork_repository=fork, upstream_repository=upstream
    ).print_settings()
    return StackExitCode.SUCCESS


@stack_app.command(name=Command.LABELS)
def labels(
    *,
    current: Annotated[tuple[str, ...], Parameter(name=CommandOption.CURRENT)] = (),
    add: Annotated[tuple[str, ...], Parameter(name=CommandOption.ADD)] = (),
    remove: Annotated[tuple[str, ...], Parameter(name=CommandOption.REMOVE)] = (),
) -> StackExitCode:
    """
    Print the complete label set a label write must send.

    :param current: A label the pull request carries now; repeat per label.
    :param add: A label to end up with.
    :param remove: A label to end up without.
    """
    LabelWrite.replacing(current, add, remove).print_labels()
    return StackExitCode.SUCCESS


@stack_app.command(name=Command.PROMOTION_LINK)
def promotion_link(
    *,
    branch: Annotated[str, Parameter(name=CommandOption.BRANCH)],
    title: Annotated[str, Parameter(name=CommandOption.TITLE)],
    body: Annotated[str, Parameter(name=CommandOption.BODY)] = "",
) -> StackExitCode:
    """
    Print the upstream compare-and-create URL for a branch.

    :param branch: The fork branch to promote.
    :param title: The title to prefill.
    :param body: The description to prefill.
    """
    PromotionLink.build(Configuration.load(), branch, title, body).print_url()
    return StackExitCode.SUCCESS


@stack_app.command(name=Command.MERGE_PROBE)
def merge_probe(
    *,
    remote: Annotated[str, Parameter(name=CommandOption.REMOTE)],
    base: Annotated[str, Parameter(name=CommandOption.BASE)],
    head: Annotated[str, Parameter(name=CommandOption.HEAD)],
) -> StackExitCode:
    """
    Report whether one branch merges into another, and where it conflicts.

    :param remote: The remote name or URL, except that the upstream base of a project
        naming an upstream is read from the upstream.
    :param base: The branch merged into.
    :param head: The branch merged.
    """
    result = MergeProbe(
        head_location=remote,
        base_location=Configuration.location_of(base, remote),
        base=base,
        head=head,
    ).run(Path.cwd())
    result.print_report()
    return result.exit_code


@stack_app.command(name=Command.CHECK_MOVE)
def check_move(
    *,
    action: Annotated[CommitMoveAction, Parameter(name=CommandOption.ACTION)],
    source: Annotated[str, Parameter(name=CommandOption.SOURCE)],
    destination: Annotated[str, Parameter(name=CommandOption.DESTINATION)],
    destination_remote: Annotated[
        str, Parameter(name=CommandOption.DESTINATION_REMOTE)
    ],
) -> StackExitCode:
    """
    Report whether these commits may move onto that branch.

    :param action: What the move would do.
    :param source: The branch whose commits move.
    :param destination: The branch they would land on.
    :param destination_remote: The remote holding the destination.
    """
    return CommitMoveChecks.of_checkout(derived_stack()).print_verdict(
        ProposedCommitMove(
            action=action,
            source=source,
            destination=destination,
            destination_remote=destination_remote,
        ),
    )


# %% entry point


def main() -> ExitCode:
    """
    Run the invoked command, ending with the status a refusal carries.

    :return: The process exit code.
    """
    try:
        return stack_app(result_action="return_value")
    except CommandFailure as error:
        logger.error(f"{error}")
        return error.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
