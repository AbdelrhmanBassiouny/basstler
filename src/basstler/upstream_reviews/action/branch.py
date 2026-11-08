"""
Installing the upstream-reviews Action on the fork's own branch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from basstler.class_property import classproperty
from basstler.maintenance.remote_branch import RemoteBranch
from basstler.render_common import create_template_environment


# %% the Action branch's names


class ActionBranch(StrEnum):
    """
    Where the Action lives in the fork.
    """

    NAME = "basstler/upstream-reviews"
    """
    The branch, outside both the fork's default branch and the ``claude/`` branches
    stack maintenance owns.
    """

    @classproperty
    def install_command(cls) -> str:
        """
        How a reader is told to install the branch or bring it up to date.
        """
        return (
            '"${BASSTLER_PYTHON}" -m basstler.setup.steps install-upstream-reviews-action '
            "--branch-or-tag <the basstler release the session runs> "
            "(/setup-personal-notes runs it)"
        )


class ActionFile(StrEnum):
    """
    Every file on the branch.
    """

    WORKFLOW = ".github/workflows/upstream-reviews.yml"
    README = "README.md"
    REQUEST = "request.json"
    RESULT = "result.json"

    @property
    def file_name(self) -> str:
        """:return: The file's own name, without its directory."""
        return Path(self.value).name


class BasstlerSource(StrEnum):
    """
    Where the reusable workflow and the package a run installs come from.
    """

    REPOSITORY = "KAOS-repositories/basstler"
    REUSABLE_WORKFLOW = ".github/workflows/upstream-reviews-action.yml"
    LATEST_RELEASE = "main"
    """
    The branch every release is tagged on, so it always holds the latest one.
    """


# %% installing


class ActionTemplate(StrEnum):
    """
    The templates in :attr:`PackageLocation.TEMPLATES` the Action's files are rendered
    from.
    """

    WORKFLOW = "upstream_reviews_action_workflow.yml"
    """
    The caller workflow.
    """

    README = "upstream_reviews_action_readme.md"
    """
    What a reader browsing the fork's branches finds there.
    """

    def render(self, **context: Any) -> str:
        """
        :param context: The values the template substitutes, by name.
        :return: The rendered file, without its final newline.
        """
        return create_template_environment().get_template(self.value).render(**context)


class InstallationState(StrEnum):
    """
    How the fork's Action compares with the release installing it.
    """

    MISSING = "missing"
    STALE = "stale"
    CURRENT = "current"


@dataclass(frozen=True)
class ActionInstallation:
    """
    The Action as one basstler release writes it.
    """

    branch_or_tag: str
    """
    The basstler branch or release tag the workflow runs.
    """

    @classproperty
    def branch_or_tag_line(cls) -> re.Pattern[str]:
        """
        The line of an installed workflow naming the basstler branch or tag it runs.
        """
        return re.compile(
            r"^\s*basstler_branch_or_tag:\s*(?P<branch_or_tag>\S+)\s*$", re.MULTILINE
        )

    @property
    def workflow(self) -> str:
        """:return: The caller workflow."""
        return ActionTemplate.WORKFLOW.render(
            branch=ActionBranch.NAME,
            request=ActionFile.REQUEST,
            repository=BasstlerSource.REPOSITORY,
            reusable_workflow=BasstlerSource.REUSABLE_WORKFLOW,
            branch_or_tag=self.branch_or_tag,
        )

    @property
    def files(self) -> dict[ActionFile, str]:
        """:return: What installing writes."""
        return {
            ActionFile.WORKFLOW: self.workflow,
            ActionFile.README: ActionTemplate.README.render(
                request=ActionFile.REQUEST,
                workflow=ActionFile.WORKFLOW,
                result=ActionFile.RESULT,
            ),
        }

    def state(self, branch: RemoteBranch) -> tuple[InstallationState, str | None]:
        """
        :param branch: The fork's branch.
        :return: How it compares, and the branch or tag it runs when it is installed at
            all.
        """
        tip = branch.fetch()
        workflow = branch.git.file_at(tip, ActionFile.WORKFLOW) if tip else None
        if workflow is None:
            return InstallationState.MISSING, None
        match = self.branch_or_tag_line.search(workflow)
        installed = match["branch_or_tag"] if match else None
        if workflow == self.workflow:
            return InstallationState.CURRENT, installed
        return InstallationState.STALE, installed

    def install(self, branch: RemoteBranch) -> bool:
        """
        :param branch: The fork's branch.
        :return: Whether anything had to be pushed.
        """
        if self.state(branch)[0] is InstallationState.CURRENT:
            return False
        branch.write(
            self.files, f"Run basstler {self.branch_or_tag}'s upstream-reviews Action"
        )
        return True
