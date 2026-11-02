"""
Integration tests for save-personal-notes.sh: what it takes from the project's local
instructions as the personal notes, and pushes to the personal-notes branch.

Runs the real scripts against a local `git init --bare` fixture instead of a real
remote - no network access or real personal-notes branch involved.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from basstler.locations import PluginLocation, ProjectLocation

from ..constants.paths import PersonalNotesPath
from ..scratch_repository import SCRATCH_IDENTITY, ScratchRepository

# %% the scratch layout


@pytest.fixture
def notes_saving_repository(scratch_repository: ScratchRepository) -> ScratchRepository:
    """
    A scratch repository carrying the real session-start.sh, save-personal-notes.sh and
    the files they read, with a notes branch published to its notes remote that holds no
    personal notes yet.

    :param scratch_repository: The initialized scratch repository and notes remote.
    :return: The same repository, ready to run session-start.sh and then save notes.
    """
    scratch_repository.install_hook_scripts(
        PluginLocation.PERSONAL_NOTES_CONFIGURATION_SCRIPT.name,
        PluginLocation.SESSION_START_MESSAGES_SCRIPT.name,
        PluginLocation.SESSION_START_SCRIPT.name,
        PluginLocation.SESSION_RULES.name,
        PluginLocation.PERSONAL_NOTES_SAVING_SCRIPT.name,
    )
    scratch_repository.write("README.md", "scratch repo\n")
    scratch_repository.commit_everything("initial commit")
    scratch_repository.publish_notes_branch(
        {PersonalNotesPath.GIT_IDENTITY: SCRATCH_IDENTITY.as_git_config_file()}
    )
    scratch_repository.resolve_notes_remote_to()
    return scratch_repository


# %% first notes written beside what the session start generated


def test_first_notes_are_saved_without_the_sections_the_session_start_generated(
    notes_saving_repository: ScratchRepository, tmp_path: Path
):
    """
    Notes written above the generated sections, before any were saved, are saved alone:

    the session rules and the pull request progress stay out of them.
    """
    session_start = notes_saving_repository.run_hook_script(
        PluginLocation.SESSION_START_SCRIPT.name
    )
    assert session_start.returncode == 0, session_start.stderr
    local_instructions = (
        notes_saving_repository.project_root / PersonalNotesPath.LOCAL_INSTRUCTIONS
    )
    first_notes = "- Open every pull request as a draft.\n"
    local_instructions.write_text(first_notes + local_instructions.read_text())

    saving = notes_saving_repository.run_hook_script(
        PluginLocation.PERSONAL_NOTES_SAVING_SCRIPT.name
    )

    assert saving.returncode == 0, saving.stderr
    checkout = notes_saving_repository.clone_notes_branch(tmp_path / "notes")
    saved_notes = (checkout / ProjectLocation.PERSONAL_NOTES_DOCUMENT).read_text()
    assert saved_notes == first_notes
