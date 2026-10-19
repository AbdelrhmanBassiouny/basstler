"""
Releases: every change to ``main`` is one, and the pull request making it names its version.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from basstler.class_property import classproperty
from basstler.exit_codes import CommandFailure, ExitCode
from basstler.locations import CheckoutLocation
from basstler.maintenance_git_commands import GitCommandRunner
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

    UNEXPECTED_VERSION = 1
    """
    The manifest names a version other than the next patch, minor or major one after the
    latest release, though something changed since it.
    """

    VERSION_REFERENCE_MISSING = 2
    """
    A file that should name the release does not; nothing was written.
    """

    MALFORMED_VERSION = 3
    """
    A version is not ``<major>.<minor>.<patch>``.
    """


class ReleaseCommand(StrEnum):
    """
    The subcommands this module answers.
    """

    CHECK = "check"
    """
    Fail if the manifest does not name the version merging the checkout releases.
    """

    BUMP = "bump"
    """
    Write a version everywhere a version is written.
    """

    RELEASE = "release"
    """
    Name the tag releasing everything since the latest release, for the workflow to put
    on the merged commit.
    """


class VersionPart(StrEnum):
    """
    The part of a version a bump increments.
    """

    MAJOR = "major"
    """
    An incompatible change.
    """

    MINOR = "minor"
    """
    A new capability.
    """

    PATCH = "patch"
    """
    A fix, or any other change; the part a bump increments unless told otherwise.
    """


class ReleaseOutputKey(StrEnum):
    """
    The ``<key>=<value>`` lines ``release`` prints, in the form a workflow step appends to
    ``$GITHUB_OUTPUT``.
    """

    TAG = "tag"
    """
    The tag to create; ``release`` prints nothing when there is nothing to release.
    """


@dataclass
class UnexpectedVersion(CommandFailure, ValueError):
    """
    Raised when the manifest names a version other than the next patch, minor or major
    one after the latest release, though something changed since it.
    """

    version: ReleaseVersion
    """
    The version the manifest names.
    """

    allowed: tuple[ReleaseVersion, ...]
    """
    The versions it may name.
    """

    @classproperty
    def exit_code(cls) -> ReleaseVersionExitCode:
        """:return: The status this kind of error ends a command with."""
        return ReleaseVersionExitCode.UNEXPECTED_VERSION

    def __str__(self) -> str:
        allowed = ", ".join(str(version) for version in self.allowed)
        return (
            f"{CheckoutLocation.PLUGIN_MANIFEST} names {self.version}, but a change "
            f"since the latest release must name one of: {allowed}. Write the next "
            "patch everywhere a version is written with `python -m "
            "basstler.release_version bump` (or `--part minor`, or `--part major`)."
        )


@dataclass
class VersionReferenceMissing(CommandFailure, LookupError):
    """
    Raised when a file that should name the release names no version.
    """

    path: Path
    """
    The file, relative to the checkout.
    """

    @classproperty
    def exit_code(cls) -> ReleaseVersionExitCode:
        """:return: The status this kind of error ends a command with."""
        return ReleaseVersionExitCode.VERSION_REFERENCE_MISSING

    def __str__(self) -> str:
        return (
            f"{self.path} names no version where one is expected; nothing was written."
        )


@dataclass
class MalformedVersion(CommandFailure, ValueError):
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

    def __str__(self) -> str:
        return f"{self.text!r} is not a <major>.<minor>.<patch> version."


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
class VersionReference:
    """
    One file that writes the release's version, and how it writes it.
    """

    path: CheckoutLocation
    """
    The file, relative to a checkout.
    """

    pattern: re.Pattern[str]
    """
    Where the version is written in it: every match's ``version`` group is one.
    """

    @classmethod
    def manifest(cls) -> VersionReference:
        """
        :return: The plugin manifest's version, the one the build and the check read.
        """
        return cls(
            CheckoutLocation.PLUGIN_MANIFEST,
            re.compile(r'"version"\s*:\s*"(?P<version>[^"]+)"'),
        )

    @classmethod
    def every(cls) -> tuple[VersionReference, ...]:
        """
        :return: Every place a version is written: the manifest, and each reference to
            the release tag.
        """
        return (
            cls.manifest(),
            cls(
                CheckoutLocation.EXAMPLE_CALLER,
                re.compile(r"(?:@|basstler_ref: )v(?P<version>[0-9][^\s]*)"),
            ),
        )

    def versions_in(self, checkout: Path) -> tuple[str, ...]:
        """
        :param checkout: The checkout's root.
        :return: Every version the file writes, in order.
        """
        text = (checkout / self.path).read_text()
        return tuple(match["version"] for match in self.pattern.finditer(text))

    def rewritten(self, checkout: Path, version: ReleaseVersion) -> str:
        """
        :param checkout: The checkout's root.
        :param version: The version to write.
        :raises VersionReferenceMissing: If the file names no version.
        :return: The file's text with every version it writes replaced by *version*.
        """
        text = (checkout / self.path).read_text()
        if self.pattern.search(text) is None:
            raise VersionReferenceMissing(self.path)
        return self.pattern.sub(lambda match: self.with_version(match, version), text)

    @staticmethod
    def with_version(match: re.Match[str], version: ReleaseVersion) -> str:
        """
        :param match: A match of :attr:`pattern`.
        :param version: The version to put in place of its ``version`` group.
        :return: The matched text, with the version replaced.
        """
        start, end = match.span("version")
        offset = match.start()
        return match[0][: start - offset] + str(version) + match[0][end - offset :]


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
    One checkout, the version its plugin manifest names, and the releases before it.
    """

    checkout: Path
    """
    The root of the checkout.
    """

    @property
    def git(self) -> GitCommandRunner:
        """:return: A runner for git in the checkout."""
        return GitCommandRunner(working_directory=self.checkout)

    @property
    def version(self) -> ReleaseVersion:
        """:return: The version the checkout's plugin manifest declares."""
        manifest = VersionReference.manifest()
        return ReleaseVersion.parse(manifest.versions_in(self.checkout)[0])

    def latest_release(self) -> ReleaseVersion | None:
        """
        :return: The highest version whose tag the checked-out commit contains, or
            ``None`` before the first release.
        """
        tags = self.git.run("tag", "--merged", "HEAD", "--list").splitlines()
        released = [ReleaseVersion.from_tag(tag) for tag in tags]
        return max((version for version in released if version), default=None)

    def changed_since(self, release: ReleaseVersion) -> bool:
        """
        :param release: A released version.
        :return: Whether the checked-out commit differs from that release.
        """
        return not self.git.attempt("diff", "--quiet", release.tag, "HEAD").succeeded

    def allowed_versions(self, latest: ReleaseVersion) -> tuple[ReleaseVersion, ...]:
        """
        :param latest: The latest release.
        :return: The versions a change since it may name: its next patch, minor or major
            one.
        """
        return (
            latest.bumped(VersionPart.PATCH),
            latest.bumped(VersionPart.MINOR),
            latest.bumped(VersionPart.MAJOR),
        )

    def next_version(self, part: VersionPart) -> ReleaseVersion:
        """
        :param part: The part to increment.
        :return: The latest release with *part* bumped, or the manifest's version with it
            bumped before the first release; bumping twice names the same version.
        """
        return (self.latest_release() or self.version).bumped(part)

    def verify(self) -> None:
        """
        :raises UnexpectedVersion: If the manifest does not name the version merging the
            checkout releases.
        """
        planned = self.plan()
        if planned is None:
            logger.info("Nothing changed since the latest release.")
        else:
            logger.info(f"Merging this releases {planned.version.tag}.")

    def bump(self, version: ReleaseVersion) -> None:
        """
        Write *version* everywhere a version is written. Every file is read and rewritten
        in memory before any is written, so a missing reference leaves them all as they
        were.

        :param version: The version to write.
        :raises VersionReferenceMissing: If a file names no version.
        """
        rewritten = {
            reference.path: reference.rewritten(self.checkout, version)
            for reference in VersionReference.every()
        }
        for path, text in rewritten.items():
            (self.checkout / path).write_text(text)

    def plan(self) -> PlannedRelease | None:
        """
        Decide the release of everything since the latest one: the version the manifest
        names, which the change itself wrote. A release never writes a version, so the
        commit a plugin syncs from already names the release it installs.

        :raises UnexpectedVersion: If something changed and the manifest does not name
            the next patch, minor or major version.
        :return: The release, or ``None`` when nothing changed since the latest one.
        """
        latest = self.latest_release()
        if latest is None:
            return PlannedRelease(self.version)
        if not self.changed_since(latest):
            return None
        allowed = self.allowed_versions(latest)
        if self.version not in allowed:
            raise UnexpectedVersion(self.version, allowed)
        return PlannedRelease(self.version)


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
        check_parser = subcommands.add_parser(
            ReleaseCommand.CHECK,
            help="Fail if the manifest does not name the version merging releases",
        )
        bump_parser = subcommands.add_parser(
            ReleaseCommand.BUMP,
            help="Write a version everywhere a version is written",
        )
        bump_parser.add_argument(
            "--part",
            type=VersionPart,
            choices=list(VersionPart),
            default=VersionPart.PATCH,
            help="The part of the latest release to increment (default: patch)",
        )
        bump_parser.add_argument(
            "--version",
            type=ReleaseVersion.parse,
            help="The version to write, instead of incrementing a part",
        )
        release_parser = subcommands.add_parser(
            ReleaseCommand.RELEASE,
            help="Name the tag releasing everything since the latest release",
        )
        for subcommand_parser in (check_parser, bump_parser, release_parser):
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
            if arguments.subcommand == ReleaseCommand.CHECK:
                release.verify()
            elif arguments.subcommand == ReleaseCommand.BUMP:
                version = arguments.version or release.next_version(arguments.part)
                release.bump(version)
                logger.info(f"Bumped to {version}; merging it releases {version.tag}.")
            elif arguments.subcommand == ReleaseCommand.RELEASE:
                planned = release.plan()
                if planned is None:
                    logger.warning("Nothing changed since the latest release.")
                else:
                    logger.info(planned.output_lines())
        except (UnexpectedVersion, VersionReferenceMissing, MalformedVersion) as error:
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
