"""
Every change merged to ``main`` is a release, at the next patch, minor or major version
the pull request making it wrote; the release workflow only tags the merged commit.

Each test builds a scratch checkout tagged at a release, changes it, and checks what
:class:`~basstler.release_version.Release` makes of it. The workflow's own tag step is
run against a scratch remote, since pushing nothing but the tag is what lets a synced
plugin take the version from the merge itself.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from basstler.environment import GitHubActionsVariable
from basstler.locations import CheckoutLocation
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

from .constants import (
    EnvironmentVariable,
    ReleaseSampleFile,
    ReleaseSampleTag,
    ReleaseSampleText,
    ReleaseSampleVersion,
    RepositoryLocation,
)
from .plugin_manifest import PluginManifest
from .scratch_repository import ScratchRepository, initialize_bare_repository


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
        ReleaseSampleVersion.NEXT_PATCH,
        ReleaseSampleVersion.NEXT_MINOR,
        ReleaseSampleVersion.NEXT_MAJOR,
    ],
)
def test_a_pull_request_may_name_the_next_patch_minor_or_major(
    released_checkout, named
):
    change_and_commit(released_checkout, named)

    release_of(released_checkout).verify()


def test_a_checkout_unchanged_since_the_latest_release_passes(released_checkout):
    release_of(released_checkout).verify()


@pytest.mark.parametrize(
    "named",
    [
        ReleaseSampleVersion.RELEASED,
        ReleaseSampleVersion.SKIPPING,
        ReleaseSampleVersion.OLDER,
    ],
)
def test_a_pull_request_may_not_name_any_other_version(released_checkout, named):
    """
    Leaving the latest release's version would make the workflow write the next one
    after the merge, in a commit a synced plugin was seen to miss.
    """
    change_and_commit(released_checkout, named)

    with pytest.raises(UnexpectedVersion) as raised:
        release_of(released_checkout).verify()

    assert raised.value.version == version(named)
    assert raised.value.allowed == (
        version(ReleaseSampleVersion.NEXT_PATCH),
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
def test_any_change_without_a_new_version_is_refused_and_writes_nothing(
    released_checkout, changed_file
):
    """
    The reported case was a hook gaining a call into the package while the plugin kept
    installing the release from before it.

    Any other change counts the same, so no list of shipped paths can leave one out.
    """
    released_checkout.write(changed_file, ReleaseSampleText.CHANGE)
    released_checkout.commit_everything("Change a file")

    with pytest.raises(UnexpectedVersion):
        release_of(released_checkout).plan()

    assert released_checkout.run_git("status", "--porcelain").stdout == ""


@pytest.mark.parametrize(
    "named",
    [
        ReleaseSampleVersion.NEXT_PATCH,
        ReleaseSampleVersion.NEXT_MINOR,
        ReleaseSampleVersion.NEXT_MAJOR,
    ],
)
def test_a_version_a_pull_request_named_is_released_as_it_stands(
    released_checkout, named
):
    change_and_commit(released_checkout, named)

    planned = release_of(released_checkout).plan()

    assert planned == PlannedRelease(version(named))
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

    assert planned == PlannedRelease(version(ReleaseSampleVersion.RELEASED))


def test_a_planned_release_prints_its_tag():
    planned = PlannedRelease(version(ReleaseSampleVersion.NEXT_PATCH))

    assert planned.output_lines() == f"tag=v{ReleaseSampleVersion.NEXT_PATCH}"


# %% the workflow's release step


def release_step_script() -> str:
    """
    :return: The shell the release workflow runs to tag and push a release.
    """
    workflow = yaml.safe_load(
        (RepositoryLocation.WORKFLOWS / "release.yml").read_text()
    )
    (job,) = workflow["jobs"].values()
    return next(
        step["run"] for step in job["steps"] if "git push" in step.get("run", "")
    )


def run_release_step(
    checkout: Path, summary: Path, output: Path
) -> subprocess.CompletedProcess[str]:
    """
    Run the release step in *checkout*, as the workflow does, with this interpreter's
    package on the path.

    :param checkout: A clone whose ``origin`` is the scratch remote.
    :param summary: The file standing in for ``$GITHUB_STEP_SUMMARY``.
    :param output: The file standing in for ``$GITHUB_OUTPUT``.
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
        GitHubActionsVariable.OUTPUT: str(output),
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
    A released checkout pushed to a scratch remote, and a clone of that remote standing
    in for the runner's checkout.
    """

    repository: ScratchRepository
    """
    The released checkout, with the scratch remote as its ``origin``.
    """

    runner: Path
    """
    The runner's clone of the scratch remote.
    """

    def merge(self, new_version: ReleaseSampleVersion | None = None) -> None:
        """
        Push a change to the remote's ``main``, and check it out in the runner's clone
        as the workflow's checkout does for the push that started it.

        :param new_version: The version the merged pull request names, if it names one.
        """
        change_and_commit(self.repository, new_version)
        self.repository.run_git("push", "--quiet", "origin", "HEAD:main")
        for command in (
            ["git", "fetch", "--quiet", "origin"],
            ["git", "checkout", "--quiet", "--detach", "origin/main"],
        ):
            subprocess.run(command, cwd=self.runner, check=True)

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


def test_the_release_step_tags_the_merged_commit_and_pushes_nothing_else(
    published_checkout, tmp_path
):
    """
    The tag lands on the commit ``main`` already names, carrying the version the pull
    request wrote, so a plugin synced from that merge installs its own release.

    The tag is the step's output, for the GitHub release.
    """
    published_checkout.merge(ReleaseSampleVersion.NEXT_PATCH)
    merged_commit = published_checkout.remote_commit("origin/main")
    output = tmp_path / "output"

    result = run_release_step(
        published_checkout.runner, tmp_path / "summary.md", output
    )

    assert result.returncode == 0, result.stderr
    tag = version(ReleaseSampleVersion.NEXT_PATCH).tag
    assert published_checkout.remote_commit("origin/main") == merged_commit
    assert published_checkout.remote_commit(tag) == merged_commit
    assert output.read_text() == f"tag={tag}\n"


def test_the_release_step_fails_on_a_change_naming_no_new_version(
    published_checkout, tmp_path
):
    """
    No version is written after the merge, so the release is refused rather than tagged
    at a version the synced plugin does not name.
    """
    published_checkout.merge()
    output = tmp_path / "output"

    result = run_release_step(
        published_checkout.runner, tmp_path / "summary.md", output
    )

    assert result.returncode != 0
    remote_tags = subprocess.run(
        ["git", "ls-remote", "--tags", "origin"],
        cwd=published_checkout.runner,
        capture_output=True,
        text=True,
    ).stdout
    assert version(ReleaseSampleVersion.NEXT_PATCH).tag not in remote_tags
    assert not output.exists()


def test_the_release_step_does_nothing_when_nothing_changed(
    published_checkout, tmp_path
):
    """
    No tag is output, so no GitHub release is published.
    """
    summary = tmp_path / "summary.md"
    output = tmp_path / "output"

    result = run_release_step(published_checkout.runner, summary, output)

    assert result.returncode == 0, result.stderr
    assert "Nothing changed" in summary.read_text()
    assert not output.exists()


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


def test_the_next_version_bumps_the_latest_release_so_bumping_twice_names_it_once(
    released_checkout,
):
    release = release_of(released_checkout)
    release.bump(release.next_version(VersionPart.PATCH))

    assert release.next_version(VersionPart.PATCH) == version(
        ReleaseSampleVersion.NEXT_PATCH
    )


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
