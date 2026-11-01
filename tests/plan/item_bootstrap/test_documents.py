"""
Tests for the plan documents an item is looked up in.
"""

from __future__ import annotations

from basstler.plan.item_bootstrap.documents import PlanDocuments
from basstler.plan.model import ManifestKey

# %% looking an item up by its branch

BRANCH_WITHOUT_ITEM_ID = "claude/work-without-an-id"

NOTES_COMMIT = "0123456789abcdef0123456789abcdef01234567"
"""
The personal-notes commit the documents claim to have been read at.
"""


def documents_holding_an_item_without_an_id() -> PlanDocuments:
    manifest_text = (
        f"{ManifestKey.IDENTIFIER.key}: some-plan\n"
        f"{ManifestKey.ITEMS.key}:\n"
        f"- {ManifestKey.BRANCH.key}: {BRANCH_WITHOUT_ITEM_ID}\n"
        f"  {ManifestKey.STATUS.key}: in progress\n"
    )
    return PlanDocuments(
        plan_identifier="some-plan",
        manifest_text=manifest_text,
        roadmap_text="",
        read_at=NOTES_COMMIT,
    )


def test_an_item_with_no_id_is_found_by_its_branch():
    documents = documents_holding_an_item_without_an_id()

    item = documents.item(BRANCH_WITHOUT_ITEM_ID)

    assert item[ManifestKey.BRANCH.key] == BRANCH_WITHOUT_ITEM_ID
