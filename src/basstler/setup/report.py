"""
Reading check-setup.sh's report.

The script's tab-separated rows are its whole interface, so they are read back into the
check each row is about and the status it reports.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import StrEnum

from basstler.exit_codes import SetupCheckExitCode

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
    The notes branch's workflow that starts the plan site's build on every push.
    """

    GIT_IDENTITY = "git_identity"
    """
    The identity commits are authored with, against the recorded one.
    """

    PACKAGE_DEPENDENCIES = "package_dependencies"
    """
    Every dependency the package declares being installed.
    """

    CLAUDE_LOCAL_MD = "claude_local_md"
    """
    ``CLAUDE.local.md`` written by the SessionStart hook.
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

    @classmethod
    def from_completed_process(
        cls, process: subprocess.CompletedProcess[str]
    ) -> SetupReport:
        """
        Parse a finished check-setup.sh run.

        :param process: The finished check-setup.sh subprocess, its output captured.
        :return: The parsed report.
        :raises ValueError: If a row names a check or a status, or the script exits
            with a status, this module does not declare, so a new one cannot go unread.
        """
        results = {}
        for line in process.stdout.splitlines():
            check, status, detail = line.split(ReportRowField.SEPARATOR)
            results[SetupCheck(check)] = CheckResult(CheckStatus(status), detail)
        return cls(SetupCheckExitCode(process.returncode), results)
