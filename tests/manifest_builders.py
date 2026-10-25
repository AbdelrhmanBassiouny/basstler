"""
Builders for raw, plan.yaml-shaped mappings, for tests that need a manifest with only
the fields they care about.
"""

from __future__ import annotations

from typing import Any


from basstler.exceptions import (
    InvalidSchemaVersion,
)
from basstler.plan_model import ItemStatus, ManifestKey

from .fixture_plans import (
    PLAN_UNDER_TEST_ID,
)


# %% manifests


def minimal_plan(**overrides: Any) -> dict[str, Any]:
    """
    Build one raw, plan.yaml-shaped ``dict`` with a single not-started item - the
    smallest input :meth:`PlanValidator.validate`/:meth:`Plan.from_mapping` accept, for tests
    that only care about one specific field.

    :param overrides: Top-level keys to replace in the returned mapping.
    """
    plan = {
        ManifestKey.SCHEMA_VERSION.key: InvalidSchemaVersion.supported_version,
        ManifestKey.IDENTIFIER.key: PLAN_UNDER_TEST_ID,
        ManifestKey.TITLE.key: "Test Plan",
        ManifestKey.DESCRIPTION.key: "A plan.",
        ManifestKey.DEFAULT_REPOSITORY.key: "owner/repo",
        ManifestKey.WAVES.key: [
            {ManifestKey.IDENTIFIER.key: "wave-1", ManifestKey.NAME.key: "Wave 1"}
        ],
        ManifestKey.TRACKS.key: [
            {
                ManifestKey.IDENTIFIER.key: "track-1",
                ManifestKey.NAME.key: "Track 1",
                ManifestKey.WAVE.key: "wave-1",
            }
        ],
        ManifestKey.ITEMS.key: [manifest_item("a", title="Item A")],
    }
    plan.update(overrides)
    return plan


def manifest_item(identifier: str, **overrides: Any) -> dict[str, Any]:
    """
    Build one raw, plan.yaml-shaped item ``dict``, keyed by :class:`ManifestKey` so a
    manifest key is spelled in one place.

    :param identifier: The item's ``id``, also used as its ``branch`` and
        ``title`` unless overridden.
    :param overrides: Further keys, named after their :class:`ManifestKey`
        member - a ``None`` value leaves that key out of the manifest
        entirely.
    """
    entry = {
        ManifestKey.IDENTIFIER.key: identifier,
        ManifestKey.TITLE.key: identifier.upper(),
        ManifestKey.BRANCH.key: identifier,
        ManifestKey.TRACK.key: "track-1",
        ManifestKey.STATUS.key: ItemStatus.NOT_STARTED.value,
    }
    entry.update(
        {
            next(
                manifest_key for manifest_key in ManifestKey if manifest_key.key == key
            ).key: value
            for key, value in overrides.items()
        }
    )
    return {key: value for key, value in entry.items() if value is not None}
