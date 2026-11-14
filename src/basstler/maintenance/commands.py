"""
The commands the executor answers, and what one run has resolved for them.

A command owns its own name, its own flags and its own work, so adding one is writing a
subclass: :meth:`MaintenanceCommand.every_command` finds it, and nothing else has to be
told it exists.
"""

from __future__ import annotations

import argparse
import json
from abc import abstractmethod
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

from basstler.class_property import classproperty
from basstler.command_line import Command
from basstler.exit_codes import StackExitCode
from basstler.git.commands import GitCommandRunner, ProposedPush
from basstler.stack.commit_move import (
    BranchAncestry,
    CommitMoveAction,
    CommitMoveChecks,
    ProposedCommitMove,
)
from basstler.github.remote_branch import GitHubRemoteBranch
from basstler.github.client import GitHubRestClient
from basstler.github.constants import MaintenanceNotice
from basstler.github.repository_access import GitHubRepository, PullRequestReader
from basstler.locations import RepositoryStateLocation
from basstler.maintenance.board import BoardExport, UpstreamPullRequests
from basstler.maintenance.check_overview import CheckOverview
from basstler.maintenance.fast_forward import fast_forward
from basstler.maintenance.finish_summary import FinishSummary
from basstler.maintenance.promotion import (
    PromotionSummaries,
    clear_spent_promotion_labels,
    promote,
)
from basstler.maintenance.promotion_context import PromotionContextReader
from basstler.maintenance.report import MaintenanceReport
from basstler.maintenance.restack_procedure import restack
from basstler.maintenance.upstream_action import (
    OpenPullRequestsAnswer,
    OpenPullRequestsRequest,
    UpstreamReadRoute,
)
from basstler.maintenance.upstream_pull_request_synchronization import (
    UpstreamPullRequestSynchronization,
)
from basstler.stack.model import Stack
from basstler.stack.settings import Configuration
from basstler.standard_streams import StandardStreamHandler
from basstler.upstream_reviews.action.branch import ActionBranch
from basstler.upstream_reviews.action.read import ActionRead

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""


@dataclass(frozen=True)
class MaintenancePass:
    """
    What one run has resolved so far, built lazily as a command asks for it.

    Every command that needs the stack derives it from a board it exports itself, so no
    command depends on a file an earlier one wrote or a later one discarded.
    """

    configuration: Configuration
    """
    The resolved configuration naming both repositories and every label.
    """

    git: GitCommandRunner
    """
    The runner every git command goes through.
    """

    board: Path
    """
    Where :class:`BoardCommand` writes the board for a person to read; no command derives
    its stack from it, and a whole pass discards it.
    """

    upstream_read: UpstreamReadRoute = UpstreamReadRoute.DIRECT
    """
    How this run reads the upstream's open pull requests.
    """

    action_timeout: float = 480
    """
    How many seconds a read through the fork's Action waits for its run.
    """

    @property
    def full_report(self) -> Path:
        """
        Where a whole pass writes everything it did, beside :attr:`board`.
        """
        return self.board.with_name(RepositoryStateLocation.MAINTENANCE_REPORT.name)

    def fork(self) -> GitHubRepository:
        """:return: The fork, as this run's credential can read and write it."""
        return GitHubRepository.from_environment(self.configuration.fork_repository)

    def upstream(self) -> PullRequestReader:
        """:return: The upstream, as this run's credential can read it."""
        return GitHubRepository.from_environment(self.configuration.upstream_repository)

    def upstream_pull_requests(self) -> UpstreamPullRequests:
        """
        :return: The upstream's open pull requests opened from the fork's branches, read
            the way :attr:`upstream_read` names; none for a project with no upstream.
        :raises ActionUnavailable: If that is the fork's Action and it cannot answer.
        """
        fork = self.configuration.fork_repository
        if not self.configuration.has_upstream:
            logger.warning(MaintenanceNotice.NO_UPSTREAM)
            return UpstreamPullRequests(fork, {})
        if self.upstream_read is UpstreamReadRoute.DIRECT:
            return UpstreamPullRequests.from_api_records(
                self.upstream().open_pull_requests(), fork
            )
        read = ActionRead(
            GitHubRemoteBranch(
                ActionBranch.NAME, self.git, self.configuration.fork_remote
            ),
            OpenPullRequestsRequest.fresh(self.configuration.upstream_repository, fork),
            GitHubRestClient(),
            answer_type=OpenPullRequestsAnswer,
        )
        return read.wait(self.action_timeout, read.send()).upstream_pull_requests

    def export_board(self) -> BoardExport:
        """:return: The fork's open pull requests, each with the upstream pull request
        reviewing it and the verdict over its head's checks."""
        fork = self.fork()
        upstream_pull_requests = self.upstream_pull_requests()
        return BoardExport.from_api_records(
            fork.open_pull_requests(), upstream_pull_requests, fork
        )

    def fresh_stack(self) -> Stack:
        """:return: The stack derived from a board exported just now, never from a file
        an earlier command left behind."""
        return Stack.from_pull_requests(list(self.export_board().pull_requests))


