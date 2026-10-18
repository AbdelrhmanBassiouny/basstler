"""
A pull request that changes the package has to bump the version, since an installed
plugin installs the package at the tag its version names.

Each test builds a scratch checkout tagged at a release, changes it, and checks what
:class:`~basstler.release_version.ReleaseCheck` makes of it.
"""

from __future__ import annotations

import json

import pytest

from basstler.locations import CheckoutLocation
from basstler.release_version import (
    PluginManifestKey,
    ReleaseCheck,
    ReleaseVersionExitCode,
    UnreleasedPackageChange,
)

from .constants import ReleaseSampleFile, ReleaseSampleVersion, RepositoryLocation
from .scratch_repository import ScratchRepository


def write_version(repository: ScratchRepository, version: ReleaseSampleVersion) -> None:
    """
    :param repository: The scratch checkout.
    :param version: The version its plugin manifest is to declare.
    """
    repository.write(
        CheckoutLocation.PLUGIN_MANIFEST,
        json.dumps({PluginManifestKey.VERSION: version}),
    )


@pytest.fixture
def released_checkout(tmp_path) -> ScratchRepository:
    """
    :return: A scratch checkout with a package, its metadata and a plugin, tagged at
        :attr:`ReleaseSampleVersion.RELEASED`.
    """
    repository = ScratchRepository.create(tmp_path)
    write_version(repository, ReleaseSampleVersion.RELEASED)
    repository.write(ReleaseSampleFile.PACKAGE_MODULE, "")
    repository.write(CheckoutLocation.PACKAGE_METADATA, "")
    repository.write(ReleaseSampleFile.SKILL, "")
    repository.commit_everything("Release")
    repository.run_git("tag", f"v{ReleaseSampleVersion.RELEASED}")
    return repository


def check(repository: ScratchRepository) -> ReleaseCheck:
    """
    :param repository: The scratch checkout.
    :return: The check of its committed state.
    """
    return ReleaseCheck(repository.project_root)


def test_an_unchanged_package_passes(released_checkout):
    check(released_checkout).verify()


@pytest.mark.parametrize(
    "changed_file",
    [ReleaseSampleFile.PACKAGE_MODULE, CheckoutLocation.PACKAGE_METADATA],
    ids=lambda path: path._name_,
)
def test_a_package_change_without_a_bump_fails_naming_the_change(
    released_checkout, changed_file
):
    """
    The reported case: the hooks gained a call into the package, and the plugin kept
    installing the release from before it.
    """
    released_checkout.write(changed_file, "changed = True\n")
    released_checkout.commit_everything("Change the package")

    with pytest.raises(UnreleasedPackageChange) as raised:
        check(released_checkout).verify()

    assert raised.value.changed_paths == (str(changed_file),)
    assert raised.value.release_tag == f"v{ReleaseSampleVersion.RELEASED}"
    assert raised.value.exit_code is ReleaseVersionExitCode.UNRELEASED_PACKAGE_CHANGE


def test_a_package_change_with_a_bump_passes(released_checkout):
    released_checkout.write(ReleaseSampleFile.PACKAGE_MODULE, "changed = True\n")
    write_version(released_checkout, ReleaseSampleVersion.NEXT)
    released_checkout.commit_everything("Change the package and bump the version")

    check(released_checkout).verify()


def test_a_plugin_only_change_needs_no_bump(released_checkout):
    """
    The installed package is unchanged, so the plugin's hooks still find what they call.
    """
    released_checkout.write(ReleaseSampleFile.SKILL, "changed\n")
    released_checkout.commit_everything("Change a skill")

    check(released_checkout).verify()


def test_an_uncommitted_package_change_is_not_judged(released_checkout):
    """
    The check reads the commit under review, not whatever the working tree holds.
    """
    released_checkout.write(ReleaseSampleFile.PACKAGE_MODULE, "changed = True\n")

    check(released_checkout).verify()


def test_the_checkout_locations_are_this_repositorys_own():
    """
    The release workflow and the build read the manifest at the path the check reads.
    """
    assert (
        RepositoryLocation.ROOT / CheckoutLocation.PLUGIN_MANIFEST
        == RepositoryLocation.PLUGIN_MANIFEST
    )
    assert (RepositoryLocation.ROOT / CheckoutLocation.PACKAGE_SOURCE).is_dir()
    assert (RepositoryLocation.ROOT / CheckoutLocation.PACKAGE_METADATA).is_file()
