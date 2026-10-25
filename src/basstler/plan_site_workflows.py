#!/usr/bin/env python3
"""
The workflows that publish the plan site from its registry repository.

``plan-site.yml`` on the default branch builds the site and deploys it to Pages, which
deploys only from that branch. ``plan-site-trigger.yml`` on the notes branch starts that
build whenever a plan is pushed; this module installs it.

Usage:
    python3 -m basstler.plan_site_workflows install-trigger
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath


from basstler.exceptions import NotesBranchMissingError
from basstler.locations import ClaudeCodeVariable, ProjectLocation
from basstler.maintenance_git_commands import GitCommandFailed, GitCommandRunner
from basstler.personal_notes_branch import (
    NotesBranchWriter,
    NotesWriteOutcome,
    PersonalNotesBranch,
    PersonalNotesLocation,
)
from basstler.render_common import PackageTemplate
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% the trigger


class PlanSiteTemplate(PackageTemplate):
    """
    The templates the plan site's workflows are rendered from.
    """

    TRIGGER = "plan_site_trigger_workflow.yml"
    """
    The notes branch's workflow starting the build.
    """


@dataclass(frozen=True)
class PlanSiteTrigger:
    """
    The notes branch's workflow that starts the plan site's build on a plan push.
    """

    notes_branch: str
    """
    The notes branch the workflow lives on and watches.
    """

    @property
    def workflow(self) -> str:
        """
        :return: The workflow file, without its final newline.
        """
        return PlanSiteTemplate.TRIGGER.render(
            notes_branch=self.notes_branch,
            plans_directory=ProjectLocation.PLANS.as_posix(),
            build_workflow=ProjectLocation.PLAN_SITE_WORKFLOW.name,
        )

    def install(self, branch: PersonalNotesBranch) -> NotesWriteOutcome:
        """
        Write the workflow onto *branch*, or bring it up to date.

        :param branch: The notes branch, which must be the one this trigger watches.
        :return: Whether anything was pushed.
        """
        return NotesBranchWriter(branch).write(
            {
                PurePosixPath(
                    ProjectLocation.PLAN_SITE_TRIGGER_WORKFLOW.as_posix()
                ): f"{self.workflow}\n"
            },
            "Start the plan site build on every plan push",
        )


# %% command line


class PlanSiteCommand(StrEnum):
    """
    The steps this module performs.
    """

    INSTALL_TRIGGER = "install-trigger"
    """
    Write the trigger onto this clone's notes branch, or bring it up to date.
    """


def main(argv: list[str] | None = None) -> int:
    """
    Perform the step the command names.

    :param argv: The arguments to parse, defaulting to the process's own.
    :return: The process exit status.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        PlanSiteCommand.INSTALL_TRIGGER,
        help="write the plan site trigger onto this clone's notes branch",
    )
    parser.parse_args(argv)
    project_root = Path(
        os.environ.get(ClaudeCodeVariable.PROJECT_DIRECTORY, Path.cwd())
    )
    location = PersonalNotesLocation.resolve(project_root, os.environ)
    branch = PersonalNotesBranch(location, GitCommandRunner(project_root))
    try:
        outcome = PlanSiteTrigger(location.branch).install(branch)
    except (GitCommandFailed, NotesBranchMissingError) as failure:
        logger.error(failure)
        return 1
    logger.info(
        f"{ProjectLocation.PLAN_SITE_TRIGGER_WORKFLOW} on {location.branch}: {outcome}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
