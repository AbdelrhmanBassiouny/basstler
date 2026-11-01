"""
Integration tests for save-plan.sh's argument validation and CLAUDE.local.md.

marker-block extraction, run against a local `git init --bare` fixture instead of a
real remote - no network access or real personal-notes branch involved.
"""

import shutil
import subprocess
from enum import StrEnum
from pathlib import Path

import pytest
import yaml

from basstler.exit_codes import ManifestToolsExitCode
from basstler.locations import PluginLocation, ProjectLocation
from basstler.plan.item_bootstrap.vocabulary import PlanSavingOption
from basstler.plan.merge import PlanVersion
from basstler.plan.model import PlanDocument
from basstler.plan.model import ManifestKey, PlanManifest
from basstler.shell_configuration import ShellConfigurationFunction

from ..constants.notes import ScratchBranch
from ..constants.paths import DatasetLocation, PersonalNotesPath
from ..fixture_plans import FixturePlanId, ForeignItemId, foreign_reference
from ..plan.concurrent_edits import (
    FIRST_ITEM,
    PLAN_IDENTIFIER,
    SECOND_ITEM,
    blocked,
    deferred,
    read_version,
)
from ..project_declaration import ProjectDeclaration
from ..scratch_repository import PackageSourceFile, ScratchRepository


class DatasetPlan(StrEnum):
    """
    What the dataset's plans are known by.
    """

    IDENTIFIER = "test-plan"
    """
    The ``id`` :attr:`DatasetLocation.PLAN` carries, and so the plan id it is saved
    under.
    """


class ConcurrentWriterVariable(StrEnum):
    """
    The environment :attr:`DatasetLocation.CONCURRENT_WRITER_HOOK` reads.
    """

    CHECKOUT = "CONCURRENT_WRITER_CHECKOUT"
    """
    The other writer's clone of the notes branch.
    """


