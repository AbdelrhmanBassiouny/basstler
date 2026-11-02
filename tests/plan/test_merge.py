"""
Merging a session's edit of a plan onto the plan as another writer has since left it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from basstler.plan.exceptions import ConcurrentEditError, PlanRemovedSinceReadError
from basstler.plan.merge import (
    ItemPart,
    ManifestFieldPart,
    PlanMerge,
    PlanVersion,
    RoadmapPart,
)
from basstler.plan.model import ManifestKey

from ..constants.paths import DatasetLocation
from .concurrent_edits import (
    FIRST_ITEM,
    SECOND_ITEM,
    blocked,
    deferred,
    read_version,
    with_added_item,
    with_roadmap,
    without_item,
)

# %% merging the fixture plan


def merged(session: PlanVersion, latest: PlanVersion) -> PlanVersion:
    """
    :return: *session*'s edits of the fixture plan merged onto *latest*.
    """
    return PlanMerge(read=read_version(), session=session, latest=latest).merged()


def parsed_items(version: PlanVersion) -> dict[str, dict[str, Any]]:
    """
    :return: The version's items by id, as YAML reads them.
    """
    return {
        item[ManifestKey.IDENTIFIER.key]: item
        for item in yaml.safe_load(version.manifest_text)[ManifestKey.ITEMS.key]
    }


# %% edits to different items


def test_an_edit_to_another_item_survives_the_session_s_save():
    session = blocked(read_version(), FIRST_ITEM)
    latest = deferred(read_version(), SECOND_ITEM)

    result = merged(session, latest)

    assert result.manifest_text == blocked(latest, FIRST_ITEM).manifest_text


def test_a_save_onto_an_unchanged_plan_writes_the_session_s_text():
    session = blocked(read_version(), FIRST_ITEM)

    assert merged(session, read_version()) == session


def test_an_untouched_session_keeps_what_the_other_writer_saved():
    latest = deferred(read_version(), SECOND_ITEM)

    assert merged(read_version(), latest) == latest


def test_an_item_the_session_added_joins_the_other_writer_s_edit():
    session = with_added_item(read_version())
    latest = deferred(read_version(), SECOND_ITEM)

    result = merged(session, latest)

    assert parsed_items(result) == parsed_items(with_added_item(latest))


def test_an_item_the_other_writer_dropped_stays_dropped():
    session = blocked(read_version(), FIRST_ITEM)
    latest = without_item(read_version(), SECOND_ITEM)

    result = merged(session, latest)

    assert parsed_items(result) == parsed_items(blocked(latest, FIRST_ITEM))


def test_a_plan_field_the_session_changed_joins_an_item_edit():
    session = PlanVersion(
        manifest_text=DatasetLocation.BOOTSTRAP_PLAN.read_text().replace(
            "A plan under test", "A plan renamed by the session"
        ),
        roadmap_text=DatasetLocation.BOOTSTRAP_ROADMAP.read_text(),
    )
    latest = deferred(read_version(), SECOND_ITEM)

    result = merged(session, latest)

    assert yaml.safe_load(result.manifest_text) == yaml.safe_load(
        deferred(session, SECOND_ITEM).manifest_text
    )


def test_a_roadmap_edit_joins_an_item_edit():
    session = with_roadmap(read_version(), DatasetLocation.ROADMAP_WITH_SESSION_RULE)
    latest = deferred(read_version(), SECOND_ITEM)

    assert merged(session, latest) == with_roadmap(
        latest, DatasetLocation.ROADMAP_WITH_SESSION_RULE
    )


# %% edits to the same part


def test_an_item_both_writers_changed_differently_is_refused():
    session = blocked(read_version(), FIRST_ITEM)
    latest = deferred(read_version(), FIRST_ITEM)

    with pytest.raises(ConcurrentEditError) as refusal:
        merged(session, latest)

    assert refusal.value.parts == (ItemPart(FIRST_ITEM),)


def test_an_item_both_writers_changed_alike_is_not_a_conflict():
    session = blocked(read_version(), FIRST_ITEM)

    assert merged(session, blocked(read_version(), FIRST_ITEM)) == blocked(
        read_version(), FIRST_ITEM
    )


def test_an_item_the_session_changed_but_another_writer_dropped_is_refused():
    session = blocked(read_version(), FIRST_ITEM)
    latest = without_item(read_version(), FIRST_ITEM)

    with pytest.raises(ConcurrentEditError) as refusal:
        merged(session, latest)

    assert refusal.value.parts == (ItemPart(FIRST_ITEM),)


def test_a_plan_field_both_writers_changed_differently_is_refused():
    def renamed(title: str) -> PlanVersion:
        return PlanVersion(
            manifest_text=DatasetLocation.BOOTSTRAP_PLAN.read_text().replace(
                "A plan under test", title
            ),
            roadmap_text=DatasetLocation.BOOTSTRAP_ROADMAP.read_text(),
        )

    with pytest.raises(ConcurrentEditError) as refusal:
        merged(renamed("The session's title"), renamed("Another writer's title"))

    assert refusal.value.parts == (ManifestFieldPart(ManifestKey.TITLE.key),)


def test_a_roadmap_both_writers_changed_differently_is_refused():
    session = with_roadmap(read_version(), DatasetLocation.ROADMAP_WITH_SESSION_RULE)
    latest = with_roadmap(read_version(), DatasetLocation.ROADMAP_WITH_CONCURRENT_RULE)

    with pytest.raises(ConcurrentEditError) as refusal:
        merged(session, latest)

    assert refusal.value.parts == (RoadmapPart(),)


# %% a plan that is new, or gone


def test_a_new_plan_is_saved_as_the_session_wrote_it():
    session = read_version()

    result = PlanMerge(
        read=PlanVersion.absent(), session=session, latest=PlanVersion.absent()
    ).merged()

    assert result == session


def test_a_plan_removed_since_it_was_read_is_refused():
    with pytest.raises(PlanRemovedSinceReadError):
        PlanMerge(
            read=read_version(),
            session=blocked(read_version(), FIRST_ITEM),
            latest=PlanVersion.absent(),
        ).merged()


# %% the plan's documents on disk


def test_a_version_reads_back_the_documents_it_wrote(tmp_path: Path):
    version = blocked(read_version(), FIRST_ITEM)

    version.write(tmp_path)

    assert PlanVersion.from_directory(tmp_path) == version


def test_a_directory_without_the_plan_reads_as_absent(tmp_path: Path):
    assert PlanVersion.from_directory(tmp_path) == PlanVersion.absent()
