"""
Tests for putting a git setting in force for a process without writing it anywhere.
"""

from __future__ import annotations

import os
import subprocess

from basstler.git.commands import TransientGitSetting

from ..scratch_repository import ScratchRepository

# %% settings git sees


def test_a_setting_added_on_top_of_another_leaves_both_in_force(
    scratch_repository: ScratchRepository,
):
    """
    Each setting takes the next free index, so one added later never replaces one
    already in the environment.
    """
    settings = [
        TransientGitSetting("basstler.first", "one"),
        TransientGitSetting("basstler.second", "two"),
    ]
    environment = dict(os.environ)
    for setting in settings:
        environment |= setting.variables(environment)

    values = [
        subprocess.run(
            ["git", "config", "--get", setting.key],
            cwd=scratch_repository.project_root,
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        for setting in settings
    ]

    assert values == [setting.value for setting in settings]


def test_a_setting_is_written_to_no_config_file(
    scratch_repository: ScratchRepository,
):
    """
    Git outside the environment the setting was added to does not see it.
    """
    setting = TransientGitSetting("basstler.unwritten", "value")
    subprocess.run(
        ["git", "config", "--get", setting.key],
        cwd=scratch_repository.project_root,
        env={**os.environ, **setting.variables(os.environ)},
        check=True,
    )

    unwritten = scratch_repository.run_git_allowing_failure(
        "config", "--get", setting.key
    )

    assert unwritten.returncode != 0
