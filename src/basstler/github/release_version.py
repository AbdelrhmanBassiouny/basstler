"""
Releases: every change merged to ``main`` is one once its tests pass, tagged on the
merge commit itself as the latest release with its patch, or the part a merged pull
request's ``release:minor`` or ``release:major`` label names, incremented.

Only the released plugin's manifest names the version.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from basstler.class_property import classproperty
from basstler.exceptions import DataclassException
from basstler.exit_codes import CommandFailure, ExitCode
from basstler.git.commands import GitCommandRunner
from basstler.json_model import ValidatedJSONModel
from basstler.locations import BasstlerRepositoryLocation
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""


class ReleaseVersionExitCode(ExitCode):
    """
    How a subcommand ended, as its caller reads it.
    """

    SUCCESS = 0
    """
    The subcommand did what it was asked.
    """

    MALFORMED_VERSION = 1
    """
    A version is not ``<major>.<minor>.<patch>``.
    """


class ReleaseCommand(StrEnum):
    """
    The subcommands this module answers.
    """

    UNRELEASED = "unreleased"
    """
    Print the commits since the latest release, whose pull requests choose its part.
    """

    RELEASE = "release"
    """
    Decide the release of everything since the latest one, for the workflow to tag.
    """

    PLUGIN = "plugin"
    """
    Print the commit the plugin release branch moves to for a release.
    """


class VersionPart(StrEnum):
    """
    The part of a version a release increments, ordered from least to most significant.
    """

    PATCH = "patch"
    """
    A fix, or any other change; what a release increments unless a label says otherwise.
    """

    MINOR = "minor"
    """
    A new capability.
    """

    MAJOR = "major"
    """
    An incompatible change.
    """

    @classproperty
    def label_prefix(cls) -> str:
        """:return: What a part's pull request label puts before its name."""
        return "release:"

    @property
    def significance(self) -> int:
        """:return: Its rank: a release of several parts increments the highest."""
        return list(VersionPart).index(self)

    @property
    def label(self) -> str:
        """:return: The pull request label that asks a release to increment it."""
        return f"{self.label_prefix}{self}"

    @classmethod
    def labelled(cls, label: str) -> VersionPart:
        """
        :param label: A pull request label's name.
        :return: The part it is the label of, else the patch.
        """
        return next((part for part in cls if part.label == label), cls.PATCH)


class ReleaseOutputKey(StrEnum):
    """
    The ``<key>=<value>`` lines ``release`` prints, in the form a workflow step appends
    to ``$GITHUB_OUTPUT``.
    """

    TAG = "tag"
    """
    The tag to create, or empty when there is nothing to release.
    """


class PullRequestLabel(ValidatedJSONModel):
    """
    One label on a merged pull request.
    """

    name: str
    """
    The label's name.
    """

    @property
    def part(self) -> VersionPart:
        """:return: The part it asks a release to increment."""
        return VersionPart.labelled(self.name)


class MergedPullRequest(ValidatedJSONModel):
    """
    A pull request merged since the latest release, and the labels it carries.
    """

    number: int
    """
    Its number.
    """

    labels: tuple[PullRequestLabel, ...]
    """
    Its labels.
    """

    @classmethod
    def read_all(cls, path: Path) -> tuple[MergedPullRequest, ...]:
        """
        :param path: A JSON array of pull request objects, one per entry GitHub returned;
            a pull request reached by several commits appears more than once.
        :return: Each pull request once.
        """
        parsed = (cls.from_json(entry) for entry in json.loads(path.read_text()))
        return tuple({pull.number: pull for pull in parsed}.values())

    @property
    def part(self) -> VersionPart:
        """:return: The most significant part its labels ask for."""
        return max(
            (label.part for label in self.labels),
            key=lambda part: part.significance,
            default=VersionPart.PATCH,
        )


@dataclass
class MalformedVersion(CommandFailure, DataclassException, ValueError):
    """
    Raised when a version is not ``<major>.<minor>.<patch>``.
    """

    text: str
    """
    The version as written.
    """

    @classproperty
    def exit_code(cls) -> ReleaseVersionExitCode:
        """:return: The status this kind of error ends a command with."""
        return ReleaseVersionExitCode.MALFORMED_VERSION

    def error_message(self) -> str:
        return f"{self.text!r} is not a <major>.<minor>.<patch> version."

    def suggest_correction(self) -> str:
        return (
            "Write three dot-separated numbers, e.g. 0.1.1, with no "
            f"{ReleaseVersion.tag_prefix!r} prefix; that belongs to the tag."
        )


