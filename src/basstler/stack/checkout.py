"""
The git checkout the stack commands run in, asked through plain ``git``.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from basstler.stack.settings import Configuration

# %% git vocabulary


class GitArgument(StrEnum):
    """
    The git executable, subcommands and flags the stack commands run.
    """

    GIT = "git"
    """
    The git executable itself.
    """

    REMOTE = "remote"
    """
    Lists the remotes, or with :attr:`GET_URL` reads one's URL.
    """

    GET_URL = "get-url"
    """
    The :attr:`REMOTE` subcommand reading a remote's fetch URL.
    """

    REVISION_LIST = "rev-list"
    """
    Lists the commits in a revision range.
    """

    COUNT = "--count"
    """
    Makes :attr:`REVISION_LIST` print how many commits there are instead of naming them.
    """

    FETCH = "fetch"
    """
    Updates references from a remote.
    """

    QUIET = "-q"
    """
    Silences a fetch's progress output.
    """

    MERGE_BASE = "merge-base"
    """
    Answers questions about two commits' common history.
    """

    IS_ANCESTOR = "--is-ancestor"
    """
    Makes :attr:`MERGE_BASE` answer whether the first commit is contained in the second.
    """

    MERGE_TREE = "merge-tree"
    """
    Merges two commits without touching the work tree.
    """

    WRITE_TREE = "--write-tree"
    """
    Makes :attr:`MERGE_TREE` merge for real and report conflicts in its exit status.
    """

    CAT_FILE = "cat-file"
    """
    Reads an object out of the repository.
    """

    EXISTS = "-e"
    """
    Makes :attr:`CAT_FILE` answer only whether the object exists.
    """

    ADD = "add"
    """
    The :attr:`REMOTE` subcommand adding a remote.
    """

    FETCH_HEAD = "FETCH_HEAD"
    """
    The reference to whatever the last fetch brought in.
    """

    SHOW = "show"
    """
    Prints an object's content.
    """

    BRANCH = "branch"
    """
    Reports on local branches.
    """

    SHOW_CURRENT = "--show-current"
    """
    Makes :attr:`BRANCH` print the checked-out branch.
    """

    FOR_EACH_REFERENCE = "for-each-ref"
    """
    Lists references, optionally only those a commit contains.
    """

    MERGED = "--merged"
    """
    Makes :attr:`FOR_EACH_REFERENCE` list only the references the given commit contains.
    """

    REFERENCE_NAME_FORMAT = "--format=%(refname)"
    """
    Makes :attr:`FOR_EACH_REFERENCE` print each reference's full name and nothing else.
    """

    REMOTE_REFERENCES = "refs/remotes"
    """
    The namespace holding every remote's tracking references.
    """


class MergeTreeStatus(IntEnum):
    """
    The exit statuses of ``git merge-tree --write-tree`` that answer the question asked.
    """

    CLEAN = 0
    """
    The two commits merge without a conflict.
    """

    CONFLICTED = 1
    """
    Merging them conflicts.
    """


# %% the checkout


@dataclass(frozen=True)
class CurrentCheckout:
    """
    The git checkout the command runs in.
    """

    @staticmethod
    def run(*arguments: str) -> subprocess.CompletedProcess[str]:
        """
        Run a git command in the working directory, capturing its output.

        :param arguments: The git subcommand and its arguments.
        :return: The finished command.
        """
        return subprocess.run(
            [GitArgument.GIT, *arguments],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )

    @classmethod
    def output(cls, *arguments: str) -> str:
        """
        :param arguments: The git subcommand and its arguments.
        :return: The command's stripped stdout, empty when it failed.
        """
        return cls.run(*arguments).stdout.strip()

    @classmethod
    def succeeds(cls, *arguments: str) -> bool:
        """
        :param arguments: The git subcommand and its arguments.
        :return: Whether the command exited successfully.
        """
        return cls.run(*arguments).returncode == 0

    @classmethod
    def remote_urls(cls) -> dict[str, str]:
        """
        :return: Every remote in this checkout, mapped to its fetch URL.
        """
        listed = cls.output(GitArgument.REMOTE).splitlines()
        return {
            name: cls.output(GitArgument.REMOTE, GitArgument.GET_URL, name)
            for name in listed
            if name
        }

    @classmethod
    def commit_count(cls, revision_range: str) -> int | None:
        """
        :param revision_range: A git revision-range expression.
        :return: The number of commits in it, or ``None`` if a reference is missing.
        """
        counted = cls.output(
            GitArgument.REVISION_LIST, GitArgument.COUNT, revision_range
        )
        return int(counted) if counted.isdigit() else None

    @classmethod
    def fetch(cls, configuration: Configuration, branches: list[str]) -> None:
        """
        Refresh the references the stack names, so drift and landed branches are current.

        :param configuration: The static configuration.
        :param branches: The fork branch names to fetch.
        """
        cls.output(
            GitArgument.FETCH,
            configuration.upstream_remote,
            configuration.upstream_base,
            GitArgument.QUIET,
        )
        cls.output(
            GitArgument.FETCH, configuration.fork_remote, GitArgument.QUIET, *branches
        )

    @classmethod
    def ancestry_predicate(
        cls, configuration: Configuration
    ) -> Callable[[str, str], bool]:
        """
        :param configuration: The resolved configuration naming the fork remote.
        :return: A predicate testing whether a fork branch is contained in a local branch.
        """

        def is_ancestor(candidate: str, descendant: str) -> bool:
            return cls.succeeds(
                GitArgument.MERGE_BASE,
                GitArgument.IS_ANCESTOR,
                configuration.reference_on_fork(candidate),
                descendant,
            )

        return is_ancestor


# %% which fork branches have landed upstream


@dataclass(frozen=True)
class LandedBranches:
    """
    The fork branches the upstream base contained when this snapshot was taken.
    """

    configuration: Configuration
    """
    The resolved configuration naming the fork remote and the upstream base.
    """

    landed_references: frozenset[str]
    """
    The full names of the fork's tracking references the upstream base contained.
    """

    @classmethod
    def from_checkout(cls, configuration: Configuration) -> LandedBranches:
        """
        :param configuration: The resolved configuration naming the fork remote and the
            upstream base.
        :return: The fork branches the current checkout's upstream base contains now.
        """
        listed = CurrentCheckout.output(
            GitArgument.FOR_EACH_REFERENCE,
            f"{GitArgument.MERGED}={configuration.upstream_remote}/{configuration.upstream_base}",
            GitArgument.REFERENCE_NAME_FORMAT,
            f"{GitArgument.REMOTE_REFERENCES}/{configuration.fork_remote}/",
        )
        return cls(configuration, frozenset(listed.splitlines()))

    def contains(self, name: str) -> bool:
        """
        :param name: A fork branch name.
        :return: Whether the upstream base contained the fork's copy of it.
        """
        return (
            f"{GitArgument.REMOTE_REFERENCES}/{self.configuration.reference_on_fork(name)}"
            in self.landed_references
        )
