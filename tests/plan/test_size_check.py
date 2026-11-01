"""
Tests for plan/size_check.py: the command ``/add-plan-item`` and ``/plan-create`` run to
learn whether a plan is already full, before writing anything into or as it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import basstler.plan.size_check
from basstler.plan.model import ItemStatus, ManifestKey, PlanManifest
from basstler.plan.size_check import PlanSizeCheckOption, PlanSizeCheckResult, main
from basstler.plan.size_limits import Measure

# %% helpers

SCRIPT_NAME = Path(basstler.plan.size_check.__file__).name
"""
This script's own filename, read from the module rather than spelled again here.
"""


def write_plan(
    tmp_path: Path, open_item_count: int, landed_item_count: int = 0
) -> Path:
    """
    Write a manifest holding the given numbers of open and landed items to *tmp_path*.

    :param tmp_path: Where to write the manifest.
    :param open_item_count: How many items are still in progress.
    :param landed_item_count: How many items have landed.
    :return: The manifest's path.
    """
    statuses = [ItemStatus.IN_PROGRESS] * open_item_count + [
        ItemStatus.DONE
    ] * landed_item_count
    manifest_path = tmp_path / "plan.yaml"
    PlanManifest(
        {
            ManifestKey.IDENTIFIER.key: "a-plan",
            ManifestKey.ITEMS.key: [
                {
                    ManifestKey.IDENTIFIER.key: f"item-{number}",
                    ManifestKey.STATUS.key: status.value,
                }
                for number, status in enumerate(statuses)
            ],
        }
    ).write(manifest_path)
    return manifest_path


def run_check(monkeypatch, capsys, manifest_path: Path) -> PlanSizeCheckResult:
    """
    Run the check's command line against *manifest_path* and parse its printed result.

    :param monkeypatch: pytest's monkeypatch fixture.
    :param capsys: pytest's stdout/stderr capture fixture.
    :param manifest_path: The manifest to measure.
    :return: The result it printed.
    """
    monkeypatch.setattr(
        sys,
        "argv",
        [SCRIPT_NAME, PlanSizeCheckOption.MANIFEST, str(manifest_path)],
    )
    exit_code = main()
    assert exit_code == 0
    return PlanSizeCheckResult.from_json(json.loads(capsys.readouterr().out))


# %% fullness


def test_a_plan_with_room_for_one_more_item_is_not_full(tmp_path, monkeypatch, capsys):
    manifest_path = write_plan(tmp_path, Measure.ITEM_COUNT.maximum - 1)
    result = run_check(monkeypatch, capsys, manifest_path)
    assert result.is_full is False


def test_a_plan_at_the_item_limit_is_full_since_one_more_would_be_refused(
    tmp_path, monkeypatch, capsys
):
    manifest_path = write_plan(tmp_path, Measure.ITEM_COUNT.maximum)
    result = run_check(monkeypatch, capsys, manifest_path)
    assert result.is_full is True


def test_landed_items_are_not_counted_since_a_save_prunes_them(
    tmp_path, monkeypatch, capsys
):
    manifest_path = write_plan(
        tmp_path, Measure.ITEM_COUNT.maximum - 1, landed_item_count=3
    )
    result = run_check(monkeypatch, capsys, manifest_path)
    assert result.item_count == Measure.ITEM_COUNT.maximum - 1
    assert result.is_full is False


def test_reports_the_measured_count_against_the_limit(tmp_path, monkeypatch, capsys):
    manifest_path = write_plan(tmp_path, 4)
    result = run_check(monkeypatch, capsys, manifest_path)
    assert result.item_count == 4
    assert result.item_limit == Measure.ITEM_COUNT.maximum