@dataclass(frozen=True, order=True)
class ReleaseVersion:
    """
    A ``<major>.<minor>.<patch>`` version, ordered as releases are.
    """

    major: int
    """
    Incremented by an incompatible change.
    """

    minor: int
    """
    Incremented by a new capability.
    """

    patch: int
    """
    Incremented by any other change.
    """

    @classproperty
    def tag_prefix(cls) -> str:
        """:return: What a release's tag puts before its version."""
        return "v"

    @classmethod
    def parse(cls, text: str) -> ReleaseVersion:
        """
        :param text: A version as written, e.g. ``"0.1.1"``.
        :raises MalformedVersion: If it is not three dot-separated numbers.
        :return: The version.
        """
        parts = text.split(".")
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            raise MalformedVersion(text)
        return cls(*(int(part) for part in parts))

    @classmethod
    def from_tag(cls, tag: str) -> ReleaseVersion | None:
        """
        :param tag: A git tag.
        :return: The version it releases, or ``None`` if it is not a release tag.
        """
        if not tag.startswith(cls.tag_prefix):
            return None
        try:
            return cls.parse(tag.removeprefix(cls.tag_prefix))
        except MalformedVersion:
            return None

    def bumped(self, part: VersionPart) -> ReleaseVersion:
        """
        :param part: The part to increment; every part after it resets to zero.
        :return: The next version.
        """
        if part is VersionPart.MAJOR:
            return ReleaseVersion(self.major + 1, 0, 0)
        if part is VersionPart.MINOR:
            return ReleaseVersion(self.major, self.minor + 1, 0)
        return ReleaseVersion(self.major, self.minor, self.patch + 1)

    @property
    def tag(self) -> str:
        """:return: The tag the release of this version carries."""
        return f"{self.tag_prefix}{self}"

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class PlannedRelease:
    """
    What ``release`` decided to release.
    """

    version: ReleaseVersion
    """
    The version to tag.
    """

    def output_lines(self) -> str:
        """:return: The release as ``<key>=<value>`` lines for ``$GITHUB_OUTPUT``."""
        return f"{ReleaseOutputKey.TAG}={self.version.tag}"


@dataclass(frozen=True)
class Release:
    """
    One checkout, the commit checked out in it, and the releases before it.
    """

    checkout: Path
    """
    The root of the checkout.
    """

    @classproperty
    def first(cls) -> ReleaseVersion:
        """:return: The version a repository with no release yet releases."""
        return ReleaseVersion(0, 1, 0)

    @property
    def git(self) -> GitCommandRunner:
        """:return: A runner for git in the checkout."""
        return GitCommandRunner(working_directory=self.checkout)

    @staticmethod
    def released(tags: str) -> list[ReleaseVersion]:
        """
        :param tags: Tag names, one per line.
        :return: The versions those that are release tags release.
        """
        versions = (ReleaseVersion.from_tag(tag) for tag in tags.splitlines())
        return [version for version in versions if version]

    def latest_release(self) -> ReleaseVersion | None:
        """
        :return: The highest version whose tag the checked-out commit contains, or
            ``None`` before the first release.
        """
        tags = self.git.run("tag", "--merged", "HEAD", "--list")
        return max(self.released(tags), default=None)

    def is_released(self) -> bool:
        """
        :return: Whether a release tag already contains the checked-out commit, as when
            a later merge's run has released it, or this run is run again.
        """
        return bool(self.released(self.git.run("tag", "--contains", "HEAD", "--list")))

    def changed_since(self, release: ReleaseVersion) -> bool:
        """
        :param release: A released version.
        :return: Whether the checked-out commit differs from that release.
        """
        return not self.git.attempt("diff", "--quiet", release.tag, "HEAD").succeeded

    def unreleased_commits(self) -> tuple[str, ...]:
        """
        :return: The commits on the first-parent line since the latest release, oldest
            first: one merge commit per merged pull request, plus any direct push.
        """
        latest = self.latest_release()
        revisions = f"{latest.tag}..HEAD" if latest else "HEAD"
        listed = self.git.run("rev-list", "--first-parent", "--reverse", revisions)
        return tuple(listed.splitlines())

    def plan(self, merged: tuple[MergedPullRequest, ...]) -> PlannedRelease | None:
        """
        Decide the release of everything since the latest one: the latest release with
        the most significant part any merged pull request's labels ask for, else its
        patch, incremented.

        :param merged: The pull requests merged since the latest release.
        :return: The release, or ``None`` when nothing changed since the latest one.
        """
        if self.is_released():
            return None
        latest = self.latest_release()
        if latest is None:
            return PlannedRelease(self.first)
        if not self.changed_since(latest):
            return None
        part = max(
            (pull.part for pull in merged),
            key=lambda part: part.significance,
            default=VersionPart.PATCH,
        )
        return PlannedRelease(latest.bumped(part))


