"""
Recording an item in its plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from basstler.plan.item_bootstrap.documents import PlanDocuments
from basstler.plan.item_bootstrap.exceptions import IncompleteNewItemError
from basstler.plan.item_bootstrap.manifest_text import ManifestText
from basstler.plan.item_bootstrap.report import BootstrapReport
from basstler.plan.model import (
    ItemIndentation,
    ItemStatus,
    ManifestKey,
)

# %% recording an item


@dataclass(frozen=True)
class ItemRecordRequest:
    """
    What recording one item needs: where it goes, what it is, and what to say about it.
    """

    plan_identifier: str
    """
    The plan the item belongs to.
    """

    item_identifier: str
    """
    The item's id, created if the plan does not track it yet.
    """

    status: ItemStatus
    """
    The status to set on the item.
    """

    title: str | None = None
    """
    The item's title, required only when the entry does not exist yet.
    """

    track: str | None = None
    """
    The track the item belongs to, required only when the entry does not exist yet.
    """

    roadmap_entry: str | None = None
    """
    A standing rule of the plan the item settled, added to its roadmap; ``None`` leaves
    the roadmap as it is.
    """

    def render_new_item(self, indentation: ItemIndentation) -> str:
        """
        Render a brand-new item block, in the field order ``plan-schema.md`` documents.

        :param indentation: How the manifest it is added to indents its items.
        :raises IncompleteNewItemError: If a field a new entry cannot omit is missing.
        :return: The block's text, newline-terminated.
        """
        required = {ManifestKey.TITLE: self.title, ManifestKey.TRACK: self.track}
        missing = tuple(
            manifest_key for manifest_key, value in required.items() if not value
        )
        if missing:
            raise IncompleteNewItemError(
                item_identifier=self.item_identifier, missing_keys=missing
            )
        body = {
            ManifestKey.TITLE: self.title,
            ManifestKey.BRANCH: None,
            ManifestKey.TRACK: self.track,
            ManifestKey.DEPENDS_ON: (),
            ManifestKey.STATUS: self.status.value,
        }
        return ManifestKey.IDENTIFIER.render(
            self.item_identifier, opening_the_item=True, indentation=indentation
        ) + "".join(
            manifest_key.render(value, indentation=indentation)
            for manifest_key, value in body.items()
        )

    def roadmap_after(self, roadmap_text: str) -> str:
        """
        :param roadmap_text: The roadmap as it stands.
        :return: The roadmap with :attr:`roadmap_entry` appended as one standing rule,
            or unchanged when there is none.
        """
        if self.roadmap_entry is None:
            return roadmap_text
        return f"{roadmap_text.rstrip(chr(10))}\n- {' '.join(self.roadmap_entry.split())}\n"

    def record(self, project_root: Path) -> BootstrapReport:
        """
        Write or update the item's manifest entry, and add its roadmap entry when it has
        one, then push both.

        :param project_root: The repository to run within.
        :raises UnknownPlanError: If the plan has no manifest on the notes branch.
        :raises IncompleteNewItemError: If a new entry is missing a field it cannot
            omit.
        :return: What was recorded.
        """
        documents = PlanDocuments.load(self.plan_identifier, project_root)
        manifest = ManifestText.from_text(documents.manifest_text)
        created_item = not documents.has_item(self.item_identifier)
        if created_item:
            manifest_text = manifest.with_item(
                self.render_new_item(manifest.item_indentation())
            )
        else:
            manifest_text = manifest.with_item_fields(
                self.plan_identifier,
                self.item_identifier,
                {ManifestKey.STATUS: self.status.value},
            )
        documents.save(
            manifest_text, self.roadmap_after(documents.roadmap_text), project_root
        )
        return BootstrapReport(
            plan_identifier=self.plan_identifier,
            item_identifier=self.item_identifier,
            created_item=created_item,
        )
