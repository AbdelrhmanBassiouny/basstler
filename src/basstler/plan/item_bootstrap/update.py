"""
Setting an item's recorded fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from basstler.plan.item_bootstrap.documents import PlanDocuments
from basstler.plan.item_bootstrap.manifest_text import ManifestText
from basstler.plan.item_bootstrap.report import BootstrapReport
from basstler.plan.item_bootstrap.vocabulary import BlockScalarStyle
from basstler.plan.model import (
    ManifestKey,
    Prose,
)

# %% updating an item


@dataclass(frozen=True)
class RecordedNote:
    """
    The note an item's manifest entry carries, as YAML read it back.
    """

    text: str | None
    """
    The note's text, or ``None`` where the item carries none.
    """

    style: BlockScalarStyle
    """
    How the note is written in the manifest, which decides how its paragraphs read back.
    """

    def extended_by(self, addition: str) -> str:
        """
        The note with *addition* as a further paragraph, its paragraphs separated by
        blank lines as :class:`basstler.plan.model.Prose` reads them.

        :param addition: The text to add, as its author wrote it.
        :return: The whole note.
        """
        paragraphs = [
            paragraph
            for paragraph in self.style.paragraph_separator.split(
                (self.text or "").strip()
            )
            if paragraph
        ]
        paragraphs.append(addition.strip())
        return "\n\n".join(paragraphs)


@dataclass(frozen=True)
class ItemUpdateRequest:
    """
    What updating one item needs: which item, and which fields to set on it.
    """

    plan_identifier: str
    """
    The plan the item belongs to.
    """

    item_identifier: str
    """
    The item being updated, which must already be tracked.
    """

    values_by_key: dict[ManifestKey, Any]
    """
    The value to write to each key, in the order they are applied.
    """

    notes_to_append: str | None = None
    """
    A further paragraph for the item's recorded note, rather than a replacement for it.
    """

    def update(self, project_root: Path) -> BootstrapReport:
        """
        Set the item's fields and push the manifest, leaving the roadmap alone.

        :param project_root: The repository to run within.
        :raises UnknownPlanError: If the plan has no manifest on the notes branch.
        :raises UnknownItemError: If the plan tracks no item of that id.
        :return: What was written.
        """
        documents = PlanDocuments.load(self.plan_identifier, project_root)
        manifest = ManifestText.from_text(documents.manifest_text)
        values_by_key = dict(self.values_by_key)
        if self.notes_to_append is not None:
            recorded = RecordedNote(
                text=documents.item(self.item_identifier).get(ManifestKey.NOTES.key),
                style=manifest.block_scalar_style(
                    self.plan_identifier, self.item_identifier, ManifestKey.NOTES
                ),
            )
            values_by_key[ManifestKey.NOTES] = recorded.extended_by(
                self.notes_to_append
            )
        manifest_text = manifest.with_item_fields(
            self.plan_identifier, self.item_identifier, values_by_key
        )
        documents.save(manifest_text, documents.roadmap_text, project_root)
        written_note = values_by_key.get(ManifestKey.NOTES)
        return BootstrapReport(
            plan_identifier=self.plan_identifier,
            item_identifier=self.item_identifier,
            note_paragraphs=(
                len(Prose(written_note).paragraphs)
                if written_note is not None
                else None
            ),
        )
