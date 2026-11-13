"""
The environment variables this package reads, grouped by who sets them.

Every group is an :class:`EnvironmentVariable`, so reading one is the same call
whichever group it belongs to, and a variable is named once rather than typed out where
it is read.
"""

from __future__ import annotations

import os
from enum import StrEnum

from basstler.github.credential import CredentialOrigin


class EnvironmentFlag(StrEnum):
    """
    The values a variable that switches something on or off is set to.
    """

    TRUE = "true"
    """
    The thing the variable stands for is on.
    """


class EnvironmentVariable(StrEnum):
    """
    An environment variable, named by its value.

    The base every group of them extends.
    """

    def read(self) -> str | None:
        """
        :return: The variable's value in this process's environment, or ``None`` when it
            is not set.
        """
        return os.environ.get(self)

    def is_true(self) -> bool:
        """:return: Whether the variable is set to :attr:`EnvironmentFlag.TRUE`."""
        return self.read() == EnvironmentFlag.TRUE


class OperatingSystemVariable(EnvironmentVariable):
    """
    The variables the operating system sets for every process.
    """

    EXECUTABLE_SEARCH_PATH = "PATH"
    """
    The directories a program is searched for in.
    """

    WINDOWS_DIRECTORY = "SYSTEMROOT"
    """
    The Windows installation's own directory, set only on Windows, spelled as Windows
    lists it in a copy of the environment.
    """


class GitBashVariable(EnvironmentVariable):
    """
    The variables Git for Windows' bash (MSYS2) reads before it starts a program.
    """

    ARGUMENT_CONVERSION_EXCLUSIONS = "MSYS2_ARG_CONV_EXCL"
    """
    The ``;``-separated prefixes of the arguments it passes on as written rather than
    rewriting them as Windows paths.
    """


class GitVariable(EnvironmentVariable):
    """
    The variables git reads that this package, or its tests, set for the commands run.
    """

    INDEX_FILE = "GIT_INDEX_FILE"
    """
    The index git stages into, in place of the clone's own.
    """

    CONFIGURATION_COUNT = "GIT_CONFIG_COUNT"
    """
    How many configuration entries the environment passes to git.
    """

    CONFIGURATION_KEY_PREFIX = "GIT_CONFIG_KEY_"
    """
    Followed by an entry's index, names the variable holding that entry's key.
    """

    CONFIGURATION_VALUE_PREFIX = "GIT_CONFIG_VALUE_"
    """
    Followed by an entry's index, names the variable holding that entry's value.
    """

    COMMITTER_DATE = "GIT_COMMITTER_DATE"
    """
    The date git records as a new commit's committer date, in place of the clock's.
    """


class GitHubCredentialVariable(CredentialOrigin, EnvironmentVariable):
    """
    The variables a GitHub token is read from, in the order they are tried.
    """

    GH_TOKEN = "GH_TOKEN"
    """
    The token the ``gh`` CLI reads, preferred where both are set.
    """

    GITHUB_TOKEN = "GITHUB_TOKEN"
    """
    The token GitHub Actions hands a workflow.
    """

    def describe_credential(self) -> str:
        """
        :return: :meth:`CredentialOrigin.describe_credential`: the token in this
            variable.
        """
        return f"the token in {self}"

    def suggest_renewal(self) -> str:
        """
        :return: :meth:`CredentialOrigin.suggest_renewal`: set a valid token in this
            variable.
        """
        return f"Set a valid token in {self}."

    @classmethod
    def first_set(cls) -> GitHubCredentialVariable | None:
        """
        :return: The first variable holding a non-empty token, in the order they are
            tried, or ``None`` when none does.
        """
        return next((variable for variable in cls if variable.read()), None)

    @classmethod
    def first_token(cls) -> str | None:
        """
        :return: The first non-empty token, in the order the variables are tried, or
            ``None`` when none is set.
        """
        variable = cls.first_set()
        return None if variable is None else variable.read()


class GitHubActionsVariable(EnvironmentVariable):
    """
    The variables a GitHub Actions runner sets for the steps it runs.
    """

    STEP_SUMMARY = "GITHUB_STEP_SUMMARY"
    """
    The file a step appends its Markdown job summary to.
    """

    OUTPUT = "GITHUB_OUTPUT"
    """
    The file a step appends its ``<key>=<value>`` outputs to.
    """

    RUNNER_TEMPORARY_DIRECTORY = "RUNNER_TEMP"
    """
    A directory the runner empties for each job, which steps hand files through.
    """

    REPOSITORY_OWNER = "GITHUB_REPOSITORY_OWNER"
    """
    The owner of the repository the workflow runs in.
    """
