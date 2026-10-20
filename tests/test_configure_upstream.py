"""
Tests for naming a project's upstream in the user's own personal-notes ``stack.toml``,
and for check-setup.sh's row reporting whether one is named.

``/upstream-reviews`` and ``/stacked-pr-maintenance`` are the only callers needing an
upstream, so the row only fails a check made on their behalf; every other check reports
it as context. Run against a scratch project with a local bare repository standing in
for the personal-notes remote.
"""

from __future__ import annotations

import subprocess
import tomllib
from enum import StrEnum
from pathlib import Path

import pytest

import basstler.setup_steps
from basstler.locations import PluginLocation, ProjectLocation
from basstler.setup_steps import SetupCommand, SetupCommandOption
from basstler.stack_configuration import StackSetting

from .scratch_repository import ScratchRepository
from .script_runner import PythonModuleRunner

SETUP_STEPS_MODULE = basstler.setup_steps.__name__

BASH_ENTRY_POINTS = (
    PluginLocation.PERSONAL_NOTES_CONFIGURATION_SCRIPT.value.name,
    PluginLocation.PERSONAL_NOTES_WRITER_SCRIPT.value.name,
    PluginLocation.SETUP_CHECK_SCRIPT.value.name,
)
"""
The shell scripts the step drives and the check runs as.
"""


class UpstreamSample(StrEnum):
    """
    The repositories and settings these tests write.
    """

    UPSTREAM = "an-upstream-owner/a-project"
    """
    The upstream a user names.
    """

    PREVIOUS_UPSTREAM = "an-old-upstream/a-project"
    """
    An upstream named before, which a new one replaces.
    """

    MALFORMED = "no-owner-part"
    """
    A value that names no repository.
    """

    OTHER_SETTING = 'upstream_remote = "mine"\n'
    """
    A personal setting the step has no business touching.
    """


UPSTREAM_CHECK = "stack_upstream"
"""
The check-setup.sh row this step answers.
"""

REQUIRE_UPSTREAM = "--require-upstream"
"""
What a caller needing an upstream passes check-setup.sh.
"""


@pytest.fixture
def upstream_repository(scratch_repository: ScratchRepository) -> ScratchRepository:
    """
    A scratch repository with the scripts this step drives and a published notes branch
    naming no upstream.

    :param scratch_repository: The initialized scratch repository and notes remote.
    :return: The same repository.
    """
    scratch_repository.install_hook_scripts(*BASH_ENTRY_POINTS)
    scratch_repository.install_package()
    scratch_repository.write("README.md", "scratch repo\n")
    scratch_repository.commit_everything("initial commit")
    scratch_repository.publish_notes_branch(
        {ProjectLocation.PERSONAL_NOTES_DOCUMENT: "notes\n"}
    )
    scratch_repository.resolve_notes_remote_to()
    return scratch_repository


def configure_upstream(
    repository: ScratchRepository, upstream: str
) -> subprocess.CompletedProcess[str]:
    """
    Run the step naming *upstream*.

    :param repository: A fixture-built scratch repository.
    :param upstream: The ``owner/name`` to name.
    :return: The finished subprocess.
    """
    return PythonModuleRunner(
        project_root=repository.project_root, module_name=SETUP_STEPS_MODULE
    ).run(
        SetupCommand.CONFIGURE_UPSTREAM,
        SetupCommandOption.REPOSITORY,
        upstream,
    )


def published_stack_settings(
    repository: ScratchRepository, tmp_path: Path
) -> dict[str, str]:
    """
    Read the personal ``stack.toml`` as it is on the notes branch.

    :param repository: A fixture-built scratch repository.
    :param tmp_path: Somewhere to check the notes branch out into.
    :return: The parsed settings.
    """
    checkout = repository.clone_notes_branch(tmp_path / "published")
    return tomllib.loads(
        (checkout / ProjectLocation.PERSONAL_STACK_CONFIGURATION).read_text()
    )