@pytest.fixture
def save_plan_repository(scratch_repository: ScratchRepository) -> ScratchRepository:
    """
    A scratch repository carrying the real save-plan.sh, resolve-personal-notes-
    config.sh and plan/manifest_tools.py, with a notes branch already published to its
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
        PlanSavingOption.MANIFEST,
        str(manifest_path),
        PlanSavingOption.ROADMAP,
        str(roadmap_path),
    )

    assert result.returncode == 1
    verify_checkout = save_plan_repository.clone_notes_branch(
        save_plan_repository.project_root.parent / "verify-checkout"
    )
    assert not (
        verify_checkout / ProjectLocation.PLANS / DatasetPlan.IDENTIFIER
    ).exists()


def save_depending_on(
    repository: ScratchRepository, dependency_text: str
) -> subprocess.CompletedProcess[str]:
    """
    Publish the fixture's other plan to the notes branch, then save the dataset plan
    with its item depending on *dependency_text*.

    :param repository: A fixture-built scratch repository.
    :param dependency_text: The one entry of the saved item's ``depends_on``.
    :return: The finished hook.
    """
    other_plan_manifest = (
        DatasetLocation.PLANS.value / FixturePlanId.OTHER / PlanDocument.MANIFEST
    )
    repository.update_notes_branch_file(
        ProjectLocation.PLANS / FixturePlanId.OTHER / PlanDocument.MANIFEST,
        other_plan_manifest.read_text(),
    )
    manifest = yaml.safe_load(DatasetLocation.PLAN.read_text())
    manifest[ManifestKey.ITEMS.key][0][ManifestKey.DEPENDS_ON.key] = [dependency_text]
    manifest_path = repository.write(PlanDocument.MANIFEST, yaml.safe_dump(manifest))
    roadmap_path = repository.write(
        PlanDocument.ROADMAP, DatasetLocation.ROADMAP_OF_STANDING_RULES.read_text()
    )
    return run_save_plan(
        repository,
        DatasetPlan.IDENTIFIER,
        PlanSavingOption.MANIFEST,
        str(manifest_path),
        PlanSavingOption.ROADMAP,
        str(roadmap_path),
    )


def test_saves_a_manifest_naming_an_item_of_a_plan_on_the_notes_branch(
    save_plan_repository: ScratchRepository,
):
    result = save_depending_on(
        save_plan_repository, foreign_reference(ForeignItemId.READY)
    )

    assert result.returncode == 0, result.stderr
    assert saved_plan_directory(save_plan_repository, DatasetPlan.IDENTIFIER).exists()


def test_refuses_a_manifest_naming_a_plan_the_notes_branch_lacks(
    save_plan_repository: ScratchRepository,
):
    result = save_depending_on(
        save_plan_repository,
        foreign_reference(ForeignItemId.READY, FixturePlanId.ABSENT),
    )

    assert result.returncode == 1
    assert not saved_plan_directory(
        save_plan_repository, DatasetPlan.IDENTIFIER
    ).exists()


# %% --manifest/--roadmap pairing


def test_manifest_without_roadmap_fails(save_plan_repository: ScratchRepository):
    manifest_path = save_plan_repository.write(
        PlanDocument.MANIFEST, DatasetLocation.PLAN.read_text()
    )
    result = run_save_plan(
        save_plan_repository,
        DatasetPlan.IDENTIFIER,
        PlanSavingOption.MANIFEST,
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
        PlanSavingOption.ROADMAP,
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


# %% the size gate


def save_from_files(
    repository: ScratchRepository, manifest: Path, roadmap: Path
) -> subprocess.CompletedProcess[str]:
    """
    Run save-plan.sh on a manifest and roadmap read from files.

    :return: The finished hook.
    """
    plan_identifier = PlanManifest.from_file(manifest).identifier
    return run_save_plan(
        repository,
        plan_identifier,
        PlanSavingOption.MANIFEST,
        str(manifest),
        PlanSavingOption.ROADMAP,
        str(roadmap),
    )


def saved_plan_directory(repository: ScratchRepository, plan_identifier: str) -> Path:
    """
    :return: The plan's directory in a fresh clone of the notes branch.
    """
    checkout = repository.clone_notes_branch(repository.project_root.parent / "verify")
    return checkout / ProjectLocation.PLANS / plan_identifier


def test_a_save_drops_the_landed_items(save_plan_repository: ScratchRepository):
    result = save_from_files(
        save_plan_repository,
        DatasetLocation.PLAN_WITH_LANDED_ITEMS,
        DatasetLocation.ROADMAP_OF_STANDING_RULES,
    )
    assert result.returncode == 0, result.stderr
    manifest = PlanManifest.from_file(DatasetLocation.PLAN_WITH_LANDED_ITEMS)
    saved = PlanManifest.from_file(
        saved_plan_directory(save_plan_repository, manifest.identifier)
        / PlanDocument.MANIFEST
    )
    assert saved == manifest.without_landed_items()


def test_a_plan_with_every_item_landed_is_removed(
    save_plan_repository: ScratchRepository,
):
    plan_identifier = PlanManifest.from_file(DatasetLocation.PLAN_ALL_LANDED).identifier
    plan_directory = ProjectLocation.PLANS / plan_identifier
    save_plan_repository.update_notes_branch_file(
        plan_directory / PlanDocument.MANIFEST,
        DatasetLocation.PLAN_ALL_LANDED.read_text(),
    )
    save_plan_repository.update_notes_branch_file(
        plan_directory / PlanDocument.ROADMAP,
        DatasetLocation.ROADMAP_OF_STANDING_RULES.read_text(),
    )

    result = save_from_files(
        save_plan_repository,
        DatasetLocation.PLAN_ALL_LANDED,
        DatasetLocation.ROADMAP_OF_STANDING_RULES,
    )

    assert result.returncode == 0, result.stderr
    assert not saved_plan_directory(save_plan_repository, plan_identifier).exists()


def test_a_roadmap_with_a_dated_section_is_refused(
    save_plan_repository: ScratchRepository,
):
    result = save_from_files(
        save_plan_repository,
        DatasetLocation.PLAN_WITH_LANDED_ITEMS,
        DatasetLocation.ROADMAP_WITH_DATED_SECTION,
    )
    assert result.returncode == 1
    assert not saved_plan_directory(
        save_plan_repository,
        PlanManifest.from_file(DatasetLocation.PLAN_WITH_LANDED_ITEMS).identifier,
    ).exists()


# %% saving alongside another writer


def notes_branch_tip(repository: ScratchRepository) -> str:
    """
    :param repository: A fixture-built scratch repository.
    :return: The commit the notes remote's notes branch points at.
    """
    listing = repository.run_git(
        "ls-remote", str(repository.notes_remote_path), ScratchBranch.PERSONAL_NOTES
    )
    return listing.stdout.split()[0]


def plan_path(document: PlanDocument) -> str:
    """
    :return: Where the fixture plan keeps *document* on the notes branch.
    """
    return document.path_within_notes_branch(PLAN_IDENTIFIER)


@pytest.fixture
def plan_read_at(save_plan_repository: ScratchRepository) -> str:
    """
    Publish the fixture plan, as the session then reads it.

    :param save_plan_repository: A fixture-built scratch repository.
    :return: The notes-branch commit the session read the plan at.
    """
    version = read_version()
    save_plan_repository.update_notes_branch_file(
        plan_path(PlanDocument.MANIFEST), version.manifest_text
    )
    save_plan_repository.update_notes_branch_file(
        plan_path(PlanDocument.ROADMAP), version.roadmap_text
    )
    return notes_branch_tip(save_plan_repository)


def save_arguments(
    repository: ScratchRepository, version: PlanVersion, *options: str
) -> tuple[str, ...]:
    """
    Write *version* of the fixture plan to files for save-plan.sh to read.

    :param repository: A fixture-built scratch repository.
    :param version: The plan as the session wrote it.
    :param options: Further options to pass.
    :return: The arguments that save it.
    """
    directory = repository.project_root / "session-plan"
    version.write(directory)
    return (
        PLAN_IDENTIFIER,
        PlanSavingOption.MANIFEST,
        str(directory / PlanDocument.MANIFEST),
        PlanSavingOption.ROADMAP,
        str(directory / PlanDocument.ROADMAP),
        *options,
    )


def save_version(
    repository: ScratchRepository, version: PlanVersion, *options: str
) -> subprocess.CompletedProcess[str]:
    """
    Save *version* of the fixture plan with save-plan.sh.

    :param repository: A fixture-built scratch repository.
    :param version: The plan as the session wrote it.
    :param options: Further options to pass.
    :return: The finished hook.
    """
    return run_save_plan(repository, *save_arguments(repository, version, *options))


def published_version(repository: ScratchRepository) -> PlanVersion:
    """
    :return: The fixture plan as the notes remote now holds it.
    """
    return PlanVersion.from_directory(saved_plan_directory(repository, PLAN_IDENTIFIER))


def prepare_concurrent_writer(
    repository: ScratchRepository, writes: int, version: PlanVersion | None = None
) -> str:
    """
    Install :attr:`DatasetLocation.CONCURRENT_WRITER_HOOK` as the repository's pre-push
    hook, with a clone of the notes branch for it to push from.

    :param repository: A fixture-built scratch repository.
    :param writes: How many pushes the other writer gets ahead of.
    :param version: A manifest the other writer has committed, unpushed, before its
        first write; ``None`` for writes that change nothing.
    :return: The clone's path, for the run's environment.
    """
    writer = repository.clone_notes_branch(repository.project_root.parent / "writer")
    for setting, value in (
        ("user.name", "Another Writer"),
        ("user.email", "another-writer@example.invalid"),
        ("commit.gpgsign", "false"),
    ):
        repository.run_git("config", setting, value, cwd=writer)
    if version is not None:
        (writer / plan_path(PlanDocument.MANIFEST)).write_text(version.manifest_text)
        repository.run_git("commit", "--quiet", "--all", "-m", "edit", cwd=writer)
    (writer / ".git" / "writes-remaining").write_text(f"{writes}\n")
    hook = repository.project_root / ".git" / "hooks" / "pre-push"
    hook.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(DatasetLocation.CONCURRENT_WRITER_HOOK, hook)
    return str(writer)


def test_a_save_keeps_another_writer_s_edit_to_another_item(
    save_plan_repository: ScratchRepository, plan_read_at: str
):
    latest = deferred(read_version(), SECOND_ITEM)
    save_plan_repository.update_notes_branch_file(
        plan_path(PlanDocument.MANIFEST), latest.manifest_text
    )

    result = save_version(
        save_plan_repository,
        blocked(read_version(), FIRST_ITEM),
        PlanSavingOption.READ_AT,
        plan_read_at,
    )

    assert result.returncode == 0, result.stderr
    assert published_version(save_plan_repository) == blocked(latest, FIRST_ITEM)


def test_a_save_refuses_an_item_another_writer_changed_since_the_read(
    save_plan_repository: ScratchRepository, plan_read_at: str
):
    latest = deferred(read_version(), FIRST_ITEM)
    save_plan_repository.update_notes_branch_file(
        plan_path(PlanDocument.MANIFEST), latest.manifest_text
    )

    result = save_version(
        save_plan_repository,
        blocked(read_version(), FIRST_ITEM),
        PlanSavingOption.READ_AT,
        plan_read_at,
    )

    assert result.returncode == ManifestToolsExitCode.CHANGED_SINCE_READ
    assert published_version(save_plan_repository) == latest


def test_a_rejected_push_is_retried_onto_the_other_writer_s_save(
    save_plan_repository: ScratchRepository, plan_read_at: str
):
    latest = deferred(read_version(), SECOND_ITEM)
    writer = prepare_concurrent_writer(save_plan_repository, writes=1, version=latest)

    result = save_plan_repository.run_hook_script(
        PluginLocation.PLAN_SAVING_SCRIPT.name,
        *save_arguments(
            save_plan_repository,
            blocked(read_version(), FIRST_ITEM),
            PlanSavingOption.READ_AT,
            plan_read_at,
        ),
        **{ConcurrentWriterVariable.CHECKOUT: writer},
    )

    assert result.returncode == 0, result.stderr
    assert published_version(save_plan_repository) == blocked(latest, FIRST_ITEM)


def test_a_save_without_its_read_point_still_retries_a_rejected_push(
    save_plan_repository: ScratchRepository, plan_read_at: str
):
    writer = prepare_concurrent_writer(save_plan_repository, writes=1)
    session = blocked(read_version(), FIRST_ITEM)

    result = save_plan_repository.run_hook_script(
        PluginLocation.PLAN_SAVING_SCRIPT.name,
        *save_arguments(save_plan_repository, session),
        **{ConcurrentWriterVariable.CHECKOUT: writer},
    )

    assert result.returncode == 0, result.stderr
    assert published_version(save_plan_repository) == session


def test_a_save_stops_after_its_attempts(
    save_plan_repository: ScratchRepository, plan_read_at: str
):
    attempts = 2
    writer = prepare_concurrent_writer(save_plan_repository, writes=attempts)

    result = save_plan_repository.run_hook_script(
        PluginLocation.PLAN_SAVING_SCRIPT.name,
        *save_arguments(
            save_plan_repository,
            blocked(read_version(), FIRST_ITEM),
            PlanSavingOption.READ_AT,
            plan_read_at,
            PlanSavingOption.ATTEMPTS,
            str(attempts),
        ),
        **{ConcurrentWriterVariable.CHECKOUT: writer},
    )

    assert result.returncode == 1
    assert published_version(save_plan_repository) == read_version()
