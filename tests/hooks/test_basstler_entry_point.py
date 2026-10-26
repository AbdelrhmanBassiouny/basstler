"""
Tests for basstler.sh, the entry point every skill runs a module of the package through:
it runs the module once the package is ready, waits on or completes an install that is
not finished, and says in one line why when the package still cannot run.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from basstler.locations import PluginLocation
from basstler.shell_configuration import ShellConfigurationFunction

from ..constants.environment import ConfigurationVariable, SearchPathVariable
from ..executable_stubs import ExecutableStubDirectory, path_hiding_executables
from ..scratch_repository import ScratchRepository
from .test_session_start import PackageManager, StubVariable

MODULE_WITH_HELP = "maintenance"
"""
A module of the package whose ``--help`` succeeds without a board or a credential.
"""


# %% the scratch layout


@pytest.fixture
def entry_point_repository(scratch_repository: ScratchRepository) -> ScratchRepository:
    """
    A scratch repository whose plugin carries basstler.sh and whose package environment
    is installed and current.

    :param scratch_repository: The initialized scratch repository.
    :return: The same repository.
    """
    scratch_repository.install_hook_scripts(
        PluginLocation.PERSONAL_NOTES_CONFIGURATION_SCRIPT.name,
        PluginLocation.ENTRY_POINT_SCRIPT.name,
    )
    scratch_repository.install_package()
    scratch_repository.install_package_environment()
    return scratch_repository


def run_entry_point(
    repository: ScratchRepository, *arguments: str, **environment: str
) -> subprocess.CompletedProcess[str]:
    """
    :param repository: The fixture-built scratch repository.
    :param arguments: The module and its arguments.
    :param environment: Variables to set for the run.
    :return: The finished basstler.sh.
    """
    return repository.run_hook_script(
        PluginLocation.ENTRY_POINT_SCRIPT.name, *arguments, **environment
    )


def installed_source_file(repository: ScratchRepository) -> Path:
    """
    :param repository: The fixture-built scratch repository.
    :return: The file recording what the environment's package was installed from.
    """
    return Path(repository.configuration_value(ConfigurationVariable.INSTALLED_SOURCE_FILE))


def install_lock(repository: ScratchRepository) -> Path:
    """
    :param repository: The fixture-built scratch repository.
    :return: The directory held while the package is installed.
    """
    return Path(repository.configuration_value(ConfigurationVariable.INSTALL_LOCK))


def hold_install_lock(repository: ScratchRepository, holder: int) -> Path:
    """
    :param repository: The fixture-built scratch repository.
    :param holder: The process id to record as holding it.
    :return: The lock, now held.
    """
    lock = install_lock(repository)
    lock.mkdir(parents=True)
    (lock / "pid").write_text(f"{holder}\n")
    return lock


def a_process_that_has_exited() -> int:
    """
    :return: The id of a process that has already exited.
    """
    finished = subprocess.Popen(["true"])
    finished.wait()
    return finished.pid


def pip_only_path(stub_bin: ExecutableStubDirectory, tmp_path: Path) -> str:
    """
    :param stub_bin: The stub directory, holding the ``pip`` stub.
    :param tmp_path: pytest's per-test temporary directory.
    :return: A ``PATH`` finding the ``pip`` stub and no ``uv``.
    """
    stub_bin.install(PackageManager.PIP)
    return stub_bin.ahead_of(path_hiding_executables(tmp_path, PackageManager.UV))


# %% a ready package


def test_a_ready_package_runs_the_module(entry_point_repository: ScratchRepository):
    result = run_entry_point(entry_point_repository, MODULE_WITH_HELP, "--help")

    assert result.returncode == 0, result.stderr
    assert f"basstler.{MODULE_WITH_HELP}" in result.stdout


# %% an install that is not finished


def test_an_install_that_never_finished_is_completed_before_the_module_runs(
    entry_point_repository: ScratchRepository,
    stub_bin: ExecutableStubDirectory,
    tmp_path: Path,
):
    """
    The session start died holding the lock, mid-install: the lock is taken over and the
    install run again.
    """
    installed_source_file(entry_point_repository).unlink()
    hold_install_lock(entry_point_repository, a_process_that_has_exited())
    call_log = tmp_path / "pip-calls"

    result = run_entry_point(
        entry_point_repository,
        MODULE_WITH_HELP,
        "--help",
        **{
            SearchPathVariable.EXECUTABLE_SEARCH_PATH: pip_only_path(stub_bin, tmp_path),
            StubVariable.PIP_CALL_LOG: str(call_log),
        },
    )

    assert result.returncode == 0, result.stderr
    assert len(call_log.read_text().splitlines()) == 1
    assert not install_lock(entry_point_repository).exists()


def test_an_install_still_running_is_waited_for_rather_than_repeated(
    entry_point_repository: ScratchRepository,
    stub_bin: ExecutableStubDirectory,
    tmp_path: Path,
):
    source_file = installed_source_file(entry_point_repository)
    source = source_file.read_text()
    source_file.unlink()
    lock = install_lock(entry_point_repository)
    running_install = subprocess.Popen(
        [
            "bash",
            "-c",
            'sleep 1; printf "%s" "$1" > "$2"; rm -rf "$3"',
            "running-install",
            source,
            str(source_file),
            str(lock),
        ]
    )
    hold_install_lock(entry_point_repository, running_install.pid)
    call_log = tmp_path / "pip-calls"

    result = run_entry_point(
        entry_point_repository,
        MODULE_WITH_HELP,
        "--help",
        **{
            SearchPathVariable.EXECUTABLE_SEARCH_PATH: pip_only_path(stub_bin, tmp_path),
            StubVariable.PIP_CALL_LOG: str(call_log),
        },
    )
    running_install.wait()

    assert result.returncode == 0, result.stderr
    assert not call_log.exists()


# %% a package that cannot run


def test_a_failed_install_is_one_line_naming_what_to_run(
    entry_point_repository: ScratchRepository,
    stub_bin: ExecutableStubDirectory,
    tmp_path: Path,
):
    installed_source_file(entry_point_repository).unlink()

    result = run_entry_point(
        entry_point_repository,
        MODULE_WITH_HELP,
        "--help",
        **{
            SearchPathVariable.EXECUTABLE_SEARCH_PATH: pip_only_path(stub_bin, tmp_path),
            StubVariable.PIP_STATUS: "1",
        },
    )

    source = entry_point_repository.configuration_output(
        ShellConfigurationFunction.BASSTLER_PACKAGE_SOURCE
    ).strip()
    assert result.returncode == 1
    assert result.stdout == ""
    (line,) = result.stderr.splitlines()
    assert line.startswith(f"could not install {source}: ")
    assert f" - run: {PackageManager.PIP} --python " in line


def test_an_install_held_by_a_live_process_past_the_wait_is_one_line_naming_the_lock(
    entry_point_repository: ScratchRepository,
):
    installed_source_file(entry_point_repository).unlink()
    lock = hold_install_lock(entry_point_repository, os.getpid())

    result = run_entry_point(
        entry_point_repository,
        MODULE_WITH_HELP,
        "--help",
        **{ConfigurationVariable.INSTALL_WAIT_SECONDS: "0"},
    )

    assert result.returncode == 1
    (line,) = result.stderr.splitlines()
    assert str(lock) in line
