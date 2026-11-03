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
from pathlib import Path

import pytest

import basstler
from basstler.locations import PluginLocation, ProjectLocation, WorkflowLocation
from basstler.exit_codes import SetupCheckExitCode
from basstler.plan_site import dispatch_check, publication
from basstler.plan_site.dispatch_check import UNVERIFIED_PREFIX
from basstler.plan_site.hub import HubFileKey
from basstler.setup.report import CheckStatus, SetupCheck, SetupReport

from ..constants.environment import ConfigurationVariable, ScrubbedEnvironmentPrefix
from ..constants.notes import ScratchBranch
from ..constants.paths import DatasetLocation, PersonalNotesPath
from ..project_declaration import ProjectDeclaration
from ..scratch_repository import (
    SCRATCH_IDENTITY,
    ScratchRepository,
    PackageSourceFile,
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
    repository: ScratchRepository, *arguments: str, **environment_overrides: str
) -> SetupReport:
    """
    Run the scratch layout's check-setup.sh and parse its report.

    :param repository: A fixture-built scratch repository.
    :param arguments: The flags to pass.
    :param environment_overrides: Environment variables to set for this run, for the
        tests that exercise resolution from the environment.
    :return: The parsed report.
    """
    return SetupReport.from_completed_process(
        repository.run_hook_script(
            PluginLocation.SETUP_CHECK_SCRIPT.name, *arguments, **environment_overrides
        )
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


@pytest.fixture
def dispatch_needing_setup(
    check_setup_repository: ScratchRepository,
) -> ScratchRepository:
    """
    The scratch repository with a dispatch workflow on its notes branch, whose dispatch
    check reports that it needs setup.

    check-setup.sh runs the check in a process of its own, which imports it from the
    scratch checkout, so the stand-in replaces the module's file there.
    """
    check_setup_repository.update_notes_branch_file(
        WorkflowLocation.PLAN_SITE_DISPATCH, "name: Plan site dispatch\n"
    )
    package_root = Path(basstler.__file__).parent.parent
    shutil.copy(
        DatasetLocation.DISPATCH_CHECK_NEEDS_SETUP_STUB,
        check_setup_repository.checkout_root
        / PackageSourceFile.SOURCE
        / Path(dispatch_check.__file__).relative_to(package_root),
    )
    return check_setup_repository


def test_a_dispatch_workflow_is_reported_as_its_runs_say(
    dispatch_needing_setup: ScratchRepository,
):
    report = run_check_setup(dispatch_needing_setup)

    assert report.exit_code is SetupCheckExitCode.SETUP_INCOMPLETE
    assert report.results[SetupCheck.PLAN_SITE].status == CheckStatus.NEEDS_SETUP


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
        OnlyFlag.ONLY,
        SetupCheck.NOTES_BRANCH,
        OnlyFlag.ONLY,
        SetupCheck.NOTES_FILE,
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
        OnlyFlag.ONLY,
        SetupCheck.STACK_UPSTREAM,
    )

    assert report.exit_code is SetupCheckExitCode.SUCCESS
    assert report.results[SetupCheck.STACK_UPSTREAM].status == CheckStatus.OK


@pytest.mark.parametrize("check", list(SetupCheck))
def test_every_documented_check_can_be_requested(
    check_setup_repository: ScratchRepository, check: SetupCheck
):
    report = run_check_setup(check_setup_repository, OnlyFlag.ONLY, check)

    assert set(report.results) == {check}


def test_an_unknown_check_is_a_usage_error(check_setup_repository: ScratchRepository):
    result = check_setup_repository.run_hook_script(
        PluginLocation.SETUP_CHECK_SCRIPT.name, OnlyFlag.ONLY, "no_such_check"
    )

    assert result.returncode == SetupCheckExitCode.USAGE
    assert result.stdout == ""