@dataclass(frozen=True)
class PluginRelease:
    """
    The checked-out commit's plugin, alone at the root of a commit whose manifest names
    the release's version.
    """

    release: Release
    """
    The checkout whose plugin is released.
    """

    version: ReleaseVersion
    """
    The version the release tags.
    """

    previous: str
    """
    The plugin release branch, which the commit descends from so the branch only moves
    forward; it need not exist yet.
    """

    def commit(self) -> str:
        """
        :return: The new commit, its first parent the plugin's own history.
        """
        git = self.release.git
        plugin = git.run(
            "subtree",
            "split",
            "--quiet",
            f"--prefix={BasstlerRepositoryLocation.PLUGIN}",
            "HEAD",
        )
        manifest_path = BasstlerRepositoryLocation.PLUGIN_MANIFEST.path_in_plugin
        manifest = json.loads(git.file_at(plugin, manifest_path))
        manifest["version"] = str(self.version)
        previous = git.commit_or_none(self.previous)
        return git.commit_files(
            plugin,
            {manifest_path.as_posix(): json.dumps(manifest, indent=2)},
            f"Release the plugin at {self.version.tag}",
            merged_parents=(previous,) if previous else (),
        )


class ReleaseCommandLine:
    """
    The command line: its arguments, and the subcommand they name.
    """

    @classmethod
    def parser(cls) -> argparse.ArgumentParser:
        """
        :return: The parser for every subcommand and its arguments.
        """
        parser = argparse.ArgumentParser(
            description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
        )
        subcommands = parser.add_subparsers(dest="subcommand", required=True)
        unreleased_parser = subcommands.add_parser(
            ReleaseCommand.UNRELEASED,
            help="Print the commits since the latest release, oldest first",
        )
        release_parser = subcommands.add_parser(
            ReleaseCommand.RELEASE,
            help="Decide the release of everything since the latest one",
        )
        release_parser.add_argument(
            "--pull-requests",
            type=Path,
            help="A JSON array of the pull requests GitHub associates with the "
            "unreleased commits (default: none, so a patch release)",
        )
        plugin_parser = subcommands.add_parser(
            ReleaseCommand.PLUGIN,
            help="Print the commit the plugin release branch moves to for a release",
        )
        plugin_parser.add_argument(
            "--tag", required=True, help="The tag the release carries, e.g. v1.2.3"
        )
        plugin_parser.add_argument(
            "--previous",
            required=True,
            help="The plugin release branch as the checkout names it, which need not "
            "exist yet",
        )
        for subcommand_parser in (unreleased_parser, release_parser, plugin_parser):
            subcommand_parser.add_argument(
                "--checkout",
                type=Path,
                default=Path.cwd(),
                help="The checkout's root (default: the current directory)",
            )
        return parser

    @classmethod
    def run(cls, arguments: argparse.Namespace) -> ReleaseVersionExitCode:
        """
        Carry out the subcommand *arguments* name.

        :param arguments: The parsed command line.
        :return: How the subcommand ended.
        """
        release = Release(arguments.checkout)
        try:
            match arguments.subcommand:
                case ReleaseCommand.UNRELEASED:
                    for commit in release.unreleased_commits():
                        logger.info(commit)
                case ReleaseCommand.RELEASE:
                    merged = (
                        MergedPullRequest.read_all(arguments.pull_requests)
                        if arguments.pull_requests
                        else ()
                    )
                    planned = release.plan(merged)
                    if planned is None:
                        logger.warning("Nothing changed since the latest release.")
                    else:
                        logger.info(planned.output_lines())
                case ReleaseCommand.PLUGIN:
                    released = ReleaseVersion.parse(
                        arguments.tag.removeprefix(ReleaseVersion.tag_prefix)
                    )
                    plugin = PluginRelease(release, released, arguments.previous)
                    logger.info(plugin.commit())
        except MalformedVersion as error:
            logger.error(str(error))
            return error.exit_code
        return ReleaseVersionExitCode.SUCCESS


def main() -> ReleaseVersionExitCode:
    """
    Parse arguments and dispatch to the requested subcommand.
    """
    return ReleaseCommandLine.run(ReleaseCommandLine.parser().parse_args())


if __name__ == "__main__":
    sys.exit(main())
