"""
Tests for the install lock: a session start holds it while it installs the package, and a
caller of the package waits for it rather than failing on a half-installed environment.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from ..constants.environment import ConfigurationVariable
from ..scratch_repository import ScratchRepository

# %% a lock held by another process


REQUIRE_BASSTLER_PYTHON = "require_basstler_python"
"""
The shell configuration's readiness check every entry point of the package runs first.
"""


@pytest.fixture
def installed_repository(scratch_repository: ScratchRepository) -> ScratchRepository:
    """
    :param scratch_repository: The initialized scratch repository.
    :return: The same repository, with the package and its environment in place.
    """
    scratch_repository.install_package()
    scratch_repository.install_package_environment()
    return scratch_repository


def hold_the_lock(repository: ScratchRepository, holder: int) -> None:
    """
    Take the install lock in the name of another process, as a session start does.

    :param repository: The repository whose shell configuration names the lock.
    :param holder: The id of the process to name as holding it.
    """
    lock = Path(repository.configuration_value(ConfigurationVariable.INSTALL_LOCK))
    lock.mkdir(parents=True)
    Path(
        repository.configuration_value(ConfigurationVariable.INSTALL_LOCK_HOLDER)
    ).write_text(f"{holder}\n")


@pytest.fixture
def unfinished_install() -> Iterator[subprocess.Popen]:
    """
    :return: A process that outlives any test, standing for an install that never ends.
    """
    holder = subprocess.Popen(["sleep", "60"])
    yield holder
    holder.kill()
    holder.wait()


def test_a_caller_waits_for_an_install_in_progress(
    installed_repository: ScratchRepository, tmp_path: Path
):
    finished = tmp_path / "install-finished"
    # Started in the background of a shell that exits at once, so the install is
    # reaped when it ends rather than lingering as a child of this test.
    detached = subprocess.run(
        ["bash", "-c", f'(sleep 1; printf done > "{finished}") > /dev/null & echo $!'],
        capture_output=True,
        text=True,
        check=True,
    )
    hold_the_lock(installed_repository, int(detached.stdout))

    result = installed_repository.run_with_configuration(
        f'{REQUIRE_BASSTLER_PYTHON} && cat "{finished}"'
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "done"


def test_a_caller_stops_with_a_message_when_the_install_does_not_finish(
    installed_repository: ScratchRepository, unfinished_install: subprocess.Popen
):
    hold_the_lock(installed_repository, unfinished_install.pid)

    result = installed_repository.run_with_configuration(
        REQUIRE_BASSTLER_PYTHON, **{ConfigurationVariable.INSTALL_WAIT_SECONDS: "1"}
    )

    assert result.returncode == 1
    assert (
        installed_repository.configuration_value(ConfigurationVariable.INSTALL_LOCK)
        in result.stderr
    )


def test_a_lock_left_by_an_install_that_died_is_not_waited_on(
    installed_repository: ScratchRepository,
):
    holder = subprocess.Popen(["true"])
    holder.wait()
    hold_the_lock(installed_repository, holder.pid)

    result = installed_repository.run_with_configuration(
        REQUIRE_BASSTLER_PYTHON, **{ConfigurationVariable.INSTALL_WAIT_SECONDS: "0"}
    )

    assert result.returncode == 0, result.stderr
