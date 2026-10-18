"""
Releases: whether a checkout's version names what it ships, and bumping it.

An installed plugin installs the package at ``v<version>``, the tag the release workflow
puts on ``main`` when the plugin manifest's version changes, and a project calls the
reusable workflow at a tag too. So a version has to name one state of the repository: once
its tag exists, any change is a new release, and needs a new version. Left unbumped, a
change reaches some installs and not others: a plugin's hooks call a subcommand the
package installed at the old tag does not have yet.

Every change counts, not only those to a list of shipped paths: such a list goes stale
the day something new ships from outside it, which is how the bug this guards against
would come back. A change that alters no behaviour costs one more patch release.

``check`` fails when the tag the manifest's version names already exists and the
checked-out commit differs from it. A version whose tag does not exist yet is the next
release, and passes. CI runs it on every pull request, against a checkout with its tags
fetched.

``bump`` writes the next version everywhere a version is written: the plugin manifest,
which the build reads it from, and every reference to the release tag.

Usage:
    python3 -m basstler.release_version check [--checkout <directory>]
    python3 -m basstler.release_version bump [--part major|minor|patch]
        [--version <version>] [--checkout <directory>]
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

    UNRELEASED_CHANGE = 1
    """
    Something changed since the version's release; the version needs a bump.
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
    Fail if anything changed since the release the version names.
    """

    BUMP = "bump"
    """
    Write the next version everywhere a version is written.
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
    A fix.
    """


@dataclass
class UnreleasedChange(CommandFailure, RuntimeError):
    """
    Raised when anything changed since the release the unchanged version names.
    """

    release_tag: str
    """
    The existing tag the manifest's version names.
    """

    changed_paths: tuple[str, ...]
    """
    The files that differ from that tag.
    """

    @classproperty
    def exit_code(cls) -> ReleaseVersionExitCode:
        """:return: The status this kind of error ends a command with."""
        return ReleaseVersionExitCode.UNRELEASED_CHANGE

    def __str__(self) -> str:
        changed = "\n".join(f"  {path}" for path in self.changed_paths)
        return (
            f"These files changed since {self.release_tag}, but "
            f"{CheckoutLocation.PLUGIN_MANIFEST} still names that release:\n{changed}\n"
            "Bump the version with `python -m basstler.release_version bump`; merging "
            "the bump releases it."
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


@dataclass(frozen=True)
class ReleaseVersion:
    """
    A ``<major>.<minor>.<patch>`` version.
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
    Incremented by a fix.
    """

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
        """:return: The tag the release workflow puts on this version."""
        return f"v{self}"

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
class Release:
    """
    One checkout, and the release its plugin manifest names.
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

    def is_released(self) -> bool:
        """:return: Whether the version's tag exists in the checkout."""
        return self.git.attempt(
            "rev-parse", "--verify", "--quiet", f"refs/tags/{self.version.tag}"
        ).succeeded

    def paths_changed_since_release(self) -> tuple[str, ...]:
        """
        :return: The files that differ between the release tag and the checked-out
            commit.
        """
        output = self.git.run("diff", "--name-only", self.version.tag, "HEAD")
        return tuple(output.splitlines())

    def verify(self) -> None:
        """
        :raises UnreleasedChange: If the version is released and anything changed since
            that release.
        """
        tag = self.version.tag
        if not self.is_released():
            logger.info(f"{tag} is not tagged yet; merging releases it.")
            return
        changed_paths = self.paths_changed_since_release()
        if changed_paths:
            raise UnreleasedChange(tag, changed_paths)
        logger.info(f"Nothing changed since {tag}.")

    def bump(self, version: ReleaseVersion) -> None:
        """
        Write *version* everywhere a version is written. Every file is read and rewritten
        in memory before any is written, so a missing reference leaves them all as they
        were.

        :param version: The version to release next.
        :raises VersionReferenceMissing: If a file names no version.
        """
        rewritten = {
            reference.path: reference.rewritten(self.checkout, version)
            for reference in VersionReference.every()
        }
        for path, text in rewritten.items():
            (self.checkout / path).write_text(text)
        logger.info(f"Bumped to {version}; merging it to main tags {version.tag}.")


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
            help="Fail if anything changed since the version's release",
        )
        bump_parser = subcommands.add_parser(
            ReleaseCommand.BUMP,
            help="Write the next version everywhere a version is written",
        )
        bump_parser.add_argument(
            "--part",
            type=VersionPart,
            choices=list(VersionPart),
            default=VersionPart.PATCH,
            help="The part to increment (default: patch)",
        )
        bump_parser.add_argument(
            "--version",
            type=ReleaseVersion.parse,
            help="The version to write, instead of incrementing a part",
        )
        for subcommand_parser in (check_parser, bump_parser):
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
                release.bump(
                    arguments.version or release.version.bumped(arguments.part)
                )
        except (UnreleasedChange, VersionReferenceMissing, MalformedVersion) as error:
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
