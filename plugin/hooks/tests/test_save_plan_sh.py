"""
Integration tests for save-plan.sh's argument validation and CLAUDE.local.md.

marker-block extraction, run against a local `git init --bare` fixture instead of a
real remote - no network access or real personal-notes branch involved.
"""

from pathlib import Path

from conftest import ScratchProject

FIXTURES_DIRECTORY = Path(__file__).parent / "fixtures"

PLAN_MANIFEST = (FIXTURES_DIRECTORY / "plan.yaml").read_text()
PLAN_ROADMAP = (FIXTURES_DIRECTORY / "roadmap.md").read_text()

PLAN_DIRECTORY = ".claude/personal/plans/test-plan"
BRANCH_INDEX_PATH = ".claude/personal/plans/_generated/branch-index.tsv"


# %% --manifest/--roadmap pairing


def test_manifest_without_roadmap_fails(scratch_project: ScratchProject):
    manifest_path = scratch_project.root / "plan.yaml"
    manifest_path.write_text(PLAN_MANIFEST)
    result = scratch_project.run_hook(
        "save-plan.sh", "test-plan", "--manifest", str(manifest_path)
    )
    assert result.returncode == 1
    assert result.stderr == (
        "--manifest was given without --roadmap - they must be passed together.\n"
    )


def test_roadmap_without_manifest_fails(scratch_project: ScratchProject):
    roadmap_path = scratch_project.root / "roadmap.md"
    roadmap_path.write_text(PLAN_ROADMAP)
    result = scratch_project.run_hook(
        "save-plan.sh", "test-plan", "--roadmap", str(roadmap_path)
    )
    assert result.returncode == 1
    assert result.stderr == (
        "--roadmap was given without --manifest - they must be passed together.\n"
    )


# %% CLAUDE.local.md marker-block extraction


def test_saves_the_manifest_and_roadmap_extracted_from_claude_local_md_markers(
    scratch_project: ScratchProject,
):
    claude_local_md = scratch_project.root / "CLAUDE.local.md"
    claude_local_md.write_text(
        "<!-- BEGIN-PLAN-MANIFEST: test-plan -->\n"
        f"{PLAN_MANIFEST}"
        "<!-- END-PLAN-MANIFEST -->\n"
        "<!-- BEGIN-PLAN-ROADMAP: test-plan -->\n"
        f"{PLAN_ROADMAP}"
        "<!-- END-PLAN-ROADMAP -->\n"
    )

    result = scratch_project.run_hook("save-plan.sh", "test-plan")
    assert result.returncode == 0, result.stderr
    assert "Saved plan 'test-plan'" in result.stdout
    assert str(scratch_project.notes_repository) in result.stdout

    assert (
        scratch_project.read_notes_branch_file(f"{PLAN_DIRECTORY}/plan.yaml")
        == PLAN_MANIFEST
    )
    assert (
        scratch_project.read_notes_branch_file(f"{PLAN_DIRECTORY}/roadmap.md")
        == PLAN_ROADMAP
    )
    assert (
        scratch_project.read_notes_branch_file(BRANCH_INDEX_PATH)
        == "item-a-branch\ttest-plan\n"
    )


def test_missing_marker_pair_fails_with_a_clear_message(
    scratch_project: ScratchProject,
):
    (scratch_project.root / "CLAUDE.local.md").write_text("no markers here\n")
    result = scratch_project.run_hook("save-plan.sh", "test-plan")
    assert result.returncode == 1
    assert result.stderr.startswith(
        "CLAUDE.local.md has no plan-manifest/plan-roadmap section to extract.\n"
    )
