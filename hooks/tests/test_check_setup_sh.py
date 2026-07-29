"""
Integration tests for check-setup.sh's per-check reporting and exit code.

Run against a scratch project root with a local ``git init --bare`` fixture standing
in for the personal-notes remote - no network access or real personal-notes branch
involved.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

import plan_manifest_tools

HOOKS_SOURCE_DIRECTORY = Path(plan_manifest_tools.__file__).parent

# The files check-setup.sh's `tooling_files` check requires, relative to the
# project root. Kept as literals rather than sourced from
# resolve-personal-notes-config.sh so a rename that breaks the check has to be
# made deliberately in both places, instead of the test silently following
# along and asserting nothing.
TOOLING_FILES = (
    ".claude/skills/plan-dashboard/build_dashboard.py",
    ".claude/skills/plan-dashboard/refresh_dashboard.sh",
    ".claude/skills/plan-dashboard/requirements.txt",
    ".claude/skills/plan-dashboard/plan-schema.md",
)

NOTES_PATH = ".claude/personal/cram-notes.md"
NOTES_BRANCH = "claude/personal-notes"


def _run_git(*arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *arguments], cwd=cwd, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    return result


class SetupReport:
    """
    One parsed run of check-setup.sh: its rows, keyed by check name, and its exit code.

    Wraps the raw process result so tests assert against named checks rather than re-
    splitting tab-separated text at every call site.
    """

    def __init__(self, process: subprocess.CompletedProcess[str]) -> None:
        self.exit_code = process.returncode
        """
        The script's exit code: 0 when nothing needs setup, 1 otherwise.
        """
        self.rows: dict[str, tuple[str, str]] = {}
        """
        Every reported check, mapped to its ``(status, detail)`` pair.
        """
        for line in process.stdout.splitlines():
            check, status, detail = line.split("\t")
            self.rows[check] = (status, detail)

    def status_of(self, check: str) -> str:
        """
        The status reported for *check*.

        :param check: The check name, as printed in the row's first column.
        :return: One of ``ok``, ``needs-setup`` or ``info``.
        """
        return self.rows[check][0]

    def detail_of(self, check: str) -> str:
        """
        The human-readable detail reported for *check*.

        :param check: The check name, as printed in the row's first column.
        :return: The row's third column.
        """
        return self.rows[check][1]


@pytest.fixture
def scratch_repo(tmp_path: Path) -> Path:
    """
    Build a fully set-up scratch project root: the real check-setup.sh and resolve-
    personal-notes-config.sh, placeholder tooling files, a registered SessionStart hook,
    a gitignored CLAUDE.local.md, and a local ``git init --bare`` fixture carrying a
    personal-notes branch with a notes file on it.

    Individual tests break exactly one of those conditions to assert the matching check
    reports it.

    :param tmp_path: pytest's per-test temporary directory.
    :return: The scratch project root, checked out on a throwaway branch.
    """
    project_root = tmp_path / "project"
    hooks_directory = project_root / ".claude" / "hooks"
    hooks_directory.mkdir(parents=True)
    for script in ("resolve-personal-notes-config.sh", "check-setup.sh"):
        shutil.copy(HOOKS_SOURCE_DIRECTORY / script, hooks_directory / script)

    for tooling_file in TOOLING_FILES:
        destination = project_root / tooling_file
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("placeholder\n")
    # The dependency check reads this file rather than a hardcoded list, so a
    # requirement that is certainly installed keeps the fixture's baseline green.
    (
        project_root / ".claude" / "skills" / "plan-dashboard" / "requirements.txt"
    ).write_text("pytest>=1\n")

    (project_root / ".claude" / "settings.json").write_text(
        '{"hooks": {"SessionStart": [{"hooks": [{"type": "command",'
        ' "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/session-start.sh"}]}]}}\n'
    )
    (project_root / ".gitignore").write_text("CLAUDE.local.md\n")
    (project_root / "CLAUDE.local.md").write_text("notes\n")

    _run_git("init", "--quiet", cwd=project_root)
    _run_git("config", "user.name", "Scratch Repo", cwd=project_root)
    _run_git("config", "user.email", "scratch-repo@example.com", cwd=project_root)
    _run_git("add", ".", cwd=project_root)
    _run_git("commit", "--quiet", "-m", "initial commit", cwd=project_root)

    bare_repository_path = tmp_path / "personal-notes.git"
    _run_git("init", "--quiet", "--bare", str(bare_repository_path), cwd=tmp_path)

    _run_git("checkout", "--quiet", "-b", NOTES_BRANCH, cwd=project_root)
    notes_file = project_root / NOTES_PATH
    notes_file.parent.mkdir(parents=True)
    notes_file.write_text("my notes\n")
    _run_git("add", NOTES_PATH, cwd=project_root)
    _run_git("commit", "--quiet", "-m", "bootstrap personal-notes", cwd=project_root)
    _run_git("push", str(bare_repository_path), NOTES_BRANCH, cwd=project_root)
    _run_git("checkout", "--quiet", "-b", "some-work-branch", cwd=project_root)
    _run_git("rm", "-r", "--quiet", "--cached", NOTES_PATH, cwd=project_root)
    shutil.rmtree(project_root / ".claude" / "personal")
    _run_git(
        "commit", "--quiet", "-m", "drop notes from the work branch", cwd=project_root
    )

    _run_git(
        "config",
        "claude.personalNotesRemote",
        str(bare_repository_path),
        cwd=project_root,
    )
    return project_root


def run_check_setup(scratch_repo: Path, **environment_overrides: str) -> SetupReport:
    """
    Run the scratch layout's check-setup.sh and parse its report.

    Every ``CLAUDE_PERSONAL_NOTES_*`` variable is stripped from the inherited
    environment first, so a value that happens to be set in whoever's shell is running
    the tests can never change what they assert.

    :param scratch_repo: A fixture-built scratch project root.
    :param environment_overrides: Personal-notes environment variables to set for this
        run, for the tests that exercise resolution from the environment.
    :return: The parsed report.
    """
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("CLAUDE_PERSONAL_NOTES_")
    }
    environment.update(environment_overrides)
    return SetupReport(
        subprocess.run(
            ["bash", str(scratch_repo / ".claude" / "hooks" / "check-setup.sh")],
            cwd=scratch_repo,
            capture_output=True,
            text=True,
            env=environment,
        )
    )


# %% the already-set-up fast path


def test_reports_no_work_needed_when_everything_is_in_place(scratch_repo: Path):
    report = run_check_setup(scratch_repo)
    assert report.exit_code == 0
    needing_setup = [
        check for check in report.rows if report.status_of(check) == "needs-setup"
    ]
    assert needing_setup == []


def test_reports_every_check_it_documents(scratch_repo: Path):
    report = run_check_setup(scratch_repo)
    assert set(report.rows) == {
        "tooling_files",
        "session_start_hook",
        "claude_local_md_ignored",
        "notes_remote",
        "notes_remote_url",
        "notes_branch_name",
        "notes_path",
        "notes_branch",
        "notes_file",
        "dashboard_dependencies",
        "claude_local_md",
    }


# %% the personal-notes branch


def test_reports_a_missing_notes_branch_and_the_remotes_it_tried(
    scratch_repo: Path, tmp_path: Path
):
    empty_remote = tmp_path / "empty-remote.git"
    _run_git("init", "--quiet", "--bare", str(empty_remote), cwd=tmp_path)
    _run_git(
        "config", "claude.personalNotesRemote", str(empty_remote), cwd=scratch_repo
    )

    report = run_check_setup(scratch_repo)
    assert report.exit_code == 1
    assert report.status_of("notes_branch") == "needs-setup"
    assert str(empty_remote) in report.detail_of("notes_branch")


def test_does_not_check_for_the_notes_file_when_its_branch_is_missing(
    scratch_repo: Path, tmp_path: Path
):
    empty_remote = tmp_path / "empty-remote.git"
    _run_git("init", "--quiet", "--bare", str(empty_remote), cwd=tmp_path)
    _run_git(
        "config", "claude.personalNotesRemote", str(empty_remote), cwd=scratch_repo
    )

    report = run_check_setup(scratch_repo)
    assert report.status_of("notes_file") == "needs-setup"
    assert report.detail_of("notes_file") == (
        "not checked - the branch that would hold it doesn't exist yet"
    )


def test_reports_a_notes_branch_that_exists_but_holds_no_notes_file(
    scratch_repo: Path, tmp_path: Path
):
    _run_git(
        "config",
        "claude.personalNotesPath",
        ".claude/personal/some-other-notes.md",
        cwd=scratch_repo,
    )

    report = run_check_setup(scratch_repo)
    assert report.exit_code == 1
    assert report.status_of("notes_branch") == "ok"
    assert report.status_of("notes_file") == "needs-setup"
    assert ".claude/personal/some-other-notes.md" in report.detail_of("notes_file")


# %% how each setting was resolved


def test_reports_which_source_each_resolved_setting_came_from(scratch_repo: Path):
    report = run_check_setup(scratch_repo)
    assert "from git config claude.personalNotesRemote" in report.detail_of(
        "notes_remote"
    )
    assert report.detail_of("notes_branch_name") == (
        f"{NOTES_BRANCH} (from built-in default)"
    )
    assert report.detail_of("notes_path") == f"{NOTES_PATH} (from built-in default)"


def test_reports_a_setting_resolved_from_the_environment(scratch_repo: Path):
    report = run_check_setup(
        scratch_repo,
        CLAUDE_PERSONAL_NOTES_PATH=".claude/personal/from-the-environment.md",
    )
    assert report.detail_of("notes_path") == (
        ".claude/personal/from-the-environment.md"
        " (from environment variable CLAUDE_PERSONAL_NOTES_PATH)"
    )


# %% the tooling this checkout is expected to carry


def test_reports_which_tooling_files_this_checkout_is_missing(scratch_repo: Path):
    (scratch_repo / ".claude" / "skills" / "plan-dashboard" / "plan-schema.md").unlink()

    report = run_check_setup(scratch_repo)
    assert report.exit_code == 1
    assert report.status_of("tooling_files") == "needs-setup"
    assert ".claude/skills/plan-dashboard/plan-schema.md" in report.detail_of(
        "tooling_files"
    )
    assert ".claude/skills/plan-dashboard/build_dashboard.py" not in report.detail_of(
        "tooling_files"
    )


def test_reports_a_session_start_hook_that_is_not_registered(scratch_repo: Path):
    (scratch_repo / ".claude" / "settings.json").write_text("{}\n")

    report = run_check_setup(scratch_repo)
    assert report.exit_code == 1
    assert report.status_of("session_start_hook") == "needs-setup"


def test_reports_a_claude_local_md_that_is_not_gitignored(scratch_repo: Path):
    (scratch_repo / ".gitignore").write_text("something-else\n")

    report = run_check_setup(scratch_repo)
    assert report.exit_code == 1
    assert report.status_of("claude_local_md_ignored") == "needs-setup"


# %% plan-dashboard dependencies


def test_reports_dashboard_requirements_that_are_not_installed(scratch_repo: Path):
    (
        scratch_repo / ".claude" / "skills" / "plan-dashboard" / "requirements.txt"
    ).write_text("pytest>=1\nno-such-distribution-exists>=2  # a comment\n")

    report = run_check_setup(scratch_repo)
    assert report.exit_code == 1
    assert report.status_of("dashboard_dependencies") == "needs-setup"
    assert "no-such-distribution-exists" in report.detail_of("dashboard_dependencies")
    assert "pytest" not in report.detail_of("dashboard_dependencies")


# %% the outcome of it all working


def test_reports_a_claude_local_md_that_was_never_written(scratch_repo: Path):
    (scratch_repo / "CLAUDE.local.md").unlink()

    report = run_check_setup(scratch_repo)
    assert report.exit_code == 1
    assert report.status_of("claude_local_md") == "needs-setup"
