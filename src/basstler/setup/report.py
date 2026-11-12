"""
Reading check-setup.sh's report.

The script's tab-separated rows are its whole interface, so they are read back into the
check each row is about and the status it reports.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import IntEnum, StrEnum

from basstler.exit_codes import SetupCheckExitCode
from basstler.setup.exceptions import CheckSetupFailedError

# %% what a report is made of


class SetupCheck(StrEnum):
    """
    The checks check-setup.sh reports on, in the order it prints them.
    """

    TOOLING_FILES = "tooling_files"
    """
    The plugin's own files a set up clone runs.
    """

    SESSION_START_HOOK = "session_start_hook"
    """
    The SessionStart hook registered in the plugin.
    """

    CLAUDE_LOCAL_MD_IGNORED = "claude_local_md_ignored"
    """
    ``CLAUDE.local.md`` excluded from commits.
    """

    NOTES_REMOTE = "notes_remote"
    """
    The remote the notes branch resolves to, and where that came from.
    """

    NOTES_REMOTE_URL = "notes_remote_url"
    """
    That remote's URL.
    """

    NOTES_BRANCH_NAME = "notes_branch_name"
    """
    The notes branch's name, and where that came from.
    """

    NOTES_PATH = "notes_path"
    """
    The notes file's path on that branch, and where that came from.
    """

    NOTES_REPOSITORY_ACCESS = "notes_repository_access"
    """
    A cloud session reaching the repository the notes are kept in.
    """

    NOTES_BRANCH = "notes_branch"
    """
    The notes branch existing on its remote.
    """

    NOTES_FILE = "notes_file"
    """
    The notes file existing on that branch.
    """

    STACK_UPSTREAM = "stack_upstream"
    """
    The project's upstream named for the stacked-pull-request workflow.
    """

    UPSTREAM_REVIEWS_ACTION = "upstream_reviews_action"
    """
    The fork's own upstream-reviews Action, installed at the session's basstler.
    """

    PLAN_SITE = "plan_site"
    """
    Every repository on the plan site storing its token and starting the site's build.
    """

    PLAN_SITE_ACCESS = "plan_site_access"
    """
    A cloud session reaching the plan site's repository, so a plan save can start the
    build.
    """

    GIT_IDENTITY = "git_identity"
    """
    The identity commits are authored with, against the recorded one.
    """

    PACKAGE_DEPENDENCIES = "package_dependencies"
    """
    Every dependency the package declares being installed.
    """

    BASSTLER_VERSION = "basstler_version"
    """
    The installed package's version, against the plugin's own release.
    """

    CLAUDE_LOCAL_MD = "claude_local_md"
    """
    ``CLAUDE.local.md`` written by the SessionStart hook.
    """


class RepositoryCheck(StrEnum):
    """
    The checks check-setup.sh reports once for each repository, after the fixed ones.
    """

    PLAN_SITE_REPOSITORY = "plan_site_repository"
    """
    One repository on the plan site other than the clone's own, informational only.
    """


class CheckStatus(StrEnum):
    """
    The status check-setup.sh reports for a single check.
    """

    OK = "ok"
    """
    Nothing to do.
    """

    NEEDS_SETUP = "needs-setup"
    """
    Something still has to be set up.
    """

    IN_PROGRESS = "in-progress"
    """
    Another process is setting it up right now, so it is waited for rather than set up
    again.
    """

    UNVERIFIED = "unverified"
    """
    Nothing the check could read decides it yet, so it is neither passed nor failed.
    """

    MISMATCHED = "mismatched"
    """
    The plugin's hooks and the package they call are not one release.
    """

    INFORMATIONAL = "info"
    """
    Context rather than a verdict.
    """


class ReportRowField(StrEnum):
    """
    How one report row is laid out.
    """

    SEPARATOR = "\t"
    """
    What separates a row's check, status and detail.
    """


class ReportRowPosition(IntEnum):
    """
    Where each field sits in one report row.
    """

    CHECK = 0
    """
    The check the row reports on.
    """

    STATUS = 1
    """
    The status it reports.
    """

    DETAIL = 2
    """
    The human-readable explanation.
    """


REPORTING_EXIT_CODES = frozenset(
    {SetupCheckExitCode.SUCCESS, SetupCheckExitCode.SETUP_INCOMPLETE}
)
"""
The statuses check-setup.sh exits with after printing its whole report.
"""


@dataclass(frozen=True)
class CheckResult:
    """
    What check-setup.sh reported for one check.
    """

    status: CheckStatus
    """
    Whether the check passed, needs setup, or is context rather than a verdict.
    """

    detail: str
    """
    The human-readable explanation printed alongside the status.
    """

    @property
    def fields(self) -> str:
        """
        :return: The status and the detail as a report row prints them after its
            check.
        """
        return f"{self.status}{ReportRowField.SEPARATOR}{self.detail}"


@dataclass(frozen=True)
class SetupReport:
    """
    One parsed run of check-setup.sh: what it reported, and how it exited.
    """

    exit_code: SetupCheckExitCode
    """
    The status the script exited with.
    """

    results: dict[SetupCheck, CheckResult]
    """
    Every reported check, keyed by the check it reports on.
    """

    repository_results: list[CheckResult]
    """
    What each :class:`RepositoryCheck` row reported, in the order printed.
    """

    @classmethod
    def from_completed_process(
        cls,
        process: subprocess.CompletedProcess[str],
        requested_checks: frozenset[SetupCheck] = frozenset(SetupCheck),
    ) -> SetupReport:
        """
        Parse a finished check-setup.sh run.

        :param process: The finished check-setup.sh subprocess, its output captured.
        :param requested_checks: The checks the run was asked to report on.
        :return: The parsed report.
        :raises CheckSetupFailedError: If the script exits with a status that carries no
            report, a requested check has no row, or a row cannot be read.
        """
        results = {}
        repository_results = []
        unreadable_rows = []
        for line in process.stdout.splitlines():
            fields = line.split(ReportRowField.SEPARATOR)
            if not cls.is_readable(fields):
                unreadable_rows.append(line)
                continue
            check, status, detail = fields
            result = CheckResult(CheckStatus(status), detail)
            if check in RepositoryCheck:
                repository_results.append(result)
            else:
                results[SetupCheck(check)] = result
        missing_checks = [
            check
            for check in SetupCheck
            if check in requested_checks and check not in results
        ]
        if (
            process.returncode not in REPORTING_EXIT_CODES
            or missing_checks
            or unreadable_rows
        ):
            raise CheckSetupFailedError(
                process.returncode, process.stderr, missing_checks, unreadable_rows
            )
        return cls(SetupCheckExitCode(process.returncode), results, repository_results)

    @staticmethod
    def is_readable(fields: list[str]) -> bool:
        """
        :param fields: One printed row, split at its separators.
        :return: Whether the row holds a declared check, a declared status and a detail.
        """
        return (
            len(fields) == len(ReportRowPosition)
            and (
                fields[ReportRowPosition.CHECK] in SetupCheck
                or fields[ReportRowPosition.CHECK] in RepositoryCheck
            )
            and fields[ReportRowPosition.STATUS] in CheckStatus
        )
