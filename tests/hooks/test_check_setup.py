"""
Integration tests for check-setup.sh's per-check reporting and exit code.

Run against a scratch project root with a local bare repository standing in for the
personal-notes remote - no network access or real personal-notes branch involved.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from enum import StrEnum
from importlib.metadata import version
from pathlib import Path

import pytest

import basstler
from basstler.environment import EnvironmentFlag
from basstler.exit_codes import SetupCheckExitCode
from basstler.locations import (
    ClaudeCodeVariable,
    PackageLocation,
    PluginLocation,
    ProjectLocation,
    WorkflowLocation,
)
from basstler.personal_notes import access
from basstler.plan_site import build_start, dispatch_check, publication
from basstler.plan_site.dispatch_check import UNVERIFIED_PREFIX
from basstler.plan_site.hub import HubFileKey
from basstler.setup.report import CheckResult, CheckStatus, SetupCheck, SetupReport

from ..constants.environment import ConfigurationVariable, ScrubbedEnvironmentPrefix
from ..constants.notes import ScratchBranch
from ..constants.paths import DatasetLocation, PersonalNotesPath
from ..project_declaration import ProjectDeclaration
from ..scratch_repository import (
    SCRATCH_IDENTITY,
    PackageSourceFile,
    ScratchRepository,
    SetupPrerequisiteFile,
    initialize_bare_repository,
)
from ..script_runner import BashScriptRunner

# %% the scratch layout


@pytest.fixture
def check_setup_repository(scratch_repository: ScratchRepository) -> ScratchRepository:
    """
    A scratch repository set up so every check-setup.sh check passes: the real check-
    setup.sh and resolve-personal-notes-config.sh, placeholder tooling files, a
    registered SessionStart hook, a gitignored CLAUDE.local.md, and a notes branch
    carrying a notes file and the identity this repository's own commits are authored
    with.

    Individual tests break exactly one of those conditions to assert the matching check
    reports it.

    :param scratch_repository: The initialized scratch repository and notes remote.
    :return: The same repository, fully set up.
    """
    scratch_repository.install_hook_scripts(
        PluginLocation.PERSONAL_NOTES_CONFIGURATION_SCRIPT.name,
        PluginLocation.SETUP_CHECK_SCRIPT.name,
    )
    scratch_repository.install_package()

    scratch_repository.write_setup_prerequisites()
    scratch_repository.write("CLAUDE.local.md", "notes\n")

    scratch_repository.commit_everything("initial commit")
    scratch_repository.publish_notes_branch(
        {
            ProjectLocation.PERSONAL_NOTES_DOCUMENT: "my notes\n",
            PersonalNotesPath.GIT_IDENTITY: SCRATCH_IDENTITY.as_git_config_file(),
        }
    )
    scratch_repository.resolve_notes_remote_to()
    return scratch_repository


def run_check_setup(
    repository: ScratchRepository,
    *arguments: str,
    requested_checks: frozenset[SetupCheck] = frozenset(SetupCheck),
    **environment_overrides: str,
) -> SetupReport:
    """
    Run the scratch layout's check-setup.sh and parse its report.

    :param repository: A fixture-built scratch repository.
    :param arguments: The flags to pass besides :attr:`OnlyFlag.ONLY`.
    :param requested_checks: The checks to report on, each passed after
        :attr:`OnlyFlag.ONLY` unless every check is requested.
    :param environment_overrides: Environment variables to set for this run, for the
        tests that exercise resolution from the environment.
    :return: The parsed report.
    """
    only_arguments = (
        []
        if requested_checks == frozenset(SetupCheck)
        else [
            argument
            for check in sorted(requested_checks)
            for argument in (OnlyFlag.ONLY, check)
        ]
    )
    return SetupReport.from_completed_process(
        repository.run_hook_script(
            PluginLocation.SETUP_CHECK_SCRIPT.name,
            *arguments,
            *only_arguments,
            **environment_overrides,
        ),
        requested_checks,
    )


class OnlyFlag(StrEnum):
    """
    The check-setup.sh flags these tests pass.
    """

    ONLY = "--only"
    """
    Reports only the check named after it.
    """

    REQUIRE_UPSTREAM = "--require-upstream"
    """
    Makes a project naming no upstream a check that needs setup.
    """


# %% the already-set-up fast path


def test_reports_no_work_needed_when_everything_is_in_place(
    check_setup_repository: ScratchRepository,
):
    report = run_check_setup(check_setup_repository)
    assert report.exit_code is SetupCheckExitCode.SUCCESS
    needing_setup = [
        check
        for check, result in report.results.items()
        if result.status == CheckStatus.NEEDS_SETUP
    ]
    assert needing_setup == []


def test_reports_every_check_it_documents(check_setup_repository: ScratchRepository):
    report = run_check_setup(check_setup_repository)
    assert set(report.results) == set(SetupCheck)


def test_reports_every_check_it_documents_when_the_notes_branch_is_missing(
    check_setup_repository: ScratchRepository, tmp_path: Path
):
    check_setup_repository.resolve_notes_remote_to(
        initialize_bare_repository(tmp_path / "empty-remote.git")
    )

    report = run_check_setup(check_setup_repository)

    assert set(report.results) == set(SetupCheck)


# %% the personal-notes branch


def test_reports_a_missing_notes_branch_and_the_remotes_it_tried(
    check_setup_repository: ScratchRepository, tmp_path: Path
):
    empty_remote = initialize_bare_repository(tmp_path / "empty-remote.git")
    check_setup_repository.resolve_notes_remote_to(empty_remote)

    report = run_check_setup(check_setup_repository)
    assert report.exit_code is SetupCheckExitCode.SETUP_INCOMPLETE
    assert report.results[SetupCheck.NOTES_BRANCH].status == CheckStatus.NEEDS_SETUP
    assert str(empty_remote) in report.results[SetupCheck.NOTES_BRANCH].detail


def test_does_not_check_for_the_notes_file_when_its_branch_is_missing(
    check_setup_repository: ScratchRepository, tmp_path: Path
):
    check_setup_repository.resolve_notes_remote_to(
        initialize_bare_repository(tmp_path / "empty-remote.git")
    )

    report = run_check_setup(check_setup_repository)
    assert report.results[SetupCheck.NOTES_FILE].status == CheckStatus.NEEDS_SETUP
    assert report.results[SetupCheck.NOTES_FILE].detail == (
        "not checked - the branch that would hold it doesn't exist yet"
    )


def test_reports_a_notes_branch_that_exists_but_holds_no_notes_file(
    check_setup_repository: ScratchRepository,
):
    other_notes = str(ProjectLocation.PERSONAL_NOTES / "some-other-notes.md")
    check_setup_repository.run_git("config", "claude.personalNotesPath", other_notes)

    report = run_check_setup(check_setup_repository)
    assert report.exit_code is SetupCheckExitCode.SETUP_INCOMPLETE
    assert report.results[SetupCheck.NOTES_BRANCH].status == CheckStatus.OK
    assert report.results[SetupCheck.NOTES_FILE].status == CheckStatus.NEEDS_SETUP
    assert other_notes in report.results[SetupCheck.NOTES_FILE].detail


# %% the plan site


def test_a_notes_branch_without_the_dispatch_workflow_says_how_to_publish(
    check_setup_repository: ScratchRepository,
):
    report = run_check_setup(check_setup_repository)
    assert report.exit_code is SetupCheckExitCode.SUCCESS
    assert report.results[SetupCheck.PLAN_SITE].status == CheckStatus.INFORMATIONAL
    assert publication.__name__ in report.results[SetupCheck.PLAN_SITE].detail


def test_a_listed_repository_without_the_dispatch_workflow_names_the_site_it_is_missing_from(
    check_setup_repository: ScratchRepository,
):
    site_url = "https://an-owner.github.io/plans/"
    check_setup_repository.update_notes_branch_file(
        ProjectLocation.PLAN_HUB, f"{HubFileKey.SITE_URL}: {site_url}\n"
    )

    report = run_check_setup(check_setup_repository)

    plan_site = report.results[SetupCheck.PLAN_SITE]
    assert plan_site.status == CheckStatus.INFORMATIONAL
    assert site_url in plan_site.detail
    assert publication.__name__ in plan_site.detail


def test_a_dispatch_workflow_whose_runs_cannot_be_read_is_not_verified(
    check_setup_repository: ScratchRepository,
):
    check_setup_repository.update_notes_branch_file(
        WorkflowLocation.PLAN_SITE_DISPATCH, "name: Plan site dispatch\n"
    )

    report = run_check_setup(check_setup_repository)

    plan_site = report.results[SetupCheck.PLAN_SITE]
    assert report.exit_code is SetupCheckExitCode.SETUP_INCOMPLETE
    assert plan_site.status == CheckStatus.UNVERIFIED
    assert plan_site.detail.startswith(UNVERIFIED_PREFIX)
    assert publication.__name__ in plan_site.detail


# %% the notes repository


def with_notes_access_stub(
    repository: ScratchRepository, stub: DatasetLocation
) -> ScratchRepository:
    """
    Make the scratch repository's notes access command print what a stand-in prints.

    :param repository: The scratch repository, fully set up.
    :param stub: The module whose output replaces the notes access command's.
    :return: The same repository.
    """
    repository.replace_package_module(access, stub)
    return repository


def test_a_notes_repository_the_session_cannot_reach_needs_setup(
    check_setup_repository: ScratchRepository,
):
    with_notes_access_stub(check_setup_repository, DatasetLocation.NOTES_ACCESS_STUB)

    report = run_check_setup(check_setup_repository)

    reached = report.results[SetupCheck.NOTES_REPOSITORY_ACCESS]
    assert report.exit_code is SetupCheckExitCode.SETUP_INCOMPLETE
    assert reached.status == CheckStatus.NEEDS_SETUP
    assert reached.detail == access.__name__


def test_a_notes_repository_the_session_reaches_passes(
    check_setup_repository: ScratchRepository,
):
    with_notes_access_stub(
        check_setup_repository, DatasetLocation.NOTES_ACCESS_REACHED_STUB
    )

    report = run_check_setup(check_setup_repository)

    assert report.results[SetupCheck.NOTES_REPOSITORY_ACCESS].status == CheckStatus.OK


# %% the plan site access


def with_build_start_stub(
    repository: ScratchRepository, stub: DatasetLocation
) -> ScratchRepository:
    """
    Make the scratch repository's build start command print what a stand-in prints,
    and record a plan site for it.

    :param repository: The scratch repository, fully set up.
    :param stub: The module whose output replaces the build start command's.
    :return: The same repository.
    """
    repository.update_notes_branch_file(
        ProjectLocation.PLAN_HUB,
        f"{HubFileKey.SITE_URL}: https://an-owner.github.io/plans/\n",
    )
    package_root = Path(basstler.__file__).parent.parent
    shutil.copy(
        stub,
        repository.checkout_root
        / PackageSourceFile.SOURCE
        / Path(build_start.__file__).relative_to(package_root),
    )
    return repository


def test_a_cloud_session_that_cannot_start_the_build_needs_setup(
    check_setup_repository: ScratchRepository,
):
    with_build_start_stub(
        check_setup_repository, DatasetLocation.BUILD_START_NEEDS_ACCESS_STUB
    )

    report = run_check_setup(
        check_setup_repository, **{ClaudeCodeVariable.REMOTE: EnvironmentFlag.TRUE}
    )

    access = report.results[SetupCheck.PLAN_SITE_ACCESS]
    assert report.exit_code is SetupCheckExitCode.SETUP_INCOMPLETE
    assert access.status == CheckStatus.NEEDS_SETUP
    assert "\n" not in access.detail
    assert "an-owner/the-site" in access.detail


def test_a_cloud_session_that_can_start_the_build_passes(
    check_setup_repository: ScratchRepository,
):
    with_build_start_stub(
        check_setup_repository, DatasetLocation.BUILD_START_HAS_ACCESS_STUB
    )

    report = run_check_setup(
        check_setup_repository, **{ClaudeCodeVariable.REMOTE: EnvironmentFlag.TRUE}
    )

    assert report.results[SetupCheck.PLAN_SITE_ACCESS].status == CheckStatus.OK


def test_a_local_session_that_cannot_start_the_build_gets_the_issue_and_the_fix(
    check_setup_repository: ScratchRepository,
):
    with_build_start_stub(
        check_setup_repository, DatasetLocation.BUILD_START_NEEDS_ACCESS_STUB
    )

    report = run_check_setup(check_setup_repository)

    access = report.results[SetupCheck.PLAN_SITE_ACCESS]
    assert access.status == CheckStatus.INFORMATIONAL
    assert "cannot start the build in an-owner/the-site" in access.detail
    assert "Attach it" in access.detail


def test_a_clone_no_plan_site_lists_reports_the_access_check_as_context(
    check_setup_repository: ScratchRepository,
):
    report = run_check_setup(
        check_setup_repository, **{ClaudeCodeVariable.REMOTE: EnvironmentFlag.TRUE}
    )

    assert (
        report.results[SetupCheck.PLAN_SITE_ACCESS].status == CheckStatus.INFORMATIONAL
    )


def with_dispatch_check_stub(
    repository: ScratchRepository, stub: DatasetLocation
) -> ScratchRepository:
    """
    Give the scratch repository a dispatch workflow on its notes branch, and make its
    dispatch check print what a stand-in prints.

    check-setup.sh runs the check in a process of its own, which imports it from the
    scratch checkout, so the stand-in replaces the module's file there.

    :param repository: The scratch repository, fully set up.
    :param stub: The module whose output replaces the dispatch check's.
    :return: The same repository.
    """
    repository.update_notes_branch_file(
        WorkflowLocation.PLAN_SITE_DISPATCH, "name: Plan site dispatch\n"
    )
    package_root = Path(basstler.__file__).parent.parent
    shutil.copy(
        stub,
        repository.checkout_root
        / PackageSourceFile.SOURCE
        / Path(dispatch_check.__file__).relative_to(package_root),
    )
    return repository


@pytest.fixture
def dispatch_needing_setup(
    check_setup_repository: ScratchRepository,
) -> ScratchRepository:
    """
    The scratch repository whose dispatch check reports that it needs setup.
    """
    return with_dispatch_check_stub(
        check_setup_repository, DatasetLocation.DISPATCH_CHECK_NEEDS_SETUP_STUB
    )


@pytest.fixture
def dispatch_with_other_repository(
    check_setup_repository: ScratchRepository,
) -> ScratchRepository:
    """
    The scratch repository whose dispatch check reports its own repository as starting
    the build and a second repository as informational.
    """
    return with_dispatch_check_stub(
        check_setup_repository,
        DatasetLocation.DISPATCH_CHECK_WITH_OTHER_REPOSITORY_STUB,
    )


def test_a_dispatch_workflow_is_reported_as_its_runs_say(
    dispatch_needing_setup: ScratchRepository,
):
    report = run_check_setup(dispatch_needing_setup)

    assert report.exit_code is SetupCheckExitCode.SETUP_INCOMPLETE
    assert report.results[SetupCheck.PLAN_SITE].status == CheckStatus.NEEDS_SETUP


def test_every_other_repository_on_the_plan_site_gets_a_row_of_its_own(
    dispatch_with_other_repository: ScratchRepository,
):
    report = run_check_setup(dispatch_with_other_repository)

    assert report.results[SetupCheck.PLAN_SITE].status == CheckStatus.OK
    assert report.repository_results == [
        CheckResult(CheckStatus.INFORMATIONAL, "another repository's latest run failed")
    ]


def test_a_repository_row_never_fails_the_run(
    dispatch_with_other_repository: ScratchRepository,
):
    report = run_check_setup(
        dispatch_with_other_repository,
        requested_checks=frozenset({SetupCheck.PLAN_SITE}),
    )

    assert report.exit_code is SetupCheckExitCode.SUCCESS


def test_a_repository_row_is_not_printed_when_the_plan_site_is_not_requested(
    dispatch_with_other_repository: ScratchRepository,
):
    report = run_check_setup(
        dispatch_with_other_repository,
        requested_checks=frozenset({SetupCheck.NOTES_FILE}),
    )

    assert report.repository_results == []


def test_the_dispatch_workflow_path_matches_the_shell_configuration(
    check_setup_repository: ScratchRepository,
):
    assert check_setup_repository.configuration_value(
        "PLAN_SITE_DISPATCH_WORKFLOW_PATH"
    ) == str(WorkflowLocation.PLAN_SITE_DISPATCH)


# %% the package's version


def test_the_latest_release_is_reported_beside_the_installed_package(
    check_setup_repository: ScratchRepository,
):
    latest_release = "v0.10.0"
    check_setup_repository.run_git("tag", latest_release)

    report = run_check_setup(check_setup_repository)

    version = report.results[SetupCheck.BASSTLER_VERSION]
    assert version.status == CheckStatus.INFORMATIONAL
    assert latest_release in version.detail


def test_a_latest_release_that_cannot_be_read_says_where_it_was_looked_for(
    check_setup_repository: ScratchRepository,
):
    report = run_check_setup(check_setup_repository)

    version = report.results[SetupCheck.BASSTLER_VERSION]
    assert version.status == CheckStatus.INFORMATIONAL
    assert str(check_setup_repository.project_root) in version.detail


def remove_checkout_around_plugin(repository: ScratchRepository) -> None:
    """
    Make the scratch plugin one installed on its own, outside a checkout.

    :param repository: A fixture-built scratch repository.
    """
    (repository.checkout_root / PackageSourceFile.METADATA).unlink()


def test_a_package_of_another_release_than_the_plugin_s_is_mismatched(
    check_setup_repository: ScratchRepository,
):
    """
    Hooks of one release calling the package of another can pass options it no longer
    accepts, so the pair being two releases is a status of its own, failing the run.
    """
    remove_checkout_around_plugin(check_setup_repository)
    check_setup_repository.release_plugin_as("0.0.1")

    report = run_check_setup(check_setup_repository)

    assert report.results[SetupCheck.BASSTLER_VERSION].status == CheckStatus.MISMATCHED
    assert report.exit_code is SetupCheckExitCode.SETUP_INCOMPLETE


def test_a_plugin_naming_no_release_outside_a_checkout_is_mismatched(
    check_setup_repository: ScratchRepository,
):
    """
    Nothing pins the package to a plugin that names no release, so the pair cannot be
    told apart from two releases.
    """
    remove_checkout_around_plugin(check_setup_repository)

    report = run_check_setup(check_setup_repository)

    assert report.results[SetupCheck.BASSTLER_VERSION].status == CheckStatus.MISMATCHED


def test_a_package_of_the_plugin_s_release_passes(
    check_setup_repository: ScratchRepository,
):
    """
    The package installed at the plugin's own release is what every hook expects.
    """
    remove_checkout_around_plugin(check_setup_repository)
    check_setup_repository.release_plugin_as(
        version(PackageLocation.DIRECTORY.value.name)
    )

    report = run_check_setup(
        check_setup_repository,
        requested_checks=frozenset({SetupCheck.BASSTLER_VERSION}),
    )

    assert report.results[SetupCheck.BASSTLER_VERSION].status == CheckStatus.OK
    assert report.exit_code is SetupCheckExitCode.SUCCESS


# %% who commits here would be authored as


def test_reports_a_recorded_identity_that_matches_this_clone(
    check_setup_repository: ScratchRepository,
):
    report = run_check_setup(check_setup_repository)
    assert report.results[SetupCheck.GIT_IDENTITY].status == CheckStatus.OK
    assert (
        f"{SCRATCH_IDENTITY.name} <{SCRATCH_IDENTITY.email}>"
        in report.results[SetupCheck.GIT_IDENTITY].detail
    )


def test_reports_a_notes_branch_that_records_no_identity(
    check_setup_repository: ScratchRepository,
):
    check_setup_repository.remove_from_notes_branch(PersonalNotesPath.GIT_IDENTITY)

    report = run_check_setup(check_setup_repository)
    assert report.exit_code is SetupCheckExitCode.SETUP_INCOMPLETE
    assert report.results[SetupCheck.GIT_IDENTITY].status == CheckStatus.NEEDS_SETUP
    assert (
        f"{SCRATCH_IDENTITY.name} <{SCRATCH_IDENTITY.email}>"
        in report.results[SetupCheck.GIT_IDENTITY].detail
    )


def test_reports_a_recorded_identity_this_clone_does_not_commit_as(
    check_setup_repository: ScratchRepository,
):
    check_setup_repository.run_git("config", "user.name", "Somebody Else")

    report = run_check_setup(check_setup_repository)
    assert report.exit_code is SetupCheckExitCode.SETUP_INCOMPLETE
    assert report.results[SetupCheck.GIT_IDENTITY].status == CheckStatus.NEEDS_SETUP
    detail = report.results[SetupCheck.GIT_IDENTITY].detail
    assert f"{SCRATCH_IDENTITY.name} <{SCRATCH_IDENTITY.email}>" in detail
    assert f"Somebody Else <{SCRATCH_IDENTITY.email}>" in detail


def test_reads_the_identity_the_environment_overrides_config_with(
    check_setup_repository: ScratchRepository,
):
    report = run_check_setup(
        check_setup_repository,
        GIT_AUTHOR_NAME="Environment Author",
        GIT_AUTHOR_EMAIL="environment@example.com",
    )
    assert report.exit_code is SetupCheckExitCode.SETUP_INCOMPLETE
    assert report.results[SetupCheck.GIT_IDENTITY].status == CheckStatus.NEEDS_SETUP
    assert (
        "Environment Author <environment@example.com>"
        in report.results[SetupCheck.GIT_IDENTITY].detail
    )


def test_does_not_check_the_identity_when_the_notes_branch_is_missing(
    check_setup_repository: ScratchRepository, tmp_path: Path
):
    check_setup_repository.resolve_notes_remote_to(
        initialize_bare_repository(tmp_path / "empty-remote.git")
    )

    report = run_check_setup(check_setup_repository)
    assert report.results[SetupCheck.GIT_IDENTITY].status == CheckStatus.NEEDS_SETUP
    assert report.results[SetupCheck.GIT_IDENTITY].detail == (
        "not checked - the branch that would record it doesn't exist yet"
    )


# %% how each setting was resolved


def test_reports_which_source_each_resolved_setting_came_from(
    check_setup_repository: ScratchRepository,
):
    report = run_check_setup(check_setup_repository)
    assert (
        "from git config claude.personalNotesRemote"
        in report.results[SetupCheck.NOTES_REMOTE].detail
    )
    assert report.results[SetupCheck.NOTES_BRANCH_NAME].detail == (
        f"{ScratchBranch.PERSONAL_NOTES} (from built-in default)"
    )
    assert report.results[SetupCheck.NOTES_PATH].detail == (
        f"{ProjectLocation.PERSONAL_NOTES_DOCUMENT} (from built-in default)"
    )


def test_reports_a_setting_resolved_from_the_environment(
    check_setup_repository: ScratchRepository,
):
    notes_path = str(ProjectLocation.PERSONAL_NOTES / "from-the-environment.md")
    report = run_check_setup(
        check_setup_repository, CLAUDE_PERSONAL_NOTES_PATH=notes_path
    )
    assert report.results[SetupCheck.NOTES_PATH].detail == (
        f"{notes_path} (from environment variable CLAUDE_PERSONAL_NOTES_PATH)"
    )


# %% the plugin's own files


def test_reports_which_tooling_files_the_plugin_is_missing(
    check_setup_repository: ScratchRepository,
):
    (check_setup_repository.plugin_root / SetupPrerequisiteFile.PLAN_SCHEMA).unlink()

    report = run_check_setup(check_setup_repository)
    assert report.exit_code is SetupCheckExitCode.SETUP_INCOMPLETE
    assert report.results[SetupCheck.TOOLING_FILES].status == CheckStatus.NEEDS_SETUP
    assert (
        SetupPrerequisiteFile.PLAN_SCHEMA
        in report.results[SetupCheck.TOOLING_FILES].detail
    )
    assert (
        SetupPrerequisiteFile.PLUGIN_MANIFEST
        not in report.results[SetupCheck.TOOLING_FILES].detail
    )


def test_reports_a_session_start_hook_that_is_not_registered(
    check_setup_repository: ScratchRepository,
):
    (
        check_setup_repository.plugin_root
        / PluginLocation.HOOKS.value.name
        / "hooks.json"
    ).write_text("{}\n")

    report = run_check_setup(check_setup_repository)
    assert report.exit_code is SetupCheckExitCode.SETUP_INCOMPLETE
    assert (
        report.results[SetupCheck.SESSION_START_HOOK].status == CheckStatus.NEEDS_SETUP
    )


def test_reports_a_claude_local_md_that_is_not_gitignored(
    check_setup_repository: ScratchRepository,
):
    check_setup_repository.write(".gitignore", "something-else\n")

    report = run_check_setup(check_setup_repository)
    assert report.exit_code is SetupCheckExitCode.SETUP_INCOMPLETE
    assert (
        report.results[SetupCheck.CLAUDE_LOCAL_MD_IGNORED].status
        == CheckStatus.NEEDS_SETUP
    )


# %% package dependencies


def test_reports_declared_dependencies_that_are_not_installed(
    check_setup_repository: ScratchRepository,
):
    (check_setup_repository.checkout_root / PackageSourceFile.METADATA).write_text(
        DatasetLocation.PARTLY_INSTALLED_PROJECT.read_text(),
    )
    installed, uninstalled = ProjectDeclaration.read(
        DatasetLocation.PARTLY_INSTALLED_PROJECT
    ).dependencies

    report = run_check_setup(check_setup_repository)
    detail = report.results[SetupCheck.PACKAGE_DEPENDENCIES].detail
    assert report.exit_code is SetupCheckExitCode.SETUP_INCOMPLETE
    assert (
        report.results[SetupCheck.PACKAGE_DEPENDENCIES].status
        == CheckStatus.NEEDS_SETUP
    )
    assert uninstalled in detail
    assert installed not in detail


def test_reports_a_declaration_it_cannot_read_rather_than_nothing_missing(
    check_setup_repository: ScratchRepository,
):
    """
    A declaration the lookup cannot parse says nothing about what is installed, so it is
    not reported as an environment with nothing missing.
    """
    (check_setup_repository.checkout_root / PackageSourceFile.METADATA).write_text(
        "this is not toml\n"
    )

    report = run_check_setup(check_setup_repository)

    assert report.exit_code is SetupCheckExitCode.SETUP_INCOMPLETE
    assert (
        report.results[SetupCheck.PACKAGE_DEPENDENCIES].status
        == CheckStatus.NEEDS_SETUP
    )


def mark_an_install_in_progress(repository: ScratchRepository, process_id: int) -> None:
    """
    Leave the marker a session start writes while it installs the package.

    :param repository: A fixture-built scratch repository.
    :param process_id: The process the marker names as the installer.
    """
    marker = Path(repository.configuration_value(ConfigurationVariable.INSTALL_MARKER))
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(f"{process_id}\n")


def test_reports_dependencies_a_session_start_is_installing_as_in_progress(
    check_setup_repository: ScratchRepository,
):
    mark_an_install_in_progress(check_setup_repository, os.getpid())

    report = run_check_setup(check_setup_repository)

    assert report.exit_code is SetupCheckExitCode.SETUP_INCOMPLETE
    assert (
        report.results[SetupCheck.PACKAGE_DEPENDENCIES].status
        == CheckStatus.IN_PROGRESS
    )


def test_a_marker_left_by_an_install_that_ended_is_not_in_progress(
    check_setup_repository: ScratchRepository,
):
    finished = subprocess.Popen(["true"])
    finished.wait()
    mark_an_install_in_progress(check_setup_repository, finished.pid)

    report = run_check_setup(check_setup_repository)

    assert report.results[SetupCheck.PACKAGE_DEPENDENCIES].status == CheckStatus.OK


def test_waiting_for_an_install_still_running_gives_up_after_its_timeout(
    check_setup_repository: ScratchRepository,
):
    mark_an_install_in_progress(check_setup_repository, os.getpid())

    status = check_setup_repository.configuration_output(
        "wait_for_basstler_install 0; printf '%s' \"$?\""
    )

    assert status == "1"


def test_waiting_for_an_install_that_ended_returns_at_once(
    check_setup_repository: ScratchRepository,
):
    finished = subprocess.Popen(["true"])
    finished.wait()
    mark_an_install_in_progress(check_setup_repository, finished.pid)

    status = check_setup_repository.configuration_output(
        "wait_for_basstler_install 0; printf '%s' \"$?\""
    )

    assert status == "0"


# %% the outcome of it all working


def test_reports_a_claude_local_md_that_was_never_written(
    check_setup_repository: ScratchRepository,
):
    (check_setup_repository.project_root / "CLAUDE.local.md").unlink()

    report = run_check_setup(check_setup_repository)
    assert report.exit_code is SetupCheckExitCode.SETUP_INCOMPLETE
    assert report.results[SetupCheck.CLAUDE_LOCAL_MD].status == CheckStatus.NEEDS_SETUP


# %% where it runs


@pytest.fixture
def outside_any_repository(tmp_path: Path) -> Path:
    """
    :return: A directory no git work tree contains.
    """
    outside = tmp_path / "outside-any-repository"
    outside.mkdir()
    return outside


def run_check_setup_outside(
    check_setup_repository: ScratchRepository, outside: Path
) -> subprocess.CompletedProcess[str]:
    """
    :param check_setup_repository: The repository whose plugin and home are used.
    :param outside: The directory to run in.
    :return: The finished check-setup.sh run.
    """
    runner = BashScriptRunner(
        project_root=outside,
        removed_variable_prefixes=tuple(ScrubbedEnvironmentPrefix),
        script_path=check_setup_repository.plugin_root
        / PluginLocation.HOOKS.value.name
        / PluginLocation.SETUP_CHECK_SCRIPT.name,
    )
    return runner.run(
        **{ConfigurationVariable.HOME: str(check_setup_repository.basstler_home)}
    )


def test_run_outside_a_repository_reports_nothing_and_exits_distinctly(
    check_setup_repository: ScratchRepository, outside_any_repository: Path
):
    """
    Outside a work tree no row is printed, and the status says why.
    """
    result = run_check_setup_outside(check_setup_repository, outside_any_repository)

    assert result.returncode == SetupCheckExitCode.NOT_IN_REPOSITORY
    assert result.stdout == ""


def test_run_outside_a_repository_names_the_directory_on_stderr(
    check_setup_repository: ScratchRepository, outside_any_repository: Path
):
    """
    The refusal names the directory it was run in, so the reader can tell what to fix.
    """
    result = run_check_setup_outside(check_setup_repository, outside_any_repository)

    assert str(outside_any_repository.resolve()) in result.stderr


# %% reporting only the requested checks


def test_only_the_requested_checks_are_reported(
    check_setup_repository: ScratchRepository,
):
    report = run_check_setup(
        check_setup_repository,
        requested_checks=frozenset({SetupCheck.NOTES_BRANCH, SetupCheck.NOTES_FILE}),
    )

    assert set(report.results) == {SetupCheck.NOTES_BRANCH, SetupCheck.NOTES_FILE}


def test_a_failing_unrequested_check_does_not_fail_the_requested_one(
    dispatch_needing_setup: ScratchRepository,
):
    dispatch_needing_setup.write(
        ProjectLocation.PROJECT_STACK_CONFIGURATION,
        DatasetLocation.SCRATCH_FORK_STACK_CONFIGURATION.read_text(),
    )

    report = run_check_setup(
        dispatch_needing_setup,
        OnlyFlag.REQUIRE_UPSTREAM,
        requested_checks=frozenset({SetupCheck.STACK_UPSTREAM}),
    )

    assert report.exit_code is SetupCheckExitCode.SUCCESS
    assert report.results[SetupCheck.STACK_UPSTREAM].status == CheckStatus.OK


@pytest.mark.parametrize("check", list(SetupCheck))
def test_every_documented_check_can_be_requested(
    check_setup_repository: ScratchRepository, check: SetupCheck
):
    report = run_check_setup(
        check_setup_repository, requested_checks=frozenset({check})
    )

    assert set(report.results) == {check}


def test_an_unknown_check_is_a_usage_error(check_setup_repository: ScratchRepository):
    result = check_setup_repository.run_hook_script(
        PluginLocation.SETUP_CHECK_SCRIPT.name, OnlyFlag.ONLY, "no_such_check"
    )

    assert result.returncode == SetupCheckExitCode.USAGE
    assert result.stdout == ""
