"""
The fixture plan as a session read it, and the edits a session or another writer makes
to it, for the tests of saving a plan two writers changed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from basstler.plan.item_bootstrap.manifest_text import ManifestText
from basstler.plan.merge import PlanVersion
from basstler.plan.model import ItemStatus, ManifestKey, PlanManifest

from ..constants.paths import DatasetLocation

# %% the plan as read, and the edits made to it


PLAN_IDENTIFIER = PlanManifest.from_file(DatasetLocation.BOOTSTRAP_PLAN).identifier
"""
The id the fixture plan carries.
"""

FIRST_ITEM = "an-existing-item"
"""
The fixture item the session edits.
"""

SECOND_ITEM = "a-second-item"
"""
The fixture item the other writer edits.
"""


def read_version() -> PlanVersion:
    """
    :return: The fixture plan as the session read it.
    """
    return PlanVersion(
        manifest_text=DatasetLocation.BOOTSTRAP_PLAN.read_text(),
        roadmap_text=DatasetLocation.BOOTSTRAP_ROADMAP.read_text(),
    )


def with_item_fields(
    version: PlanVersion, item_identifier: str, values_by_key: dict[ManifestKey, Any]
) -> PlanVersion:
    """
    :param version: The plan to edit.
    :param item_identifier: The item to set fields on.
    :param values_by_key: The fields to set.
    :return: *version* with the item's fields set, its roadmap untouched.
    """
    return PlanVersion(
        manifest_text=ManifestText.from_text(version.manifest_text).with_item_fields(
            PLAN_IDENTIFIER, item_identifier, values_by_key
        ),
        roadmap_text=version.roadmap_text,
    )


def blocked(version: PlanVersion, item_identifier: str) -> PlanVersion:
    """
    :return: *version* with the item marked blocked.
    """
    return with_item_fields(
        version, item_identifier, {ManifestKey.STATUS: ItemStatus.BLOCKED}
    )


def deferred(version: PlanVersion, item_identifier: str) -> PlanVersion:
    """
    :return: *version* with the item marked deferred.
    """
    return with_item_fields(
        version, item_identifier, {ManifestKey.STATUS: ItemStatus.DEFERRED}
    )


def with_added_item(version: PlanVersion) -> PlanVersion:
    """
    :return: *version* with :attr:`DatasetLocation.MERGE_NEW_ITEM` appended.
    """
    return PlanVersion(
        manifest_text=ManifestText.from_text(version.manifest_text).with_item(
            DatasetLocation.MERGE_NEW_ITEM.read_text()
        ),
        roadmap_text=version.roadmap_text,
    )


def without_item(version: PlanVersion, item_identifier: str) -> PlanVersion:
    """
    :return: *version* with the item's block removed, as a save drops a landed item.
    """
    manifest = ManifestText.from_text(version.manifest_text)
    start, end = manifest.locate_item_block(PLAN_IDENTIFIER, item_identifier)
    return PlanVersion(
        manifest_text="\n".join(manifest.lines[:start] + manifest.lines[end:]),
        roadmap_text=version.roadmap_text,
    )


def with_roadmap(version: PlanVersion, roadmap: Path) -> PlanVersion:
    """
    :return: *version* with its roadmap replaced by *roadmap*'s text.
    """
    return PlanVersion(
        manifest_text=version.manifest_text, roadmap_text=roadmap.read_text()
    )
