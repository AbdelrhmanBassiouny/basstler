"""
Whether a checkout's package is the one its plugin's version installs.

An installed plugin runs the hooks and skills of the revision it was installed from, but
installs the package at ``v<version>``, the tag the release workflow puts on ``main`` when
the plugin manifest's version changes. A change to the package that leaves the version
alone therefore reaches a plugin's hooks without reaching the package they call: the hooks
call a subcommand the installed package does not have yet.

This check fails when that has happened: the tag the manifest's version names already
exists, and the package's source or metadata differs from it. The fix is to bump the
version, so merging the change releases it. A version whose tag does not exist yet is
the next release, and passes. CI runs the check on every pull request, against a
checkout with its tags fetched.

Usage:
    python3 -m basstler.release_version [--checkout <directory>]
"""

from __future__ import annotations

import argparse
import json
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
    How the check ended, as its caller reads it.
    """

    SUCCESS = 0
    """
    The package is the one the version releases.
    """

    UNRELEASED_PACKAGE_CHANGE = 1
    """
    The package changed since the version's release; the version needs a bump.
    """


class PluginManifestKey(StrEnum):
    """
    The keys of the plugin manifest this module reads.
    """

    VERSION = "version"
    """
    The plugin's release.
    """


@dataclass
class UnreleasedPackageChange(CommandFailure, RuntimeError):
    """
    Raised when the package differs from the release its unchanged version names.
    """

    @classproperty
    def exit_code(cls) -> ReleaseVersionExitCode:
        """:return: The status this kind of error ends a command with."""
        return ReleaseVersionExitCode.UNRELEASED_PACKAGE_CHANGE

    release_tag: str
    """
    The existing tag the manifest's version names.
    """

    changed_paths: tuple[str, ...]
    """
    The package's files that differ from that tag.
    """

    def __str__(self) -> str:
        changed = "\n".join(f"  {path}" for path in self.changed_paths)
        return (
            f"The package changed since {self.release_tag}, but "
            f"{CheckoutLocation.PLUGIN_MANIFEST} still names that release, so an "
            f"installed plugin would run these changes' hooks against the "
            f"{self.release_tag} package:\n{changed}\n"
            f"Bump the version in {CheckoutLocation.PLUGIN_MANIFEST}; merging the bump "
            "releases it."
        )


@dataclass(frozen=True)
class ReleaseCheck:
    """
    One checkout, and the release its plugin manifest names.
    """

    checkout: Path
    """
    The root of the checkout to check.
    """

    @property
    def git(self) -> GitCommandRunner:
        """:return: A runner for git in the checkout."""
        return GitCommandRunner(working_directory=self.checkout)

    @property
    def version(self) -> str:
        """:return: The version the checkout's plugin manifest declares."""
        manifest = json.loads(
            (self.checkout / CheckoutLocation.PLUGIN_MANIFEST).read_text()
        )
        return manifest[PluginManifestKey.VERSION]

    @property
    def release_tag(self) -> str:
        """:return: The tag the release workflow puts on this version."""
        return f"v{self.version}"

    def is_released(self) -> bool:
        """:return: Whether the version's tag exists in the checkout."""
        return self.git.attempt(
            "rev-parse", "--verify", "--quiet", f"refs/tags/{self.release_tag}"
        ).succeeded

    def paths_changed_since_release(self) -> tuple[str, ...]:
        """
        :return: The package's files that differ between the release tag and the
            checked-out commit.
        """
        output = self.git.run(
            "diff",
            "--name-only",
            self.release_tag,
            "HEAD",
            "--",
            str(CheckoutLocation.PACKAGE_SOURCE),
            str(CheckoutLocation.PACKAGE_METADATA),
        )
        return tuple(output.splitlines())

    def verify(self) -> None:
        """
        :raises UnreleasedPackageChange: If the version is released and the package
            differs from that release.
        """
        if not self.is_released():
            logger.info(f"{self.release_tag} is not tagged yet; merging releases it.")
            return
        changed_paths = self.paths_changed_since_release()
        if changed_paths:
            raise UnreleasedPackageChange(self.release_tag, changed_paths)
        logger.info(f"The package is unchanged since {self.release_tag}.")


def main() -> ReleaseVersionExitCode:
    """
    Check the checkout named on the command line.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--checkout",
        type=Path,
        default=Path.cwd(),
        help="The checkout to check (default: the current directory)",
    )
    arguments = parser.parse_args()
    try:
        ReleaseCheck(arguments.checkout).verify()
    except UnreleasedPackageChange as error:
        logger.error(str(error))
        return error.exit_code
    return ReleaseVersionExitCode.SUCCESS


if __name__ == "__main__":
    sys.exit(main())