class PreparationKey(StrEnum):
    """
    The keys of the document :class:`PrepareCommand` prints.
    """

    REPARENTS = "reparents"
    """
    The pull requests whose base the session retargets before the pass.
    """

    TO_SUMMARIZE = "to_summarize"
    """
    The context of every branch whose upstream summary the session writes.
    """


@dataclass(frozen=True)
class MaintenanceCommand(Command):
    """
    One command this executor answers.
    """

    @abstractmethod
    def run(
        self, maintenance: MaintenancePass, arguments: argparse.Namespace
    ) -> StackExitCode:
        """
        Perform the command.

        :param maintenance: What this run has resolved.
        :param arguments: The parsed command line.
        :return: The process exit code.
        """


@dataclass(frozen=True)
class BoardCommand(MaintenanceCommand):
    """
    Fetches the fork's open pull requests and exports them as the board, each with the
    upstream pull request reviewing it and the verdict over its head's checks.
    """

    @classproperty
    def description(cls) -> str:
        """
        What it does, as ``--help`` puts it.
        """
        return (
            "export the fork's open pull requests, with their upstream review and "
            "checks"
        )

    def declare_arguments(self, parser: argparse.ArgumentParser) -> None:
        """:param parser: The subparser to declare ``--write`` on."""
        parser.add_argument(
            "--write",
            action="store_true",
            help="write board.json rather than printing the export",
        )

    def run(
        self, maintenance: MaintenancePass, arguments: argparse.Namespace
    ) -> StackExitCode:
        """:param maintenance: What this run has resolved.
        :param arguments: The parsed command line.
        :return: The process exit code."""
        export = maintenance.export_board()
        if not arguments.write:
            logger.info(export.as_json())
            return StackExitCode.SUCCESS
        written_to = export.write(maintenance.board)
        logger.info(f"{len(export.pull_requests)} open pull request(s) -> {written_to}")
        return StackExitCode.SUCCESS


class StackScopeArgument:
    """
    Declares the ``--stacked-on`` argument of a command that passes over every branch,
    or only over one branch's stack.
    """

    def declare_arguments(self, parser: argparse.ArgumentParser) -> None:
        """:param parser: The subparser to declare ``--stacked-on`` on."""
        parser.add_argument(
            "--stacked-on",
            help=(
                "pass only over this branch's stack: the branch, the branches it is "
                "stacked on and the branches stacked on it"
            ),
        )


@dataclass(frozen=True)
class PrepareCommand(StackScopeArgument, MaintenanceCommand):
    """
    Exports the board and lists everything a session does before the pass: the bases
    to retarget and the upstream summaries to write.
    """

    @classproperty
    def description(cls) -> str:
        """
        What it does, as ``--help`` puts it.
        """
        return (
            "export the board, then list the reparents to make and what each "
            "upstream summary to write is written from"
        )

    def run(
        self, maintenance: MaintenancePass, arguments: argparse.Namespace
    ) -> StackExitCode:
        """:param maintenance: What this run has resolved.
        :param arguments: The parsed command line.
        :return: The process exit code."""
        stack = maintenance.fresh_stack().scoped_to(arguments.stacked_on)
        contexts = PromotionContextReader(
            stack, maintenance.git, maintenance.fork()
        ).read()
        document = {
            PreparationKey.REPARENTS: [asdict(entry) for entry in stack.reparents()],
            PreparationKey.TO_SUMMARIZE: [asdict(context) for context in contexts],
        }
        logger.info(json.dumps(document, ensure_ascii=False))
        return StackExitCode.SUCCESS


