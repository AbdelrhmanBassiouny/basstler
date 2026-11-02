"""
Tests for plan/manifest_tools.py: reading a plan.yaml's id, validating it and
regenerating the branch->plan-id reverse index, used by save-plan.sh.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import yaml

import basstler.plan.manifest_tools

from basstler.exceptions import PlanValidationError
from basstler.plan.validation import PlanValidator
from basstler.plan.merge import PlanVersion
from basstler.plan.model import PlanDocument
from basstler.plan.model import (
    ItemNotTrackedError,
    ItemStatus,
    ItemSummaryKey,
    ManifestKey,
)
from basstler.plan.manifest_tools import (
    BranchIndex,
    ManifestToolsCommand,
    ManifestToolsExitCode,
    ManifestToolsOption,
    PlanManifest,
    YamlBooleanCoercionError,
    main,
)

from ..constants.paths import DatasetLocation
from ..fixture_plans import FixturePlanId, ForeignItemId, foreign_reference
from ..manifest_builders import manifest_item, minimal_plan
from ..plan_dataset import LandedItemsPlan
from .concurrent_edits import (
    FIRST_ITEM,
    SECOND_ITEM,
    blocked,
    deferred,
    read_version,
)

SCRIPT_NAME = Path(basstler.plan.manifest_tools.__file__).name
"""
This script's own filename, read from the module rather than spelled again here.
"""


def write_manifest(
    directory: Path, plan_id: str, name: str = PlanDocument.MANIFEST
) -> Path:
    """
    Write a minimal plan.yaml with just an ``id`` field.

    :param directory: Where to write the manifest.
    :param plan_id: The manifest's ``id`` field, written verbatim (unquoted) - callers
        wanting a quoted value should write the file themselves instead.
    :param name: The manifest's filename.
    :return: The written file's path.
    """
    manifest_path = directory / name
    manifest_path.write_text(f"id: {plan_id}\n")
    return manifest_path


# %% PlanManifest.identifier


def test_reads_the_id_field(tmp_path):
    manifest_path = write_manifest(tmp_path, "rdr-refactor")
    assert PlanManifest(manifest_path).identifier == "rdr-refactor"


def test_defaults_to_empty_string_when_id_is_missing(tmp_path):
    manifest_path = tmp_path / PlanDocument.MANIFEST
    manifest_path.write_text("title: No id here\n")
    assert PlanManifest(manifest_path).identifier == ""


def test_raises_when_id_is_coerced_to_a_boolean(tmp_path):
    manifest_path = write_manifest(tmp_path, "no")
    with pytest.raises(YamlBooleanCoercionError, match="'id'"):
        PlanManifest(manifest_path).identifier


# %% BranchIndex.render


def _write_plan(plans_directory: Path, plan_id: str, items_yaml: str) -> None:
    plan_directory = plans_directory / plan_id
    plan_directory.mkdir(parents=True)
    (plan_directory / PlanDocument.MANIFEST).write_text(
        f"id: {plan_id}\nitems:\n{items_yaml}"
    )


def test_indexes_every_item_branch(tmp_path):
    plans_directory = tmp_path / "plans"
    _write_plan(
        plans_directory,
        "plan-a",
        "  - branch: branch-1\n  - branch: branch-2\n",
    )
    content = BranchIndex(tmp_path, Path("plans"), PlanDocument.MANIFEST).render()
    assert content == "branch-1\tplan-a\nbranch-2\tplan-a\n"


def test_skips_items_with_no_branch(tmp_path):
    plans_directory = tmp_path / "plans"
    _write_plan(plans_directory, "plan-a", "  - title: no branch here\n")
    assert BranchIndex(tmp_path, Path("plans"), PlanDocument.MANIFEST).render() == ""


def test_empty_when_no_plans_exist(tmp_path):
    (tmp_path / "plans").mkdir()
    assert BranchIndex(tmp_path, Path("plans"), PlanDocument.MANIFEST).render() == ""


def test_first_plan_wins_on_a_duplicate_branch(tmp_path):
    plans_directory = tmp_path / "plans"
    _write_plan(plans_directory, "plan-a", "  - branch: shared\n")
    _write_plan(plans_directory, "plan-b", "  - branch: shared\n")
    content = BranchIndex(tmp_path, Path("plans"), PlanDocument.MANIFEST).render()
    # plans are scanned in sorted glob order, so plan-a wins over plan-b.
    assert content == "shared\tplan-a\n"


def test_warns_on_stderr_when_a_duplicate_branch_is_dropped(tmp_path, capsys):
    plans_directory = tmp_path / "plans"
    _write_plan(plans_directory, "plan-a", "  - branch: shared\n")
    _write_plan(plans_directory, "plan-b", "  - branch: shared\n")
    BranchIndex(tmp_path, Path("plans"), PlanDocument.MANIFEST).render()
    duplicate_manifest_path = plans_directory / "plan-b" / PlanDocument.MANIFEST
    assert capsys.readouterr().err == (
        f"plan/manifest_tools.py: duplicate branch 'shared' in "
        f"{duplicate_manifest_path} - keeping the first plan it was seen "
        "under, dropping this one.\n"
    )


def test_raises_when_plan_id_is_coerced_to_a_boolean(tmp_path):
    plans_directory = tmp_path / "plans"
    _write_plan(plans_directory, "no", "  - branch: branch-1\n")
    with pytest.raises(YamlBooleanCoercionError, match="'id'"):
        BranchIndex(tmp_path, Path("plans"), PlanDocument.MANIFEST).render()


def test_raises_when_a_branch_is_coerced_to_a_boolean(tmp_path):
    plans_directory = tmp_path / "plans"
    _write_plan(plans_directory, "plan-a", "  - branch: no\n")
    with pytest.raises(YamlBooleanCoercionError, match="'branch'"):
        BranchIndex(tmp_path, Path("plans"), PlanDocument.MANIFEST).render()


# %% main - subcommand dispatch


def test_main_dispatches_read_id(tmp_path, monkeypatch, capsys):
    manifest_path = write_manifest(tmp_path, "rdr-refactor")
    monkeypatch.setattr(
        sys,
        "argv",
        [SCRIPT_NAME, ManifestToolsCommand.READ_ID, str(manifest_path)],
    )
    exit_code = main()
    assert exit_code == ManifestToolsExitCode.SUCCESS
    assert capsys.readouterr().out.strip() == "rdr-refactor"


def test_main_dispatches_regenerate_branch_index(tmp_path, monkeypatch):
    plans_directory = tmp_path / "plans"
    _write_plan(plans_directory, "plan-a", "  - branch: branch-1\n")
    output_path = tmp_path / "branch-index.tsv"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            SCRIPT_NAME,
            ManifestToolsCommand.REGENERATE_BRANCH_INDEX,
            ManifestToolsOption.SCRATCH_DIRECTORY,
            str(tmp_path),
            ManifestToolsOption.PLANS_DIRECTORY,
            "plans",
            ManifestToolsOption.MANIFEST_FILENAME,
            PlanDocument.MANIFEST,
            ManifestToolsOption.OUTPUT,
            str(output_path),
        ],
    )
    exit_code = main()
    assert exit_code == ManifestToolsExitCode.SUCCESS
    assert output_path.read_text() == "branch-1\tplan-a\n"


# %% main - validating a manifest before it is saved


def run_validate(monkeypatch, manifest_path: Path) -> int:
    """
    :param monkeypatch: pytest's monkeypatch fixture.
    :param manifest_path: The manifest to validate.
    :return: The exit status the command line returns.
    """
    monkeypatch.setattr(
        sys,
        "argv",
        [SCRIPT_NAME, ManifestToolsCommand.VALIDATE, str(manifest_path)],
    )
    return main()


def test_validate_accepts_a_manifest_the_dashboard_builds(monkeypatch):
    assert run_validate(monkeypatch, DatasetLocation.PLAN.value) == (
        ManifestToolsExitCode.SUCCESS
    )


def test_validate_refuses_a_manifest_the_dashboard_rejects_and_says_why(
    monkeypatch, capsys
):
    """
    A manifest saved past the dashboard's own validation is one no dashboard can be
    built from, so the save refuses it with the same problems the build would report.
    """
    with pytest.raises(PlanValidationError) as expected:
        PlanValidator(
            yaml.safe_load(DatasetLocation.PLAN_WITH_UNKNOWN_STATUS.read_text())
        ).validate()

    status = run_validate(monkeypatch, DatasetLocation.PLAN_WITH_UNKNOWN_STATUS.value)

    assert status == ManifestToolsExitCode.INVALID_MANIFEST
    assert str(expected.value) in capsys.readouterr().err


# %% main - validating a manifest that names another plan


def run_validate_against_plans(
    monkeypatch, tmp_path: Path, dependency_text: str
) -> int:
    """
    Validate a one-item manifest depending on *dependency_text* against the fixture
    plans directory.

    :param monkeypatch: pytest's monkeypatch fixture.
    :param tmp_path: Where the manifest is written.
    :param dependency_text: The one entry of that item's ``depends_on``.
    :return: The exit status the command line returns.
    """
    manifest_path = tmp_path / PlanDocument.MANIFEST
    manifest_path.write_text(
        yaml.safe_dump(
            minimal_plan(items=[manifest_item("a", depends_on=[dependency_text])])
        )
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            SCRIPT_NAME,
            ManifestToolsCommand.VALIDATE,
            str(manifest_path),
            ManifestToolsOption.PLANS_DIRECTORY,
            str(DatasetLocation.PLANS.value),
        ],
    )
    return main()


def test_validate_accepts_a_reference_the_plans_directory_resolves(
    monkeypatch, tmp_path
):
    assert run_validate_against_plans(
        monkeypatch, tmp_path, foreign_reference(ForeignItemId.READY)
    ) == (ManifestToolsExitCode.SUCCESS)


def test_validate_refuses_a_reference_to_a_plan_the_directory_lacks(
    monkeypatch, tmp_path
):
    assert run_validate_against_plans(
        monkeypatch,
        tmp_path,
        foreign_reference(ForeignItemId.READY, FixturePlanId.ABSENT),
    ) == (ManifestToolsExitCode.INVALID_MANIFEST)


# %% item - one item's slice of a plan


def test_item_summary_holds_the_one_item_and_the_plan_header():
    plan = LandedItemsPlan.read()
    item = plan.item_with_status(ItemStatus.IN_PROGRESS)
    summary = yaml.safe_load(plan.manifest.item_summary(item))
    assert summary == {
        ManifestKey.IDENTIFIER.key: plan.manifest.identifier,
        ManifestKey.TITLE.key: plan.manifest.content[ManifestKey.TITLE.key],
        ManifestKey.TRACKING_ISSUE.key: plan.manifest.content[
            ManifestKey.TRACKING_ISSUE.key
        ],
        ItemSummaryKey.ITEM.value: item.content,
    }


def test_an_item_the_plan_does_not_track_is_refused():
    with pytest.raises(ItemNotTrackedError):
        LandedItemsPlan.read().manifest.item_named("missing")


def test_a_branch_no_item_is_worked_on_is_refused():
    with pytest.raises(ItemNotTrackedError):
        LandedItemsPlan.read().manifest.item_on_branch("missing")


def test_main_dispatches_item_by_id(monkeypatch, capsys):
    plan = LandedItemsPlan.read()
    item = plan.item_with_status(ItemStatus.NOT_STARTED)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            SCRIPT_NAME,
            ManifestToolsCommand.ITEM,
            str(DatasetLocation.PLAN_WITH_LANDED_ITEMS),
            ManifestToolsOption.ITEM_IDENTIFIER,
            item.identifier,
        ],
    )
    assert main() == ManifestToolsExitCode.SUCCESS
    assert capsys.readouterr().out == plan.manifest.item_summary(item)


def test_main_dispatches_item_by_branch(monkeypatch, capsys):
    plan = LandedItemsPlan.read()
    item = plan.item_with_status(ItemStatus.IN_PROGRESS)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            SCRIPT_NAME,
            ManifestToolsCommand.ITEM,
            str(DatasetLocation.PLAN_WITH_LANDED_ITEMS),
            ManifestToolsOption.BRANCH,
            item.content[ManifestKey.BRANCH.key],
        ],
    )
    assert main() == ManifestToolsExitCode.SUCCESS
    assert capsys.readouterr().out == plan.manifest.item_summary(item)


# %% merging a session's save


def run_merge(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    session: PlanVersion,
    latest: PlanVersion,
) -> ManifestToolsExitCode:
    """
    Run the merge subcommand on the fixture plan as read, *session* and *latest*.

    :return: How the command ended; what it wrote is under ``tmp_path / "output"``.
    """
    arguments = [SCRIPT_NAME, ManifestToolsCommand.MERGE]
    for option, version in (
        (ManifestToolsOption.READ, read_version()),
        (ManifestToolsOption.SESSION, session),
        (ManifestToolsOption.LATEST, latest),
    ):
        version.write(tmp_path / option.lstrip("-"))
        arguments += [option, str(tmp_path / option.lstrip("-"))]
    arguments += [ManifestToolsOption.OUTPUT, str(tmp_path / "output")]
    monkeypatch.setattr(sys, "argv", arguments)
    return main()


def test_main_writes_the_merged_plan(monkeypatch, tmp_path: Path):
    latest = deferred(read_version(), SECOND_ITEM)

    status = run_merge(
        monkeypatch, tmp_path, blocked(read_version(), FIRST_ITEM), latest
    )

    assert status == ManifestToolsExitCode.SUCCESS
    assert PlanVersion.from_directory(tmp_path / "output") == blocked(
        latest, FIRST_ITEM
    )


def test_main_refuses_an_item_both_writers_changed(monkeypatch, tmp_path: Path):
    status = run_merge(
        monkeypatch,
        tmp_path,
        blocked(read_version(), FIRST_ITEM),
        deferred(read_version(), FIRST_ITEM),
    )

    assert status == ManifestToolsExitCode.CHANGED_SINCE_READ
    assert not (tmp_path / "output").exists()
