"""
Integration tests for save-plan.sh's argument validation and CLAUDE.local.md.

marker-block extraction, run against a local `git init --bare` fixture instead of a
real remote - no network access or real personal-notes branch involved.
"""

import subprocess
from pathlib import Path

import pytest

from basstler.locations import PluginLocation, ProjectLocation
from basstler.plan_item_bootstrap import PlanDocument
from basstler.shell_configuration import ShellConfigurationFunction

from .constants import DatasetLocation, DatasetPlan, PersonalNotesPath, SavePlanOption
from .project_declaration import ProjectDeclaration
from .scratch_repository import PackageSourceFile, ScratchRepository


@pytest.fixture
def save_plan_repository(scratch_repository: ScratchRepository) -> ScratchRepository:
    """
    A scratch repository carrying the real save-plan.sh, resolve-personal-notes-
    config.sh and plan_manifest_tools.py, with a notes branch already published to its
    notes remote.

    :param scratch_repository: The initialized scratch repository and notes remote.
    :return: The same repository, ready to run save-plan.sh against.
    """
    scratch_repository.install_hook_scripts(
        PluginLocation.PERSONAL_NOTES_CONFIGURATION_SCRIPT.name,
        PluginLocation.PLAN_SAVING_SCRIPT.name,
    )
    scratch_repository.install_package()
    scratch_repository.write("README.md", "scratch repo\n")
    scratch_repository.commit_everything("initial commit")
    scratch_repository.publish_notes_branch(
        {ProjectLocation.PERSONAL_NOTES / "placeholder.md": "notes\n"}
    )
    scratch_repository.resolve_notes_remote_to()
    return scratch_repository


def run_save_plan(
    repository: ScratchRepository, *arguments: str
) -> subprocess.CompletedProcess[str]:
    """
    Run the scratch layout's save-plan.sh with *arguments*.

    :param repository: A fixture-built scratch repository.
    :param arguments: CLI arguments to pass to save-plan.sh.
    :return: The finished subprocess.
    """
    return repository.run_hook_script(
        PluginLocation.PLAN_SAVING_SCRIPT.name, *arguments
    )


# %% the dependencies it needs before it can read a manifest


UNINSTALLABLE_REQUIREMENT = "basstler-no-such-distribution>=1"
"""
A distribution nothing can have installed, so the refusal cannot pass by accident.
"""


def declaration_file(repository: ScratchRepository) -> Path:
    """
    :param repository: A fixture-built scratch repository.
    :return: Where its scratch checkout declares the package's requirements.
    """
    return repository.checkout_root / PackageSourceFile.METADATA


def test_refuses_when_a_declared_dependency_is_not_installed(
    save_plan_repository: ScratchRepository,
):
    """
    The declaration answers this rather than an import of one name, so the refusal names
    everything the tooling is short of and what to run - not a traceback from whichever
    module happens to be imported first.
    """
    declaration_file(save_plan_repository).write_text(
        ProjectDeclaration(
            name=ProjectDeclaration.of_this_package().name,
            dependencies=(UNINSTALLABLE_REQUIREMENT,),
        ).as_toml(),
    )

    result = run_save_plan(save_plan_repository, DatasetPlan.IDENTIFIER)

    assert result.returncode == 1
    assert UNINSTALLABLE_REQUIREMENT in result.stderr
    assert (
        f"install '{save_plan_repository.configuration_output(ShellConfigurationFunction.BASSTLER_PACKAGE_SOURCE).strip()}'"
        in result.stderr
    )


def test_refuses_when_the_declaration_cannot_be_read(
    save_plan_repository: ScratchRepository,
):
    """
    A declaration the lookup cannot parse says nothing about what is installed, so it
    stops the save rather than reading as nothing missing.
    """
    declaration_file(save_plan_repository).write_text("this is not toml\n")

    result = run_save_plan(save_plan_repository, DatasetPlan.IDENTIFIER)

    assert result.returncode == 1
    assert str(declaration_file(save_plan_repository)) in result.stderr


# %% the manifest it saves


