"""
The setup gate a skill passes before its first step: check-setup.sh reports only the
checks that skill needs, so a row it does not use never stops it.

Usage:
    basstler.sh setup.gate --skill <skill>
"""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter

from basstler.exit_codes import CommandFailure, ExitCode
from basstler.locations import ClaudeCodeVariable
from basstler.plugin_root import PluginRoot
from basstler.setup.report import (
    ReportRowField,
    SetupCheck,
    SetupCheckScript,
    SetupReport,
)
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% the checks a skill can need

SESSION_CHECKS = frozenset(
    {
        SetupCheck.TOOLING_FILES,
        SetupCheck.SESSION_START_HOOK,
        SetupCheck.CLAUDE_LOCAL_MD_IGNORED,
        SetupCheck.PACKAGE_DEPENDENCIES,
        SetupCheck.BASSTLER_VERSION,
        SetupCheck.CLAUDE_LOCAL_MD,
    }
)
"""
What every gated skill needs: the plugin, the session start it registers, and the
package its commands run at the plugin's own release.
"""

NOTES_READING_CHECKS = frozenset(
    {SetupCheck.NOTES_REPOSITORY_ACCESS, SetupCheck.NOTES_BRANCH}
)
"""
What reading the personal-notes branch needs.
"""

PLAN_SAVING_CHECKS = frozenset(
    {SetupCheck.NOTES_FILE, SetupCheck.PLAN_SITE_ACCESS, SetupCheck.GIT_IDENTITY}
)
"""
What saving a plan needs: the notes file beside it, a session that can start the plan
site's build, and the identity its commits carry.
"""

UPSTREAM_READING_CHECKS = frozenset(
    {SetupCheck.STACK_UPSTREAM, SetupCheck.UPSTREAM_REVIEWS_ACTION}
)
"""
What reading a branch's upstream pull request needs: the upstream named, and the fork's
Action, where installed, at the session's own release.
"""


class CheckSetupOption(StrEnum):
    """
    The check-setup.sh flags a gate passes.
    """

    ONLY = "--only"
    """
    Reports only the check named after it, and exits for the named checks alone.
    """

    REQUIRE_UPSTREAM = "--require-upstream"
    """
    Makes a project naming no upstream a check that needs setup.
    """


# %% the skills that gate on their setup


class GatedSkill(StrEnum):
    """
    The skills that check their setup before their first step, by the name a session
    invokes them with.
    """

    PLAN_CREATE = "plan-create"
    """
    Creates a plan on the personal-notes branch.
    """

    ADD_PLAN_ITEM = "add-plan-item"
    """
    Decides where new work belongs and adds it to a plan.
    """

    PLAN_ITEM_KICKOFF = "plan-item-kickoff"
    """
    Starts a plan item.
    """

    PLAN_ITEM_RESOLVE = "plan-item-resolve"
    """
    Unblocks or resumes a plan item already underway.
    """

    UPSTREAM_REVIEWS = "upstream-reviews"
    """
    Reports a fork branch's upstream pull request.
    """

    @property
    def required_checks(self) -> frozenset[SetupCheck]:
        """
        The checks this skill's steps depend on; no other row stops it.
        """
        if self is GatedSkill.UPSTREAM_REVIEWS:
            return SESSION_CHECKS | NOTES_READING_CHECKS | UPSTREAM_READING_CHECKS
        return SESSION_CHECKS | NOTES_READING_CHECKS | PLAN_SAVING_CHECKS

    @property
    def check_setup_arguments(self) -> list[str]:
        """
        The flags that make check-setup.sh report exactly :attr:`required_checks`,
        requiring an upstream when :attr:`SetupCheck.STACK_UPSTREAM` is among them.
        """
        upstream = (
            [CheckSetupOption.REQUIRE_UPSTREAM]
            if SetupCheck.STACK_UPSTREAM in self.required_checks
            else []
        )
        return [
            *upstream,
            *(
                argument
                for check in SetupCheck
                if check in self.required_checks
                for argument in (CheckSetupOption.ONLY, check)
            ),
        ]

    def gate(self, script: SetupCheckScript) -> SetupReport:
        """
        :param script: The clone's check-setup.sh.
        :return: What it reports for this skill's checks, exiting for them alone.
        :raises CheckSetupFailedError: If it exits with a status that carries no report,
            or its report lacks one of those checks or holds an unreadable row.
        """
        return SetupReport.from_completed_process(
            script.run(*self.check_setup_arguments), self.required_checks
        )


# %% the command line


class GateOption(StrEnum):
    """
    The options the command takes.
    """

    SKILL = "--skill"
    """
    The skill about to start.
    """


gate_app = App(help=__doc__)
"""
The command, which takes the skill about to start.
"""


@gate_app.default
def check_skill_setup(
    *, skill: Annotated[GatedSkill, Parameter(name=GateOption.SKILL)]
) -> ExitCode:
    """
    Print check-setup.sh's rows for the checks a skill needs, and exit as it does.

    :param skill: The skill about to start.
    :return: check-setup.sh's status for that skill's checks.
    """
    project_root = Path(
        os.environ.get(ClaudeCodeVariable.PROJECT_DIRECTORY, Path.cwd())
    )
    report = skill.gate(
        SetupCheckScript(project_root, os.environ, PluginRoot.locate(os.environ))
    )
    for check, result in report.results.items():
        logger.info(f"{check}{ReportRowField.SEPARATOR}{result.fields}")
    return report.exit_code


def main() -> ExitCode:
    """
    Run the gate, ending with the status a refusal carries.

    :return: The process exit code.
    """
    try:
        return gate_app(result_action="return_value")
    except CommandFailure as failure:
        logger.error(f"{failure}")
        return failure.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
