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

from basstler.exit_codes import StackExitCode
from basstler.class_property import classproperty
from basstler.command_line import Command
from basstler.locations import PackageLocation
from basstler.maintenance.board import BoardExport
from basstler.maintenance.fast_forward import fast_forward
from basstler.maintenance.finish_summary import FinishSummary
from basstler.maintenance.git_commands import GitCommandRunner
from basstler.maintenance.github import GitHubRepository
from basstler.maintenance.promotion import (
    PromotionSummaries,
    clear_spent_promotion_labels,
    promote,
)
from basstler.maintenance.promotion_context import PromotionContextReader
from basstler.maintenance.pushed_branch_checks import PushedBranchChecks
from basstler.maintenance.report import MaintenanceReport
from basstler.maintenance.restack_procedure import restack
from basstler.maintenance.restack_steps import RestackOutcome
from basstler.stack.model import BranchStatus, Stack
from basstler.stack.settings import Configuration
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""


@dataclass(frozen=True)
class MaintenancePass:
    """
    What one run has resolved so far, built lazily as a command asks for it.

    The board is derived before the credential is resolved, so a caller missing both is
    sent after the board - the thing the previous command produces - rather than after a
    token that would not help them yet.
    """

    configuration: Configuration
    """
    The resolved configuration naming both repositories and every label.
    """

    git: GitCommandRunner
    """
    The runner every git command goes through.
    """

    board: Path = PackageLocation.BOARD.value
    """
    The exported board this run writes, derives its stack from and discards at its end.
    """

    full_report: Path = PackageLocation.MAINTENANCE_REPORT.value
    """
    Where a whole pass writes everything it did.
    """

    def fork(self) -> GitHubRepository:
        """:return: The fork, as this run's credential can read and write it."""
        return GitHubRepository.from_environment(self.configuration.fork_repository)

    def stack(self) -> Stack:
        """:return: The derived stack, read from the exported board."""
        return Stack.load(self.board)

    def export_board(self) -> BoardExport:
        """:return: The fork's open pull requests, now also written as the board."""
        export = BoardExport.from_api_records(self.fork().open_pull_requests())
        export.write(self.board)
        return export

    def fresh_stack(self) -> Stack:
        """:return: The stack derived from a board exported just now."""
        self.export_board()
        return self.stack()


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
    Fetches the fork's open pull requests and exports them as the board.
    """

    @classproperty
    def invoked_as(cls) -> str:
        """
        The name it is invoked by on the command line.
        """
        return "board"

    @classproperty
    def description(cls) -> str:
        """
        What it does, as ``--help`` puts it.
        """
        return "export the fork's open pull requests"

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
        export = BoardExport.from_api_records(maintenance.fork().open_pull_requests())
        if not arguments.write:
            logger.info(export.as_json())
            return StackExitCode.SUCCESS
        written_to = export.write(maintenance.board)
        logger.info(f"{len(export.pull_requests)} open pull request(s) -> {written_to}")
        return StackExitCode.SUCCESS


@dataclass(frozen=True)
class PrepareCommand(MaintenanceCommand):
    """
    Exports the board and lists everything a session does before the pass: the bases
    to retarget and the upstream summaries to write.
    """

    @classproperty
    def invoked_as(cls) -> str:
        """
        The name it is invoked by on the command line.
        """
        return "prepare"

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
        stack = maintenance.fresh_stack()
        contexts = PromotionContextReader(
            stack, maintenance.git, maintenance.fork()
        ).read()
        document = {
            PreparationKey.REPARENTS: [asdict(entry) for entry in stack.reparents()],
            PreparationKey.TO_SUMMARIZE: [asdict(context) for context in contexts],
        }
        logger.info(json.dumps(document, indent=1, ensure_ascii=False))
        return StackExitCode.SUCCESS


@dataclass(frozen=True)
class FastForwardCommand(MaintenanceCommand):
    """
    Moves the fork's base branch onto the upstream, refusing to force.
    """

    @classproperty
    def invoked_as(cls) -> str:
        """
        The name it is invoked by on the command line.
        """
        return "fast-forward"

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
    def invoked_as(cls) -> str:
        """
        The name it is invoked by on the command line.
        """
        return "restack"

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
        stack = maintenance.stack()
        report = MaintenanceReport(
            restacked=tuple(
                restack(
                    stack, maintenance.git, maintenance.fork(), arguments.stacked_on
                )
            )
        )
        report.print_summary()
        return report.exit_code


@dataclass(frozen=True)
class PromoteCommand(MaintenanceCommand):
    """
    Records the upstream link on every branch ready to be promoted.
    """

    @classproperty
    def invoked_as(cls) -> str:
        """
        The name it is invoked by on the command line.
        """
        return "promote"

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
        stack = maintenance.stack()
        fork = maintenance.fork()
        report = MaintenanceReport(
            promoted=tuple(
                promote(stack, fork, PromotionSummaries.read_from(arguments.summaries))
            ),
            promotion_labels_cleared=tuple(clear_spent_promotion_labels(stack, fork)),
        )
        report.print_summary()
        return report.exit_code


@dataclass(frozen=True)
class ChecksCommand(MaintenanceCommand):
    """
    Reads the checks on every branch whose tip a pass pushed.
    """

    @classproperty
    def invoked_as(cls) -> str:
        """
        The name it is invoked by on the command line.
        """
        return "checks"

    @classproperty
    def description(cls) -> str:
        """
        What it does, as ``--help`` puts it.
        """
        return "report the checks on every branch whose tip a pass pushed"

    def run(
        self, maintenance: MaintenancePass, arguments: argparse.Namespace
    ) -> StackExitCode:
        """:param maintenance: What this run has resolved.
        :param arguments: The parsed command line.
        :return: The process exit code."""
        stack = maintenance.stack()
        report = MaintenanceReport(
            checks=tuple(
                PushedBranchChecks(stack, maintenance.git, maintenance.fork()).read(
                    branch
                    for branch in stack.maintained_branches()
                    if branch.status is not BranchStatus.MERGED
                )
            )
        )
        report.print_summary()
        return report.exit_code


@dataclass(frozen=True)
class RunReportCommand(MaintenanceCommand):
    """
    Performs the whole pass and reports it as one document.
    """

    @classproperty
    def invoked_as(cls) -> str:
        """
        The name it is invoked by on the command line.
        """
        return "run-report"

    @classproperty
    def description(cls) -> str:
        """
        What it does, as ``--help`` puts it.
        """
        return "perform the whole pass and report it"

    def declare_arguments(self, parser: argparse.ArgumentParser) -> None:
        """:param parser: The subparser to declare ``--json`` and the promotion's own
        arguments on."""
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
        ).exit_code

    def perform(
        self,
        maintenance: MaintenancePass,
        as_json: bool,
        summaries: PromotionSummaries,
    ) -> MaintenanceReport:
        """
        Export the board, perform every step of the pass, write the whole report and
        print its summary, then discard the board.

        The board is a snapshot of one moment's open pull requests, and a stale one read
        by a later run is worse than none at all - so a whole pass begins by exporting
        one and ends without it.

        The checks read are those on the branches the restack left where an earlier pass
        put them; what this pass pushed is still being checked, and is read by the next.

        :param maintenance: What this run has resolved.
        :param as_json: Whether to print the machine-readable document rather than the
            finish summary.
        :param summaries: What each upstream pull request opens with, where anybody wrote
            it.
        :return: What the pass did.
        """
        stack = maintenance.fresh_stack()
        fork = maintenance.fork()
        fast_forward_report = fast_forward(stack.configuration, maintenance.git)
        restacked = restack(stack, maintenance.git, fork)
        left_in_place = {
            outcome.branch
            for outcome in restacked
            if outcome.outcome is RestackOutcome.UP_TO_DATE
        }
        pushed_branch_checks = PushedBranchChecks(stack, maintenance.git, fork)
        checks = pushed_branch_checks.report_failures(
            pushed_branch_checks.read(
                branch
                for branch in stack.maintained_branches()
                if branch.name in left_in_place
            )
        )
        report = MaintenanceReport.of_pass(
            stack,
            fast_forward_report,
            restacked,
            promote(stack, fork, summaries),
            clear_spent_promotion_labels(stack, fork),
            checks,
        )
        maintenance.board.unlink(missing_ok=True)
        maintenance.full_report.write_text(report.as_json() + "\n")
        if as_json:
            logger.info(report.as_json())
            return report
        logger.info(
            FinishSummary(report, stack, maintenance.full_report).as_markdown()
        )
        return report


# Built now rather than on first use, so a command that cannot say what it is called is
# refused as this module is imported.
MaintenanceCommand.every_command()
