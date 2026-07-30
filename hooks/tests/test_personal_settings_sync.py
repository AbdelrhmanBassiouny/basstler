"""
Integration tests for the personal Claude Code settings round trip: session-start.sh
writing `.claude/settings.local.json` from the personal-notes branch, and save-personal-
settings.sh pushing local edits back to it.

Runs the real scripts against a local `git init --bare` fixture instead of a real
remote - no network access or real personal-notes branch involved.
"""

from conftest import ScratchProject

SETTINGS_PATH_ON_NOTES_BRANCH = ".claude/personal/settings.local.json"
LOCAL_SETTINGS_PATH = ".claude/settings.local.json"

PERSONAL_SETTINGS = '{\n  "permissions": {\n    "allow": ["Artifact"]\n  }\n}\n'
UPDATED_PERSONAL_SETTINGS = (
    '{\n  "permissions": {\n    "allow": ["Artifact", "Read"]\n  }\n}\n'
)
LOCALLY_EDITED_SETTINGS = (
    '{\n  "permissions": {\n    "allow": ["Artifact", "Bash(pytest *)"]\n  }\n}\n'
)


def local_settings_of(scratch_project: ScratchProject) -> str:
    """
    Return the project's current `.claude/settings.local.json` content.

    :param scratch_project: The scratch project to read from.
    :return: The file's content.
    """
    return (scratch_project.root / LOCAL_SETTINGS_PATH).read_text()


# %% syncing settings out of the personal-notes branch


def test_writes_the_branch_settings_when_the_project_has_none(
    scratch_project: ScratchProject,
):
    scratch_project.write_notes_branch_file(
        SETTINGS_PATH_ON_NOTES_BRANCH, PERSONAL_SETTINGS
    )

    result = scratch_project.run_hook("session-start.sh")

    assert result.returncode == 0, result.stderr
    assert local_settings_of(scratch_project) == PERSONAL_SETTINGS
    assert f"local settings:  synced to {LOCAL_SETTINGS_PATH}" in result.stdout


def test_writes_no_settings_when_the_branch_has_none(scratch_project: ScratchProject):
    result = scratch_project.run_hook("session-start.sh")

    assert result.returncode == 0, result.stderr
    assert not (scratch_project.root / LOCAL_SETTINGS_PATH).exists()
    assert (
        f"local settings:  none on 'claude/personal-notes' "
        f"({SETTINGS_PATH_ON_NOTES_BRANCH})" in result.stdout
    )


def test_updates_settings_untouched_since_the_last_sync(
    scratch_project: ScratchProject,
):
    scratch_project.write_notes_branch_file(
        SETTINGS_PATH_ON_NOTES_BRANCH, PERSONAL_SETTINGS
    )
    scratch_project.run_hook("session-start.sh")
    scratch_project.write_notes_branch_file(
        SETTINGS_PATH_ON_NOTES_BRANCH, UPDATED_PERSONAL_SETTINGS
    )

    result = scratch_project.run_hook("session-start.sh")

    assert result.returncode == 0, result.stderr
    assert local_settings_of(scratch_project) == UPDATED_PERSONAL_SETTINGS


def test_keeps_settings_edited_since_the_last_sync(scratch_project: ScratchProject):
    scratch_project.write_notes_branch_file(
        SETTINGS_PATH_ON_NOTES_BRANCH, PERSONAL_SETTINGS
    )
    scratch_project.run_hook("session-start.sh")
    (scratch_project.root / LOCAL_SETTINGS_PATH).write_text(LOCALLY_EDITED_SETTINGS)
    scratch_project.write_notes_branch_file(
        SETTINGS_PATH_ON_NOTES_BRANCH, UPDATED_PERSONAL_SETTINGS
    )

    result = scratch_project.run_hook("session-start.sh")

    assert result.returncode == 0, result.stderr
    assert local_settings_of(scratch_project) == LOCALLY_EDITED_SETTINGS
    assert (
        f"local settings:  kept local edits to {LOCAL_SETTINGS_PATH} - run "
        "save-personal-settings.sh to push them" in result.stdout
    )


def test_keeps_settings_that_were_never_synced(scratch_project: ScratchProject):
    (scratch_project.root / LOCAL_SETTINGS_PATH).write_text(LOCALLY_EDITED_SETTINGS)
    scratch_project.write_notes_branch_file(
        SETTINGS_PATH_ON_NOTES_BRANCH, PERSONAL_SETTINGS
    )

    result = scratch_project.run_hook("session-start.sh")

    assert result.returncode == 0, result.stderr
    assert local_settings_of(scratch_project) == LOCALLY_EDITED_SETTINGS


# %% saving local settings back to the personal-notes branch


def test_saves_local_settings_to_the_branch(scratch_project: ScratchProject):
    (scratch_project.root / LOCAL_SETTINGS_PATH).write_text(PERSONAL_SETTINGS)

    result = scratch_project.run_hook("save-personal-settings.sh")

    assert result.returncode == 0, result.stderr
    assert (
        scratch_project.read_notes_branch_file(SETTINGS_PATH_ON_NOTES_BRANCH)
        == PERSONAL_SETTINGS
    )


def test_saved_settings_are_no_longer_treated_as_local_edits(
    scratch_project: ScratchProject,
):
    (scratch_project.root / LOCAL_SETTINGS_PATH).write_text(LOCALLY_EDITED_SETTINGS)
    scratch_project.run_hook("save-personal-settings.sh")
    scratch_project.write_notes_branch_file(
        SETTINGS_PATH_ON_NOTES_BRANCH, UPDATED_PERSONAL_SETTINGS
    )

    result = scratch_project.run_hook("session-start.sh")

    assert result.returncode == 0, result.stderr
    assert local_settings_of(scratch_project) == UPDATED_PERSONAL_SETTINGS


def test_saving_without_local_settings_fails_with_a_clear_message(
    scratch_project: ScratchProject,
):
    result = scratch_project.run_hook("save-personal-settings.sh")

    assert result.returncode == 1
    assert result.stderr.startswith(
        f"No {LOCAL_SETTINGS_PATH} at the project root "
        f"({scratch_project.root / LOCAL_SETTINGS_PATH}) - nothing to save.\n"
    )
