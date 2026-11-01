"""
Calls into the plugin's shell configuration, ``resolve-personal-notes-config.sh``.

The shell configuration is where the personal-notes remote and branch precedence is
decided. A module that needs one of its answers sources it and calls its function,
rather than re-deriving the precedence, so the module and the hook scripts can never
disagree. This is the one place that does so.
"""

from __future__ import annotations

import os
import subprocess
from enum import StrEnum
from pathlib import Path, PurePosixPath

from basstler.bash import Bash
from basstler.locations import PluginLocation
from basstler.plugin_root import PluginRoot


class FetchedBranchReference(StrEnum):
    """
    Where the shell configuration keeps a branch it fetched, so a later fetch of
    anything else never moves it the way it moves ``FETCH_HEAD``.
    """

    PERSONAL_NOTES = "refs/basstler/personal-notes"
    """
    The personal-notes branch, as
    :attr:`ShellConfigurationFunction.FETCH_PERSONAL_NOTES_BRANCH` last fetched it; the
    shell configuration's ``PERSONAL_NOTES_REFERENCE``.
    """

    def file_at(self, path: str | PurePosixPath) -> str:
        """
        :param path: A file's path relative to the branch's root.
        :return: The git object name of that file on the fetched branch.
        """
        return f"{self}:{path}"


class ShellConfigurationFunction(StrEnum):
    """
    The functions of the shell configuration, named once here for every caller.
    """

    FETCH_PERSONAL_NOTES_BRANCH = "fetch_personal_notes_branch"
    """
    Fetches the personal-notes branch into
    :attr:`FetchedBranchReference.PERSONAL_NOTES`.

    Falls back to the current branch's upstream remote when the configured one does not
    carry the branch.
    """

    RECORDED_GIT_IDENTITY = "recorded_git_identity"
    """
    Prints the commit identity the personal-notes branch records, as its name and email
    separated by a tab.
    """

    PLAN_ID_FOR_BRANCH = "plan_id_for_branch"
    """
    Prints the plan the fetched branch index says tracks the branch it is given, and
    nothing when no plan does.
    """

    REPOSITORY_NAME = "repository_name"
    """
    Prints the project's ``origin`` as ``owner/repo``.
    """

    PLAN_SITE_PAGE_URL = "plan_site_page_url"
    """
    Prints the address of the project's page on the plan site, of one of its plans, or
    of one item's card, and fails when the fetched hub file names no site.
    """

    BASSTLER_PACKAGE_SOURCE = "basstler_package_source"
    """
    Prints what the package is installed from: the checkout the plugin sits in, else its
    repository at the latest release a session start recorded.
    """

    BASSTLER_BRANCH_OR_TAG = "basstler_branch_or_tag"
    """
    Prints the basstler branch or tag the package is installed at outside a checkout:
    the latest release a session start recorded, else ``main``.
    """

    RECORD_LATEST_BASSTLER_RELEASE = "record_latest_basstler_release"
    """
    Records the highest release tag of the package's repository, for a plugin outside a
    checkout, which :attr:`BASSTLER_PACKAGE_SOURCE` then installs.
    """

    def run(
        self, project_root: Path | None = None, *arguments: str
    ) -> subprocess.CompletedProcess[str]:
        """
        Source the shell configuration and call this function.

        :param project_root: The repository to run within; the current directory if not
            given.
        :param arguments: The arguments to call the function with.
        :return: The completed process, with output captured as text.
        """
        configuration = PluginRoot.locate(os.environ).path_of(
            PluginLocation.PERSONAL_NOTES_CONFIGURATION_SCRIPT
        )
        return subprocess.run(
            Bash.locate(os.environ).command(
                "-c",
                f'source "{configuration}" && {self} "$@"',
                PluginLocation.PERSONAL_NOTES_CONFIGURATION_SCRIPT.name,
                *arguments,
            ),
            cwd=project_root,
            capture_output=True,
            text=True,
        )
