"""
Integration tests for create-personal-notes-branch.sh.

Run against a scratch project root with a local bare repository standing in for the
personal-notes remote - no network access or real personal-notes branch involved.
"""

from __future__ import annotations

import pytest

from basstler.locations import PluginLocation

from .constants.notes import ScratchBranch
from .scratch_repository import ScratchRepository


@pytest.fixture
def branch_creation_repository(
    scratch_repository: ScratchRepository,
) -> ScratchRepository:
    """
    A scratch repository carrying the branch creation script, checked out on a branch
    that was never pushed, so it tracks no upstream - the state every fresh session
    branch starts in.

    :param scratch_repository: The initialized scratch repository and notes remote.
    :return: The same repository, ready to run the script.
    """
    scratch_repository.install_hook_scripts(
        PluginLocation.PERSONAL_NOTES_CONFIGURATION_SCRIPT.name,
        PluginLocation.PERSONAL_NOTES_BRANCH_CREATION_SCRIPT.name,
    )
    scratch_repository.write("README.md", "scratch project\n")
    scratch_repository.commit_everything("initial commit")
    scratch_repository.resolve_notes_remote_to()
    return scratch_repository


def test_creates_the_branch_from_a_branch_with_no_upstream(
    branch_creation_repository: ScratchRepository,
) -> None:
    """
    A branch with no upstream has no fallback remote to check, which is an answer, not
    an error - so the script goes on to create the notes branch rather than exiting.
    """
    result = branch_creation_repository.run_hook_script(
        PluginLocation.PERSONAL_NOTES_BRANCH_CREATION_SCRIPT.name
    )

    assert result.returncode == 0, result.stderr
    published = branch_creation_repository.run_git_allowing_failure(
        "ls-remote",
        "--exit-code",
        "--heads",
        str(branch_creation_repository.notes_remote_path),
        ScratchBranch.PERSONAL_NOTES,
    )
    assert published.returncode == 0
