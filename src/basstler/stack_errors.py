"""
The errors the stack commands end with, each carrying the status it exits with.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from basstler.class_property import classproperty
from basstler.exit_codes import CommandFailure, StackExitCode
from basstler.repository import Repository
from basstler.stack_configuration import StackSetting

if TYPE_CHECKING:
    from basstler.stack_settings import Remote

# %% remotes


@dataclass
class ForkRemoteNotFoundError(CommandFailure, LookupError):
    """
    Raised when no remote points at a repository other than the upstream.
    """

    @classproperty
    def exit_code(cls) -> StackExitCode:
        """:return: The status this kind of error ends a command with."""
        return StackExitCode.REMOTES_UNRESOLVED

    upstream_repository: Repository
    """The upstream every candidate turned out to be."""

    def __str__(self) -> str:
        """:return: What was searched for and why nothing qualified."""
        return (
            f"no remote points at a fork: every remote is {self.upstream_repository}. "
            f"Add a remote for your fork, or set {StackSetting.FORK_REPOSITORY} in stack.toml."
        )


@dataclass
class AmbiguousForkRemoteError(CommandFailure, LookupError):
    """
    Raised when several remotes could each be the fork.
    """

    @classproperty
    def exit_code(cls) -> StackExitCode:
        """:return: The status this kind of error ends a command with."""
        return StackExitCode.REMOTES_UNRESOLVED

    candidates: tuple[Remote, ...]
    """The remotes that are not the upstream, in the order git reported them."""

    def __str__(self) -> str:
        """:return: The candidates and how to disambiguate them."""
        listed = ", ".join(
            f"{remote.name} -> {remote.repository}" for remote in self.candidates
        )
        return (
            f"several remotes could be the fork ({listed}). "
            f"Set {StackSetting.FORK_REPOSITORY} in stack.toml to say which."
        )


# %% the board


@dataclass
class BoardUnavailable(CommandFailure, RuntimeError):
    """
    Raised when ``board.json`` is missing.
    """

    @classproperty
    def exit_code(cls) -> StackExitCode:
        """:return: The status this kind of error ends a command with."""
        return StackExitCode.BOARD_UNAVAILABLE

    board: Path
    """
    Where the board export was looked for.
    """

    def __str__(self) -> str:
        """:return: Which file is missing."""
        return f"{self.board.name} not found"


# %% label writes


@dataclass
class ContradictoryLabelWriteError(CommandFailure, ValueError):
    """
    Raised when one write is asked both to carry a label and to drop it.
    """

    @classproperty
    def exit_code(cls) -> StackExitCode:
        """:return: The status this kind of error ends a command with."""
        return StackExitCode.USAGE

    labels: tuple[str, ...]
    """
    The labels asked for in both directions.
    """

    def __str__(self) -> str:
        """:return: Which labels contradict, and why no outcome is safe."""
        return (
            f"cannot both add and remove {', '.join(self.labels)}: "
            f"either outcome would be a guess at what was meant"
        )


# %% promotion links


@dataclass
class PromotionLinkTooLongError(CommandFailure, ValueError):
    """
    Raised when a link cannot fit even with its whole description dropped.
    """

    @classproperty
    def exit_code(cls) -> StackExitCode:
        """:return: The status this kind of error ends a command with."""
        return StackExitCode.USAGE

    branch: str
    """
    The branch whose link was being built.
    """
    length_without_a_description: int
    """
    How long the URL already is before any description is added.
    """
    url_character_limit: int
    """
    The longest URL the link may be.
    """

    def __str__(self) -> str:
        """:return: Which link overflowed, and by how much before the body counts."""
        return (
            f"the compare link for {self.branch} is {self.length_without_a_description} "
            f"characters before its description, over the "
            f"{self.url_character_limit}-character limit: shorten the title"
        )