@dataclass(frozen=True)
class FastForwardCommand(MaintenanceCommand):
    """
    Moves the fork's base branch onto the upstream, refusing to force.
    """

    @classproperty
    def description(cls) -> str:
        """
        What it does, as ``--help`` puts it.
        """
        return "move the fork's base branch onto the upstream"

    def run(
        self, maintenance: MaintenancePass, arguments: argparse.Namespace
    ) -> StackExitCode:
        """:param maintenance: What this run has resolved.
        :param arguments: The parsed command line.
        :return: The process exit code."""
        report = MaintenanceReport(
            fast_forward=fast_forward(maintenance.configuration, maintenance.git)
        )
        report.print_summary()
        return report.exit_code


@dataclass(frozen=True)
class RestackCommand(MaintenanceCommand):
    """
    Integrates every moved parent and publishes what merged cleanly.
    """

    @classproperty
    def description(cls) -> str:
        """
        What it does, as ``--help`` puts it.
        """
        return "integrate every moved parent and publish the result"

    def declare_arguments(self, parser: argparse.ArgumentParser) -> None:
        """:param parser: The subparser to declare ``--stacked-on`` on."""
        parser.add_argument(
            "--stacked-on",
            help=(
                "carry only this branch into what is stacked on it, leaving the rest "
                "of the board alone and handing any collision back rather than "
                "reporting it to the branch's owner"
            ),
        )

    def run(
        self, maintenance: MaintenancePass, arguments: argparse.Namespace
    ) -> StackExitCode:
        """:param maintenance: What this run has resolved.
        :param arguments: The parsed command line.
        :return: The process exit code."""
        stack = maintenance.fresh_stack()
        report = MaintenanceReport(
            restacked=tuple(
                restack(
                    stack, maintenance.git, maintenance.fork(), arguments.stacked_on
                )
            )
        )
        if not report.restacked:
            logger.info(RestackCommand.nothing_to_restack(arguments.stacked_on))
        report.print_summary()
        return report.exit_code

    @staticmethod
    def nothing_to_restack(stacked_on: str | None) -> str:
        """
        :param stacked_on: The branch whose stack was asked for, ``None`` for every
            branch.
        :return: The line saying the restack had no branch to carry anything into.
        """
        if stacked_on is None:
            return "no open pull request needs restacking"
        return f"no open pull request is stacked on {stacked_on}; nothing to carry"


@dataclass(frozen=True)
class PushCommand(MaintenanceCommand):
    """
    Publishes the checked-out branch to the same branch on the fork, only once the move
    checks a restack's push is put through find it clear.
    """

    @classproperty
    def description(cls) -> str:
        """
        What it does, as ``--help`` puts it.
        """
        return (
            "publish the checked-out branch to the fork, unless the move checks "
            "refuse it"
        )

    def run(
        self, maintenance: MaintenancePass, arguments: argparse.Namespace
    ) -> StackExitCode:
        """:param maintenance: What this run has resolved.
        :param arguments: The parsed command line.
        :return: The process exit code: success only when the branch was published.
        :raises GitCommandFailed: If the fork rejects the push."""
        git = maintenance.git
        stack = maintenance.fresh_stack()
        branch = git.checked_out_branch()
        fork_remote = stack.configuration.fork_remote
        checks = CommitMoveChecks(
            stack=stack,
            checked_out_branch=branch,
            is_ancestor=BranchAncestry(stack.configuration, git).is_ancestor,
        )
        verdict = checks.print_verdict(
            ProposedCommitMove(
                action=CommitMoveAction.PUSH,
                source=branch,
                destination=branch,
                destination_remote=fork_remote,
            )
        )
        if verdict is not StackExitCode.SUCCESS:
            return verdict
        git.push(
            ProposedPush(remote=fork_remote, refspec=f"{branch}:{branch}")
        ).raise_if_failed()
        logger.info(f"pushed {branch} to {fork_remote}/{branch}")
        return StackExitCode.SUCCESS


@dataclass(frozen=True)
class PromoteCommand(MaintenanceCommand):
    """
    Records the upstream link on every branch ready to be promoted, and keeps every
    in-review label in step with the upstream.
    """

    @classproperty
    def description(cls) -> str:
        """
        What it does, as ``--help`` puts it.
        """
        return "record the upstream link on every promotable branch"

    def declare_arguments(self, parser: argparse.ArgumentParser) -> None:
        """:param parser: The subparser to declare ``--summaries`` on."""
        parser.add_argument(
            "--summaries",
            type=Path,
            help=(
                "a JSON document keyed by fork pull request number, each entry giving "
                "the 'points' and optionally the 'title' its upstream pull request "
                "opens with"
            ),
        )

    def run(
        self, maintenance: MaintenancePass, arguments: argparse.Namespace
    ) -> StackExitCode:
        """:param maintenance: What this run has resolved.
        :param arguments: The parsed command line.
        :return: The process exit code."""
        stack = maintenance.fresh_stack()
        fork = maintenance.fork()
        report = MaintenanceReport(
            promoted=tuple(
                promote(stack, fork, PromotionSummaries.read_from(arguments.summaries))
            ),
            promotion_labels_cleared=tuple(clear_spent_promotion_labels(stack, fork)),
            upstream_pull_request_synchronization_changes=tuple(
                UpstreamPullRequestSynchronization(stack, fork).synchronize()
            ),
        )
        report.print_summary()
        return report.exit_code


