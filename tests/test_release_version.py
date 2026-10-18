"""
Every change since a release needs a version bump, since an install takes the package
and the reusable workflow from the tag its version names; and a bump writes the version
everywhere one is written.

Each test builds a scratch checkout tagged at a release, changes it, and checks what
:class:`~basstler.release_version.Release` makes of it.
"""

from __future__ import annotations

import pytest

from basstler.locations import CheckoutLocation
from basstler.release_version import (
    MalformedVersion,
    Release,
    ReleaseVersion,
    ReleaseVersionExitCode,
    UnreleasedChange,
    VersionPart,
    VersionReference,
    VersionReferenceMissing,
)

from .constants import (
    ReleaseSampleFile,
    ReleaseSampleText,
    ReleaseSampleVersion,
    RepositoryLocation,
)
from .plugin_manifest import PluginManifest
from .scratch_repository import ScratchRepository


def write_version(repository: ScratchRepository, version: ReleaseSampleVersion) -> None:
    """
    :param repository: The scratch checkout.
    :param version: The version its manifest and example caller are to name.
    """
    repository.write(
        CheckoutLocation.PLUGIN_MANIFEST,
        ReleaseSampleText.MANIFEST.format(version=version),
    )
    repository.write(
        CheckoutLocation.EXAMPLE_CALLER,
        ReleaseSampleText.EXAMPLE_CALLER.format(version=version),
    )


@pytest.fixture
def released_checkout(tmp_path) -> ScratchRepository:
    """
    :return: A scratch checkout with a package, a plugin and some documentation, tagged
        at :attr:`ReleaseSampleVersion.RELEASED`.
    """
    repository = ScratchRepository.create(tmp_path)
    write_version(repository, ReleaseSampleVersion.RELEASED)
    for path in ReleaseSampleFile:
        repository.write(path, "")
    repository.commit_everything("Release")
    repository.run_git("tag", f"v{ReleaseSampleVersion.RELEASED}")
    return repository


def release_of(repository: ScratchRepository) -> Release:
    """
    :param repository: The scratch checkout.
    :return: Its release.
    """
    return Release(repository.project_root)


# %% check


def test_an_unchanged_checkout_passes(released_checkout):
    release_of(released_checkout).verify()


@pytest.mark.parametrize(
    "changed_file",
    list(ReleaseSampleFile),
    ids=lambda path: path._name_,
)
def test_a_change_without_a_bump_fails_naming_the_change(
    released_checkout, changed_file
):
    """
    The reported case was a hook gaining a call into the package while the plugin kept
    installing the release from before it.

    Any other change counts the same, so no list of shipped paths can leave one out.
    """
    released_checkout.write(changed_file, ReleaseSampleText.CHANGE)
    released_checkout.commit_everything("Change a file")

    with pytest.raises(UnreleasedChange) as raised:
        release_of(released_checkout).verify()

    assert raised.value.changed_paths == (str(changed_file),)
    assert raised.value.release_tag == f"v{ReleaseSampleVersion.RELEASED}"
    assert raised.value.exit_code is ReleaseVersionExitCode.UNRELEASED_CHANGE


def test_a_change_with_a_bump_passes(released_checkout):
    released_checkout.write(ReleaseSampleFile.PACKAGE_MODULE, ReleaseSampleText.CHANGE)
    release_of(released_checkout).bump(
        ReleaseVersion.parse(ReleaseSampleVersion.NEXT_PATCH)
    )
    released_checkout.commit_everything("Change the package and bump the version")

    release_of(released_checkout).verify()


def test_an_uncommitted_change_is_not_judged(released_checkout):
    """
    The check reads the commit under review, not whatever the working tree holds.
    """
    released_checkout.write(ReleaseSampleFile.PACKAGE_MODULE, ReleaseSampleText.CHANGE)

    release_of(released_checkout).verify()


# %% bump


@pytest.mark.parametrize(
    "part, expected",
    [
        (VersionPart.PATCH, ReleaseSampleVersion.NEXT_PATCH),
        (VersionPart.MINOR, ReleaseSampleVersion.NEXT_MINOR),
        (VersionPart.MAJOR, ReleaseSampleVersion.NEXT_MAJOR),
    ],
)
def test_a_version_bumps_by_the_part_named(part, expected):
    released = ReleaseVersion.parse(ReleaseSampleVersion.RELEASED)

    assert str(released.bumped(part)) == expected


def test_a_bump_writes_the_version_everywhere_one_is_written(released_checkout):
    release_of(released_checkout).bump(
        ReleaseVersion.parse(ReleaseSampleVersion.CHOSEN)
    )

    for reference in VersionReference.every():
        versions = reference.versions_in(released_checkout.project_root)
        assert set(versions) == {ReleaseSampleVersion.CHOSEN}, reference.path
    assert (
        released_checkout.project_root / CheckoutLocation.PLUGIN_MANIFEST
    ).read_text() == (
        ReleaseSampleText.MANIFEST.format(version=ReleaseSampleVersion.CHOSEN)
    )


def test_a_bump_with_a_reference_missing_writes_nothing(released_checkout):
    released_checkout.write(CheckoutLocation.EXAMPLE_CALLER, "")

    with pytest.raises(VersionReferenceMissing) as raised:
        release_of(released_checkout).bump(
            ReleaseVersion.parse(ReleaseSampleVersion.NEXT_PATCH)
        )

    assert raised.value.path == CheckoutLocation.EXAMPLE_CALLER
    assert release_of(released_checkout).version == ReleaseVersion.parse(
        ReleaseSampleVersion.RELEASED
    )


def test_a_version_that_is_not_three_numbers_is_refused():
    with pytest.raises(MalformedVersion):
        ReleaseVersion.parse(f"v{ReleaseSampleVersion.RELEASED}")


# %% this repository


def test_every_reference_in_this_repository_names_the_plugins_version():
    """
    A reference the bump does not know of would be left behind at the old release.
    """
    version = PluginManifest.of_this_plugin().version

    for reference in VersionReference.every():
        versions = reference.versions_in(RepositoryLocation.ROOT)
        assert versions and set(versions) == {version}, reference.path


@pytest.mark.parametrize(
    "location", list(CheckoutLocation), ids=lambda path: path._name_
)
def test_every_checkout_location_exists_in_this_repository(location):
    assert (RepositoryLocation.ROOT / location).exists()
