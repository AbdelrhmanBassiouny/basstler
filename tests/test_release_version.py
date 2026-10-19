"""
Every change merged to ``main`` is a release: the release workflow makes patch releases
on merge, and a pull request may only name a minor or major one.

Each test builds a scratch checkout tagged at a release, changes it, and checks what
:class:`~basstler.release_version.Release` makes of it. The workflow's own push step is
run against a scratch remote, since its atomic push is what keeps ``main`` from ever
carrying a version without its tag.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import pytest
import yaml

from basstler.environment import GitHubActionsVariable
from basstler.locations import CheckoutLocation, PathEnumeration
from basstler.release_version import (
    MalformedVersion,
    PlannedRelease,
    Release,
    ReleaseVersion,
    ReleaseVersionExitCode,
    UnexpectedVersion,
    VersionPart,
    VersionReference,
    VersionReferenceMissing,
)

from .constants.environment import EnvironmentVariable
from .constants.paths import RepositoryLocation
from .plugin_manifest import PluginManifest
from .scratch_repository import ScratchRepository, initialize_bare_repository


class ReleaseSampleVersion(StrEnum):
    """
    The versions a scratch checkout's plugin manifest names in the release-version tests.
    """

    RELEASED = "1.0.0"
    """
    The version the scratch checkout is tagged at.
    """

    NEXT_PATCH = "1.0.1"
    """
    :attr:`RELEASED` with its patch part bumped: what a release on merge makes.
    """

    NEXT_MINOR = "1.1.0"
    """
    :attr:`RELEASED` with its minor part bumped, which a pull request may name.
    """

    NEXT_MAJOR = "2.0.0"
    """
    :attr:`RELEASED` with its major part bumped, which a pull request may name.
    """

    SKIPPING = "1.2.0"
    """
    A minor release past the next one, which a pull request may not name.
    """

    OLDER = "0.9.0"
    """
    A version behind :attr:`RELEASED`.
    """

    UNMERGED = "3.0.0"
    """
    A version tagged on a branch the checked-out commit does not contain.
    """


class ReleaseSampleTag(StrEnum):
    """
    Tags the release-version tests put on a scratch checkout that release nothing.
    """

    NOT_A_RELEASE = "nightly"
    """
    A tag that names no version.
    """

    MALFORMED = "v1.x"
    """
    A tag shaped like a release whose version is not one.
    """


class ReleaseSampleFile(PathEnumeration):
    """
    The files of a scratch checkout the release-version tests change, relative to its
    root.
    """

    PACKAGE_MODULE = Path("src") / "sample" / "__init__.py"
    """
    A module of the scratch checkout's package.
    """

    SKILL = Path("plugin") / "skills" / "sample" / "SKILL.md"
    """
    A skill of the scratch checkout's plugin.
    """

    DOCUMENTATION = Path("docs") / "guide.md"
    """
    Documentation, which no install runs but which still makes a new release.
    """


class ReleaseSampleText(StrEnum):
    """
    File contents the release-version tests write.
    """

    MANIFEST = '{{\n  "name": "basstler",\n  "version": "{version}"\n}}\n'
    """
    A plugin manifest, formatted with its ``version``.
    """

    EXAMPLE_CALLER = (
        "    uses: owner/basstler/.github/workflows/upstream-reviews.yml@v{version}\n"
        "    with:\n"
        "      basstler_ref: v{version}\n"
    )
    """
    The example caller's two references to the release, formatted with its ``version``.
    """

    CHANGE = "changed = True\n"
    """
    What a test writes to change a file.
    """


def version(sample: ReleaseSampleVersion) -> ReleaseVersion:
    """
    :param sample: A sample version.
    :return: It, parsed.
    """
    return ReleaseVersion.parse(sample)


def write_version(repository: ScratchRepository, sample: ReleaseSampleVersion) -> None:
    """
    :param repository: The scratch checkout.
    :param sample: The version its manifest and example caller are to name.
    """
    repository.write(
        CheckoutLocation.PLUGIN_MANIFEST,
        ReleaseSampleText.MANIFEST.format(version=sample),
    )
    repository.write(
        CheckoutLocation.EXAMPLE_CALLER,
        ReleaseSampleText.EXAMPLE_CALLER.format(version=sample),
    )


def change_and_commit(
    repository: ScratchRepository, new_version: ReleaseSampleVersion | None = None
) -> None:
    """
    Commit a change to a package module, naming *new_version* in the same commit if
    given.

    :param repository: The scratch checkout.
    :param new_version: The version the pull request names, if it names one.
    """
    repository.write(ReleaseSampleFile.PACKAGE_MODULE, ReleaseSampleText.CHANGE)
    if new_version is not None:
        write_version(repository, new_version)
    repository.commit_everything("Change the package")


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
    repository.run_git("tag", version(ReleaseSampleVersion.RELEASED).tag)
    return repository


def release_of(repository: ScratchRepository) -> Release:
    """
    :param repository: The scratch checkout.
    :return: Its release.
    """
    return Release(repository.project_root)


# %% the latest release


def test_the_latest_release_is_the_highest_tag_the_commit_contains(released_checkout):
    """
    Tags that name no version, and releases on a branch never merged, are not releases
    of this commit.
    """
    released_checkout.run_git("tag", ReleaseSampleTag.NOT_A_RELEASE)
    released_checkout.run_git("tag", ReleaseSampleTag.MALFORMED)
    released_checkout.run_git("checkout", "--quiet", "-b", "side")
    released_checkout.write(ReleaseSampleFile.DOCUMENTATION, ReleaseSampleText.CHANGE)
    released_checkout.commit_everything("Elsewhere")
    released_checkout.run_git("tag", version(ReleaseSampleVersion.UNMERGED).tag)
    released_checkout.run_git("checkout", "--quiet", "-")

    assert release_of(released_checkout).latest_release() == version(
        ReleaseSampleVersion.RELEASED
    )


def test_there_is_no_latest_release_before_the_first(tmp_path):
    repository = ScratchRepository.create(tmp_path)
    write_version(repository, ReleaseSampleVersion.RELEASED)
    repository.commit_everything("First")

    assert release_of(repository).latest_release() is None


# %% check: what a pull request may name


@pytest.mark.parametrize(
    "named",
    [
        None,
        ReleaseSampleVersion.NEXT_MINOR,
        ReleaseSampleVersion.NEXT_MAJOR,
    ],
)
def test_a_pull_request_may_leave_the_version_or_name_the_next_minor_or_major(
    released_checkout, named
):
    change_and_commit(released_checkout, named)

    release_of(released_checkout).verify()


@pytest.mark.parametrize(
    "named",
    [
        ReleaseSampleVersion.NEXT_PATCH,
        ReleaseSampleVersion.SKIPPING,
        ReleaseSampleVersion.OLDER,
    ],
)
def test_a_pull_request_may_not_name_any_other_version(released_checkout, named):
    """
    A patch release is made on merge; a pull request naming one would race it.
    """
    change_and_commit(released_checkout, named)

    with pytest.raises(UnexpectedVersion) as raised:
        release_of(released_checkout).verify()

    assert raised.value.version == version(named)
    assert raised.value.allowed == (
        version(ReleaseSampleVersion.RELEASED),
        version(ReleaseSampleVersion.NEXT_MINOR),
        version(ReleaseSampleVersion.NEXT_MAJOR),
    )
    assert raised.value.exit_code is ReleaseVersionExitCode.UNEXPECTED_VERSION


# %% release: what a merge releases


def test_nothing_changed_since_the_latest_release_releases_nothing(released_checkout):
    assert release_of(released_checkout).plan() is None


@pytest.mark.parametrize(
    "changed_file", list(ReleaseSampleFile), ids=lambda p: p._name_
)
def test_any_change_is_released_as_the_next_patch_written_everywhere(
    released_checkout, changed_file
):
    """
    The reported case was a hook gaining a call into the package while the plugin kept
    installing the release from before it.

    Any other change counts the same, so no list of shipped paths can leave one out.
    """
    released_checkout.write(changed_file, ReleaseSampleText.CHANGE)
    released_checkout.commit_everything("Change a file")

    planned = release_of(released_checkout).plan()

    assert planned == PlannedRelease(version(ReleaseSampleVersion.NEXT_PATCH), True)
    for reference in VersionReference.every():
        versions = reference.versions_in(released_checkout.project_root)
        assert set(versions) == {ReleaseSampleVersion.NEXT_PATCH}, reference.path


@pytest.mark.parametrize(
    "named", [ReleaseSampleVersion.NEXT_MINOR, ReleaseSampleVersion.NEXT_MAJOR]
)
def test_a_version_a_pull_request_named_is_released_as_it_stands(
    released_checkout, named
):
    change_and_commit(released_checkout, named)

    planned = release_of(released_checkout).plan()

    assert planned == PlannedRelease(version(named), False)
    assert released_checkout.run_git("status", "--porcelain").stdout == ""


def test_a_version_behind_the_latest_release_is_refused(released_checkout):
    change_and_commit(released_checkout, ReleaseSampleVersion.OLDER)

    with pytest.raises(UnexpectedVersion):
        release_of(released_checkout).plan()


def test_the_first_release_is_the_manifests_version(tmp_path):
    repository = ScratchRepository.create(tmp_path)
    write_version(repository, ReleaseSampleVersion.RELEASED)
    repository.commit_everything("First")

    planned = release_of(repository).plan()

    assert planned == PlannedRelease(version(ReleaseSampleVersion.RELEASED), False)


def test_a_planned_release_prints_its_outputs():
    planned = PlannedRelease(version(ReleaseSampleVersion.NEXT_PATCH), True)

    assert planned.output_lines() == (
        f"tag=v{ReleaseSampleVersion.NEXT_PATCH}\nbumped=true"
    )


# %% the workflow's release step


def release_step_script() -> str:
    """
    :return: The shell the release workflow runs to commit, tag and push a release.
    """
    workflow = yaml.safe_load(
        (RepositoryLocation.WORKFLOWS / "release.yml").read_text()
    )
    (job,) = workflow["jobs"].values()
    return next(
        step["run"] for step in job["steps"] if "git push" in step.get("run", "")
    )


def run_release_step(checkout: Path, summary: Path) -> subprocess.CompletedProcess[str]:
    """
    Run the release step in *checkout*, as the workflow does, with this interpreter's
    package on the path.

    :param checkout: A clone whose ``origin`` is the scratch remote.
    :param summary: The file standing in for ``$GITHUB_STEP_SUMMARY``.
    :return: The finished step.
    """
    environment = {
        **os.environ,
        EnvironmentVariable.EXECUTABLE_SEARCH_PATH: os.pathsep.join(
            [
                str(Path(sys.executable).parent),
                os.environ[EnvironmentVariable.EXECUTABLE_SEARCH_PATH],
            ]
        ),
        GitHubActionsVariable.STEP_SUMMARY: str(summary),
    }
    return subprocess.run(
        ["bash", "-e", "-c", release_step_script()],
        cwd=checkout,
        env=environment,
        capture_output=True,
        text=True,
    )


@dataclass(frozen=True)
class PublishedCheckout:
    """
    A released checkout pushed to a scratch remote, and a clone of that remote standing in
    for the runner's checkout.
    """

    repository: ScratchRepository
    """
    The released checkout, with the scratch remote as its ``origin``.
    """
    runner: Path
    """
    The runner's clone of the scratch remote.
    """

    def remote_commit(self, reference: str) -> str:
        """
        :param reference: A reference on the scratch remote, as the runner's clone names it.
        :return: The commit it names, after fetching the remote's branches and tags.
        """
        subprocess.run(
            ["git", "fetch", "--quiet", "--tags", "origin"], cwd=self.runner, check=True
        )
        return subprocess.run(
            ["git", "rev-parse", f"{reference}^{{commit}}"],
            cwd=self.runner,
            capture_output=True,
            text=True,
        ).stdout.strip()


@pytest.fixture
def published_checkout(released_checkout, tmp_path) -> PublishedCheckout:
    """
    :return: The released checkout, published to a scratch remote with its tag.
    """
    remote = initialize_bare_repository(tmp_path / "origin.git")
    released_checkout.run_git("push", "--quiet", "--tags", str(remote), "HEAD:main")
    runner = tmp_path / "runner"
    subprocess.run(
        ["git", "clone", "--quiet", "--branch", "main", str(remote), str(runner)],
        check=True,
    )
    released_checkout.add_remote("origin", str(remote))
    return PublishedCheckout(released_checkout, runner)


def test_the_release_step_pushes_the_bump_and_its_tag_together(
    published_checkout, tmp_path
):
    """
    ``main`` and the new tag land on the same commit, so no plugin can sync a version
    whose tag does not exist yet.
    """
    change_and_commit(published_checkout.repository)
    published_checkout.repository.run_git("push", "--quiet", "origin", "HEAD:main")

    result = run_release_step(published_checkout.runner, tmp_path / "summary.md")

    assert result.returncode == 0, result.stderr
    main_commit = published_checkout.remote_commit("origin/main")
    tag = version(ReleaseSampleVersion.NEXT_PATCH).tag
    assert main_commit == published_checkout.remote_commit(tag)
    released = subprocess.run(
        ["git", "show", f"{main_commit}:{CheckoutLocation.PLUGIN_MANIFEST}"],
        cwd=published_checkout.runner,
        capture_output=True,
        text=True,
    ).stdout
    assert released == ReleaseSampleText.MANIFEST.format(
        version=ReleaseSampleVersion.NEXT_PATCH
    )


def test_the_release_step_does_nothing_when_nothing_changed(
    published_checkout, tmp_path
):
    summary = tmp_path / "summary.md"

    result = run_release_step(published_checkout.runner, summary)

    assert result.returncode == 0, result.stderr
    assert "Nothing changed" in summary.read_text()


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
    assert version(ReleaseSampleVersion.RELEASED).bumped(part) == version(expected)


def test_a_bump_writes_the_version_everywhere_one_is_written(released_checkout):
    release_of(released_checkout).bump(version(ReleaseSampleVersion.NEXT_MINOR))

    for reference in VersionReference.every():
        versions = reference.versions_in(released_checkout.project_root)
        assert set(versions) == {ReleaseSampleVersion.NEXT_MINOR}, reference.path
    manifest = released_checkout.project_root / CheckoutLocation.PLUGIN_MANIFEST
    assert manifest.read_text() == ReleaseSampleText.MANIFEST.format(
        version=ReleaseSampleVersion.NEXT_MINOR
    )


def test_a_bump_with_a_reference_missing_writes_nothing(released_checkout):
    released_checkout.write(CheckoutLocation.EXAMPLE_CALLER, "")

    with pytest.raises(VersionReferenceMissing) as raised:
        release_of(released_checkout).bump(version(ReleaseSampleVersion.NEXT_MINOR))

    assert raised.value.path == CheckoutLocation.EXAMPLE_CALLER
    assert release_of(released_checkout).version == version(
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
    plugin_version = PluginManifest.of_this_plugin().version

    for reference in VersionReference.every():
        versions = reference.versions_in(RepositoryLocation.ROOT)
        assert versions and set(versions) == {plugin_version}, reference.path


@pytest.mark.parametrize("location", list(CheckoutLocation), ids=lambda p: p._name_)
def test_every_checkout_location_exists_in_this_repository(location):
    assert (RepositoryLocation.ROOT / location).exists()
