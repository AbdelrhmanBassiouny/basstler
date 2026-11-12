"""
Tests for :mod:`basstler.setup.report`: reading check-setup.sh's rows back, and refusing
a report that is incomplete or comes from a failed run.
"""

from __future__ import annotations

import subprocess

import pytest

from basstler.exit_codes import SetupCheckExitCode
from basstler.setup.exceptions import CheckSetupFailedError
from basstler.setup.report import (
    CheckResult,
    CheckStatus,
    RepositoryCheck,
    ReportRowField,
    SetupCheck,
    SetupReport,
)

from ..constants.environment import ShellExitStatus

STANDARD_ERROR = "check-setup.sh: line 1: a-missing-command: command not found\n"
"""
What a failed check-setup.sh run printed to its standard error.
"""

# %% rows that repeat


def row(check: str, result: CheckResult) -> str:
    """
    :param check: The check the row reports on.
    :param result: What it reports.
    :return: The row as check-setup.sh prints it.
    """
    return f"{check}{ReportRowField.SEPARATOR}{result.fields}"


def every_check_reported(*left_out: SetupCheck) -> list[str]:
    """
    :param left_out: The checks to print no row for.
    :return: One passing row for every other check, in the order they are declared.
    """
    return [
        row(check, CheckResult(CheckStatus.OK, f"{check} is set up"))
        for check in SetupCheck
        if check not in left_out
    ]


def finished(
    *rows: str,
    exit_code: int = SetupCheckExitCode.SUCCESS,
    standard_error: str = "",
) -> subprocess.CompletedProcess[str]:
    """
    :param rows: The rows the run printed, in order.
    :param exit_code: The status it exited with.
    :param standard_error: What it printed to its standard error.
    :return: A finished check-setup.sh run.
    """
    return subprocess.CompletedProcess(
        [], exit_code, "".join(f"{line}\n" for line in rows), standard_error
    )


# %% reading the rows


def test_every_repository_row_is_read_in_the_order_printed():
    first = CheckResult(CheckStatus.INFORMATIONAL, "a-first repository")
    second = CheckResult(CheckStatus.INFORMATIONAL, "a-second repository")

    report = SetupReport.from_completed_process(
        finished(
            row(SetupCheck.PLAN_SITE, CheckResult(CheckStatus.OK, "the own one")),
            row(RepositoryCheck.PLAN_SITE_REPOSITORY, first),
            row(RepositoryCheck.PLAN_SITE_REPOSITORY, second),
        ),
        requested_checks=frozenset({SetupCheck.PLAN_SITE}),
    )

    assert report.repository_results == [first, second]


def test_a_repository_row_is_not_a_fixed_check():
    plan_site = CheckResult(CheckStatus.OK, "the own repository")

    report = SetupReport.from_completed_process(
        finished(
            row(SetupCheck.PLAN_SITE, plan_site),
            row(
                RepositoryCheck.PLAN_SITE_REPOSITORY,
                CheckResult(CheckStatus.INFORMATIONAL, "another repository"),
            ),
        ),
        requested_checks=frozenset({SetupCheck.PLAN_SITE}),
    )

    assert report.results == {SetupCheck.PLAN_SITE: plan_site}


def test_a_report_of_every_check_is_read_whole():
    report = SetupReport.from_completed_process(finished(*every_check_reported()))

    assert set(report.results) == set(SetupCheck)


def test_only_the_requested_checks_need_a_row():
    notes_branch = CheckResult(CheckStatus.NEEDS_SETUP, "no notes branch")

    report = SetupReport.from_completed_process(
        finished(row(SetupCheck.NOTES_BRANCH, notes_branch)),
        requested_checks=frozenset({SetupCheck.NOTES_BRANCH}),
    )

    assert report.results == {SetupCheck.NOTES_BRANCH: notes_branch}


# %% refusing a failed or incomplete report


@pytest.mark.parametrize(
    "exit_code",
    [
        SetupCheckExitCode.USAGE,
        SetupCheckExitCode.NOT_IN_REPOSITORY,
        ShellExitStatus.COMMAND_NOT_FOUND,
    ],
    ids=["usage", "not in a repository", "command not found"],
)
def test_a_run_exiting_with_no_report_status_is_refused_with_its_error(
    exit_code: int,
):
    with pytest.raises(CheckSetupFailedError) as refusal:
        SetupReport.from_completed_process(
            finished(
                *every_check_reported(),
                exit_code=exit_code,
                standard_error=STANDARD_ERROR,
            )
        )

    assert refusal.value.status == exit_code
    assert refusal.value.standard_error == STANDARD_ERROR


def test_a_report_missing_a_requested_row_is_refused():
    with pytest.raises(CheckSetupFailedError) as refusal:
        SetupReport.from_completed_process(
            finished(
                *every_check_reported(SetupCheck.NOTES_BRANCH),
                standard_error=STANDARD_ERROR,
            )
        )

    assert refusal.value.missing_checks == [SetupCheck.NOTES_BRANCH]
    assert refusal.value.standard_error == STANDARD_ERROR


@pytest.mark.parametrize(
    "unreadable_row",
    [
        row("no_such_check", CheckResult(CheckStatus.OK, "an unknown check")),
        f"{SetupCheck.NOTES_FILE}{ReportRowField.SEPARATOR}no-such-status"
        f"{ReportRowField.SEPARATOR}an unknown status",
        f"{SetupCheck.NOTES_FILE}{ReportRowField.SEPARATOR}{CheckStatus.OK}",
    ],
    ids=["unknown check", "unknown status", "no detail"],
)
def test_a_report_with_an_unreadable_row_is_refused(unreadable_row: str):
    with pytest.raises(CheckSetupFailedError) as refusal:
        SetupReport.from_completed_process(
            finished(*every_check_reported(), unreadable_row)
        )

    assert refusal.value.unreadable_rows == [unreadable_row]
