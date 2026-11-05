"""
Tests for :mod:`basstler.setup.report`: reading check-setup.sh's rows back.
"""

from __future__ import annotations

import subprocess

from basstler.exit_codes import SetupCheckExitCode
from basstler.setup.report import (
    CheckResult,
    CheckStatus,
    RepositoryCheck,
    ReportRowField,
    SetupCheck,
    SetupReport,
)

# %% rows that repeat


def finished(*rows: tuple[str, CheckResult]) -> subprocess.CompletedProcess[str]:
    """
    :param rows: The check each row reports on, and what it reports.
    :return: A finished check-setup.sh run that printed them in order.
    """
    return subprocess.CompletedProcess(
        [],
        SetupCheckExitCode.SUCCESS,
        "".join(
            f"{check}{ReportRowField.SEPARATOR}{result.fields}\n"
            for check, result in rows
        ),
    )


def test_every_repository_row_is_read_in_the_order_printed():
    first = CheckResult(CheckStatus.INFORMATIONAL, "a-first repository")
    second = CheckResult(CheckStatus.INFORMATIONAL, "a-second repository")

    report = SetupReport.from_completed_process(
        finished(
            (RepositoryCheck.PLAN_SITE_REPOSITORY, first),
            (RepositoryCheck.PLAN_SITE_REPOSITORY, second),
        )
    )

    assert report.repository_results == [first, second]


def test_a_repository_row_is_not_a_fixed_check():
    plan_site = CheckResult(CheckStatus.OK, "the own repository")

    report = SetupReport.from_completed_process(
        finished(
            (SetupCheck.PLAN_SITE, plan_site),
            (
                RepositoryCheck.PLAN_SITE_REPOSITORY,
                CheckResult(CheckStatus.INFORMATIONAL, "another repository"),
            ),
        )
    )

    assert report.results == {SetupCheck.PLAN_SITE: plan_site}