def upstream_row(repository: ScratchRepository, *arguments: str) -> tuple[str, str]:
    """
    Run check-setup.sh and pick out the upstream row.

    :param repository: A fixture-built scratch repository.
    :param arguments: Arguments to pass the check.
    :return: The row's status and detail.
    """
    finished = repository.run_hook_script(
        PluginLocation.SETUP_CHECK_SCRIPT.value.name, *arguments
    )
    for line in finished.stdout.splitlines():
        check, status, detail = line.split("\t")
        if check == UPSTREAM_CHECK:
            return status, detail
    raise AssertionError(f"no {UPSTREAM_CHECK} row in:\n{finished.stdout}")


# %% the step


def test_the_upstream_is_saved_to_the_personal_stack_file(
    upstream_repository: ScratchRepository, tmp_path: Path
):
    finished = configure_upstream(upstream_repository, UpstreamSample.UPSTREAM)

    assert finished.returncode == 0, finished.stderr
    assert published_stack_settings(upstream_repository, tmp_path) == {
        StackSetting.UPSTREAM_REPOSITORY: UpstreamSample.UPSTREAM
    }


def test_naming_an_upstream_again_replaces_it_and_keeps_every_other_setting(
    upstream_repository: ScratchRepository, tmp_path: Path
):
    upstream_repository.update_notes_branch_file(
        ProjectLocation.PERSONAL_STACK_CONFIGURATION,
        f'{StackSetting.UPSTREAM_REPOSITORY} = "{UpstreamSample.PREVIOUS_UPSTREAM}"\n'
        f"{UpstreamSample.OTHER_SETTING}",
    )

    finished = configure_upstream(upstream_repository, UpstreamSample.UPSTREAM)

    assert finished.returncode == 0, finished.stderr
    settings = published_stack_settings(upstream_repository, tmp_path)
    assert settings[StackSetting.UPSTREAM_REPOSITORY] == UpstreamSample.UPSTREAM
    assert settings[StackSetting.UPSTREAM_REMOTE] == "mine"


def test_a_value_naming_no_repository_is_refused_and_nothing_is_saved(
    upstream_repository: ScratchRepository, tmp_path: Path
):
    finished = configure_upstream(upstream_repository, UpstreamSample.MALFORMED)

    assert finished.returncode != 0
    checkout = upstream_repository.clone_notes_branch(tmp_path / "published")
    assert not (checkout / ProjectLocation.PERSONAL_STACK_CONFIGURATION).exists()


# %% the check


def test_an_unnamed_upstream_is_context_for_a_check_that_does_not_need_one(
    upstream_repository: ScratchRepository,
):
    """
    Most projects have no upstream, so its absence never fails a session's setup check.
    """
    status, _ = upstream_row(upstream_repository)

    assert status == "info"


def test_an_unnamed_upstream_needs_setup_for_a_check_that_needs_one(
    upstream_repository: ScratchRepository,
):
    status, detail = upstream_row(upstream_repository, REQUIRE_UPSTREAM)

    assert status == "needs-setup"
    assert SetupCommand.CONFIGURE_UPSTREAM in detail


def test_an_upstream_the_step_saved_passes_the_check(
    upstream_repository: ScratchRepository,
):
    configure_upstream(upstream_repository, UpstreamSample.UPSTREAM)

    status, detail = upstream_row(upstream_repository, REQUIRE_UPSTREAM)

    assert status == "ok"
    assert str(ProjectLocation.PERSONAL_STACK_CONFIGURATION) in detail


def test_an_upstream_the_project_commits_passes_the_check(
    upstream_repository: ScratchRepository,
):
    upstream_repository.write(
        ProjectLocation.PROJECT_STACK_CONFIGURATION,
        f'{StackSetting.UPSTREAM_REPOSITORY} = "{UpstreamSample.UPSTREAM}"\n',
    )

    status, detail = upstream_row(upstream_repository, REQUIRE_UPSTREAM)

    assert status == "ok"
    assert str(ProjectLocation.PROJECT_STACK_CONFIGURATION) in detail