@dataclass(frozen=True)
class ChecksCommand(MaintenanceCommand):
    """
    Exports the board and reports the verdict over every open branch's checks.
    """

    @classproperty
    def description(cls) -> str:
        """
        What it does, as ``--help`` puts it.
        """
        return (
            "report how many open branches' checks pass, run or fail, naming the rest"
        )

    def run(
        self, maintenance: MaintenancePass, arguments: argparse.Namespace
    ) -> StackExitCode:
        """:param maintenance: What this run has resolved.
        :param arguments: The parsed command line.
        :return: The process exit code."""
        logger.info("\n".join(CheckOverview(maintenance.fresh_stack()).as_lines()))
        maintenance.board.unlink(missing_ok=True)
        return StackExitCode.SUCCESS


@dataclass(frozen=True)
class RunReportCommand(StackScopeArgument, MaintenanceCommand):
    """
    Performs the whole pass and reports it as one document.
    """

    @classproperty
    def description(cls) -> str:
        """
        What it does, as ``--help`` puts it.
        """
        return "perform the whole pass and report it"

    def declare_arguments(self, parser: argparse.ArgumentParser) -> None:
        """:param parser: The subparser to declare ``--json``, ``--stacked-on`` and the
        promotion's own arguments on."""
        super().declare_arguments(parser)
        PromoteCommand().declare_arguments(parser)
        parser.add_argument(
            "--json",
            action="store_true",
            help="emit the machine-readable document rather than the finish summary",
        )

    def run(
        self, maintenance: MaintenancePass, arguments: argparse.Namespace
    ) -> StackExitCode:
        """
        :param maintenance: What this run has resolved.
        :param arguments: The parsed command line.
        :return: The process exit code.
        """
        return self.perform(
            maintenance,
            as_json=arguments.json,
            summaries=PromotionSummaries.read_from(arguments.summaries),
            stacked_on=arguments.stacked_on,
        ).exit_code

    def perform(
        self,
        maintenance: MaintenancePass,
        as_json: bool,
        summaries: PromotionSummaries,
        stacked_on: str | None = None,
    ) -> MaintenanceReport:
        """
        Export the board, perform every step of the pass, write the whole report and
        print its summary, then discard the board.

        The board is a snapshot of one moment's open pull requests, and a stale one read
        by a later run is worse than none at all - so a whole pass begins by exporting
        one and ends without it.

        The checks on the board are those on each branch's tip as the pass found it, so
        what an earlier pass pushed has finished being checked by now; what this pass
        pushes is read by the next.

        :param maintenance: What this run has resolved.
        :param as_json: Whether to print the machine-readable document rather than the
            finish summary.
        :param summaries: What each upstream pull request opens with, where anybody wrote
            it.
        :param stacked_on: The branch whose stack to pass over, or ``None`` for every
            branch.
        :return: What the pass did.
        """
        stack = maintenance.fresh_stack().scoped_to(stacked_on)
        fork = maintenance.fork()
        fast_forward_report = fast_forward(stack.configuration, maintenance.git)
        report = MaintenanceReport.of_pass(
            stack,
            fast_forward_report,
            restack(stack, maintenance.git, fork),
            promote(stack, fork, summaries),
            clear_spent_promotion_labels(stack, fork),
            UpstreamPullRequestSynchronization(stack, fork).synchronize(),
        )
        maintenance.board.unlink(missing_ok=True)
        maintenance.full_report.write_text(report.as_json() + "\n")
        if as_json:
            logger.info(report.as_json())
            return report
        logger.info(FinishSummary(report, stack, maintenance.full_report).as_markdown())
        return report


# Built now rather than on first use, so a command that cannot say what it is called is
# refused as this module is imported.
MaintenanceCommand.every_command()