def test_refuses_a_manifest_the_dashboard_would_reject(
    save_plan_repository: ScratchRepository,
):
    """
    Nothing reaches the notes branch that the dashboard could not then be built from.
    """
    manifest_path = save_plan_repository.write(
        PlanDocument.MANIFEST, DatasetLocation.PLAN_WITH_UNKNOWN_STATUS.read_text()
    )
    roadmap_path = save_plan_repository.write(
        PlanDocument.ROADMAP, DatasetLocation.ROADMAP.read_text()
    )

    result = run_save_plan(
        save_plan_repository,
        DatasetPlan.IDENTIFIER,
        SavePlanOption.MANIFEST,
        str(manifest_path),
        SavePlanOption.ROADMAP,
        str(roadmap_path),
    )

    assert result.returncode == 1
    verify_checkout = save_plan_repository.clone_notes_branch(
        save_plan_repository.project_root.parent / "verify-checkout"
    )
    assert not (
        verify_checkout / ProjectLocation.PLANS / DatasetPlan.IDENTIFIER
    ).exists()


# %% --manifest/--roadmap pairing


def test_manifest_without_roadmap_fails(save_plan_repository: ScratchRepository):
    manifest_path = save_plan_repository.write(
        PlanDocument.MANIFEST, DatasetLocation.PLAN.read_text()
    )
    result = run_save_plan(
        save_plan_repository,
        DatasetPlan.IDENTIFIER,
        SavePlanOption.MANIFEST,
        str(manifest_path),
    )
    assert result.returncode == 1
    assert result.stderr == (
        "--manifest was given without --roadmap - they must be passed together.\n"
    )


def test_roadmap_without_manifest_fails(save_plan_repository: ScratchRepository):
    roadmap_path = save_plan_repository.write(
        PlanDocument.ROADMAP, DatasetLocation.ROADMAP.read_text()
    )
    result = run_save_plan(
        save_plan_repository,
        DatasetPlan.IDENTIFIER,
        SavePlanOption.ROADMAP,
        str(roadmap_path),
    )
    assert result.returncode == 1
    assert result.stderr == (
        "--roadmap was given without --manifest - they must be passed together.\n"
    )


# %% CLAUDE.local.md marker-block extraction


def test_saves_the_manifest_and_roadmap_extracted_from_claude_local_md_markers(
    save_plan_repository: ScratchRepository,
):
    save_plan_repository.write(
        PersonalNotesPath.LOCAL_INSTRUCTIONS.value,
        f"<!-- BEGIN-PLAN-MANIFEST: {DatasetPlan.IDENTIFIER} -->\n"
        f"{DatasetLocation.PLAN.read_text()}"
        "<!-- END-PLAN-MANIFEST -->\n"
        f"<!-- BEGIN-PLAN-ROADMAP: {DatasetPlan.IDENTIFIER} -->\n"
        f"{DatasetLocation.ROADMAP.read_text()}"
        "<!-- END-PLAN-ROADMAP -->\n",
    )

    result = run_save_plan(save_plan_repository, DatasetPlan.IDENTIFIER)
    assert result.returncode == 0, result.stderr
    assert f"Saved plan '{DatasetPlan.IDENTIFIER}'" in result.stdout
    assert str(save_plan_repository.notes_remote_path) in result.stdout

    verify_checkout = save_plan_repository.clone_notes_branch(
        save_plan_repository.project_root.parent / "verify-checkout"
    )
    plan_directory = verify_checkout / ProjectLocation.PLANS / DatasetPlan.IDENTIFIER
    saved_manifest = (plan_directory / PlanDocument.MANIFEST).read_text()
    saved_roadmap = (plan_directory / PlanDocument.ROADMAP).read_text()
    assert saved_manifest == DatasetLocation.PLAN.read_text()
    assert saved_roadmap == DatasetLocation.ROADMAP.read_text()

    branch_index = (verify_checkout / PersonalNotesPath.BRANCH_INDEX).read_text()
    assert branch_index == f"item-a-branch\t{DatasetPlan.IDENTIFIER}\n"


def test_missing_marker_pair_fails_with_a_clear_message(
    save_plan_repository: ScratchRepository,
):
    save_plan_repository.write(
        PersonalNotesPath.LOCAL_INSTRUCTIONS.value, "no markers here\n"
    )
    result = run_save_plan(save_plan_repository, DatasetPlan.IDENTIFIER)
    assert result.returncode == 1
    assert result.stderr.startswith(
        "CLAUDE.local.md has no plan-manifest/plan-roadmap section to extract.\n"
    )
