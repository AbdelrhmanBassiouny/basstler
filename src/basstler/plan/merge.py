"""
Merging a session's edit of a plan onto the plan as other writers have left it since the
session read it, one top-level field, item and roadmap at a time.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from functools import cached_property
from pathlib import Path
from typing import Any

import yaml

from basstler.plan.exceptions import (
    ConcurrentEditError,
    MergeDisagreesError,
    PlanRemovedSinceReadError,
)
from basstler.plan.item_bootstrap.manifest_text import ManifestText
from basstler.plan.model import ManifestKey, PlanDocument

# %% one plan's documents at one point in time


class Absence(Enum):
    """
    What a plan version holds in place of a part it does not have.
    """

    ABSENT = "absent"
    """
    The version does not hold the part at all, which differs from a part set to
    ``null``.
    """


@dataclass(frozen=True)
class PlanVersion:
    """
    A plan's manifest and roadmap as raw text, as one writer saw or wrote them.
    """

    manifest_text: str | None
    """
    The manifest, or ``None`` where the plan does not exist.
    """

    roadmap_text: str | None
    """
    The roadmap, or ``None`` where the plan has none.
    """

    @classmethod
    def absent(cls) -> PlanVersion:
        """
        :return: The version of a plan that does not exist.
        """
        return cls(manifest_text=None, roadmap_text=None)

    @classmethod
    def from_directory(cls, directory: Path) -> PlanVersion:
        """
        :param directory: A plan's directory, holding its documents by their
            :class:`PlanDocument` filenames.
        :return: The documents the directory holds.
        """
        texts = {
            document: (
                (directory / document).read_text()
                if (directory / document).is_file()
                else None
            )
            for document in PlanDocument
        }
        return cls(
            manifest_text=texts[PlanDocument.MANIFEST],
            roadmap_text=texts[PlanDocument.ROADMAP],
        )

    def write(self, directory: Path) -> None:
        """
        Write each document this version holds into *directory*, by its
        :class:`PlanDocument` filename.

        :param directory: The plan directory to write, created if missing.
        """
        directory.mkdir(parents=True, exist_ok=True)
        texts = {
            PlanDocument.MANIFEST: self.manifest_text,
            PlanDocument.ROADMAP: self.roadmap_text,
        }
        for document, text in texts.items():
            if text is not None:
                (directory / document).write_text(text)

    @cached_property
    def manifest_content(self) -> dict[str, Any]:
        """
        The manifest as YAML reads it, empty where the plan does not exist.
        """
        if self.manifest_text is None:
            return {}
        return yaml.safe_load(self.manifest_text) or {}

    @property
    def items_by_identifier(self) -> dict[str, dict[str, Any]]:
        """
        The manifest's items keyed by their id, in manifest order.
        """
        return {
            item[ManifestKey.IDENTIFIER.key]: item
            for item in self.manifest_content.get(ManifestKey.ITEMS.key) or []
        }


# %% the parts a plan is merged by


@dataclass(frozen=True)
class PlanPart(ABC):
    """
    One part of a plan that two writers can change independently.
    """

    @classmethod
    @abstractmethod
    def parts_of(cls, version: PlanVersion) -> list[PlanPart]:
        """
        :param version: The plan to look through.
        :return: Every part of this kind the version holds, in the order it holds them.
        """

    @property
    @abstractmethod
    def description(self) -> str:
        """
        The part as a reader finds it in the plan.
        """

    @property
    @abstractmethod
    def document(self) -> PlanDocument:
        """
        The document the part is written in.
        """

    @abstractmethod
    def value_in(self, version: PlanVersion) -> Any:
        """
        :param version: The plan to read.
        :return: The part's value as the version holds it, or :attr:`Absence.ABSENT`.
        """

    @abstractmethod
    def copied_from(self, session: PlanVersion, onto: PlanVersion) -> PlanVersion:
        """
        :param session: The version whose text of this part to take.
        :param onto: The version to put it in.
        :return: *onto* with this part as *session* writes it, every other line
            untouched; without the part where *session* does not hold it.
        """


@dataclass(frozen=True)
class ManifestFieldPart(PlanPart):
    """
    A top-level manifest key other than ``items``, with its whole value.
    """

    key: str
    """
    The top-level key.
    """

    @classmethod
    def parts_of(cls, version: PlanVersion) -> list[PlanPart]:
        return [
            cls(key) for key in version.manifest_content if key != ManifestKey.ITEMS.key
        ]

    @property
    def description(self) -> str:
        return f"the field {self.key!r}"

    @property
    def document(self) -> PlanDocument:
        return PlanDocument.MANIFEST

    def value_in(self, version: PlanVersion) -> Any:
        return version.manifest_content.get(self.key, Absence.ABSENT)

    def copied_from(self, session: PlanVersion, onto: PlanVersion) -> PlanVersion:
        session_text = ManifestText.from_text(session.manifest_text)
        session_section = session_text.top_level_section(self.key)
        section_lines = (
            []
            if session_section is None
            else session_text.lines[session_section[0] : session_section[1]]
        )
        onto_text = ManifestText.from_text(onto.manifest_text)
        onto_section = onto_text.top_level_section(self.key)
        if onto_section is None:
            onto_section = (len(onto_text.lines), len(onto_text.lines))
        return PlanVersion(
            manifest_text=onto_text.with_lines_replaced(onto_section, section_lines),
            roadmap_text=onto.roadmap_text,
        )


@dataclass(frozen=True)
class ItemPart(PlanPart):
    """
    One item of the manifest's ``items``, with every field it carries.
    """

    item_identifier: str
    """
    The item's id.
    """

    @classmethod
    def parts_of(cls, version: PlanVersion) -> list[PlanPart]:
        return [cls(identifier) for identifier in version.items_by_identifier]

    @property
    def description(self) -> str:
        return f"the item {self.item_identifier!r}"

    @property
    def document(self) -> PlanDocument:
        return PlanDocument.MANIFEST

    def value_in(self, version: PlanVersion) -> Any:
        return version.items_by_identifier.get(self.item_identifier, Absence.ABSENT)

    def copied_from(self, session: PlanVersion, onto: PlanVersion) -> PlanVersion:
        session_text = ManifestText.from_text(session.manifest_text)
        session_block = session_text.item_block_named(self.item_identifier)
        onto_text = ManifestText.from_text(onto.manifest_text)
        onto_block = onto_text.item_block_named(self.item_identifier)
        if session_block is None:
            manifest_text = onto_text.with_lines_replaced(onto_block, [])
        elif onto_block is None:
            block = "\n".join(session_text.lines[session_block[0] : session_block[1]])
            manifest_text = onto_text.with_item(block.rstrip("\n") + "\n")
        else:
            manifest_text = onto_text.with_lines_replaced(
                onto_block, session_text.lines[session_block[0] : session_block[1]]
            )
        return PlanVersion(manifest_text=manifest_text, roadmap_text=onto.roadmap_text)


@dataclass(frozen=True)
class RoadmapPart(PlanPart):
    """
    The plan's roadmap, as one document.
    """

    @classmethod
    def parts_of(cls, version: PlanVersion) -> list[PlanPart]:
        return [cls()]

    @property
    def description(self) -> str:
        return "the roadmap"

    @property
    def document(self) -> PlanDocument:
        return PlanDocument.ROADMAP

    def value_in(self, version: PlanVersion) -> Any:
        if version.roadmap_text is None:
            return Absence.ABSENT
        return version.roadmap_text.strip()

    def copied_from(self, session: PlanVersion, onto: PlanVersion) -> PlanVersion:
        return PlanVersion(
            manifest_text=onto.manifest_text, roadmap_text=session.roadmap_text
        )


# %% merging


class PartResolution(Enum):
    """
    Which writer's value of one part the merged plan carries.
    """

    KEEP_LATEST = "keep latest"
    """
    The session left the part as it read it, or changed it to what is there now.
    """

    TAKE_SESSION = "take session"
    """
    Only the session changed the part since it read it.
    """

    CONFLICT = "conflict"
    """
    The session and another writer both changed the part, to different values.
    """

    @classmethod
    def between(cls, read: Any, session: Any, latest: Any) -> PartResolution:
        """
        :param read: The part's value when the session read the plan.
        :param session: The part's value in the session's edit.
        :param latest: The part's value on the notes branch now.
        :return: Which value the merged plan carries.
        """
        if session == read or session == latest:
            return cls.KEEP_LATEST
        if latest == read:
            return cls.TAKE_SESSION
        return cls.CONFLICT


@dataclass(frozen=True)
class PlanMerge:
    """
    A session's edit of a plan, and the two versions it is merged between: the plan as
    the session read it, and the plan on the notes branch now.
    """

    read: PlanVersion
    """
    The plan as the session read it, absent for a plan the session creates.
    """

    session: PlanVersion
    """
    The plan as the session wrote it.
    """

    latest: PlanVersion
    """
    The plan on the notes branch now, absent where nobody has saved it.
    """

    @property
    def plan_identifier(self) -> str:
        """
        The id of the plan being saved.
        """
        return str(self.session.manifest_content[ManifestKey.IDENTIFIER.key])

    def merged(self) -> PlanVersion:
        """
        Apply every part the session changed since it read the plan onto the latest
        version, keeping the latest version's text of every other part.

        :raises PlanRemovedSinceReadError: If the plan was removed since it was read.
        :raises ConcurrentEditError: If another writer changed a part the session also
            changed, to a different value.
        :raises MergeDisagreesError: If the merged text does not read back as the merge
            decided.
        :return: The plan to save.
        """
        if self.latest.manifest_text is None:
            if self.read.manifest_text is not None:
                raise PlanRemovedSinceReadError(plan_identifier=self.plan_identifier)
            return self.session
        conflicts = tuple(
            part
            for part, resolution in self.resolutions.items()
            if resolution is PartResolution.CONFLICT
        )
        if conflicts:
            raise ConcurrentEditError(
                plan_identifier=self.plan_identifier, parts=conflicts
            )
        merged = self.latest
        for part, resolution in self.resolutions.items():
            if resolution is PartResolution.TAKE_SESSION:
                merged = part.copied_from(self.session, merged)
        self.confirm_reads_back(merged)
        return merged

    @property
    def unapplied_parts(self) -> tuple[PlanPart, ...]:
        """
        Every part the session changed since it read the plan that the latest version
        does not carry as the session wrote it.
        """
        return tuple(
            part
            for part, resolution in self.resolutions.items()
            if resolution is not PartResolution.KEEP_LATEST
        )

    @cached_property
    def resolutions(self) -> dict[PlanPart, PartResolution]:
        """
        Which writer's value each part of the plan takes, in :attr:`parts` order.
        """
        return {
            part: PartResolution.between(
                part.value_in(self.read),
                part.value_in(self.session),
                part.value_in(self.latest),
            )
            for part in self.parts
        }

    @property
    def parts(self) -> list[PlanPart]:
        """
        Every part any of the three versions holds, in the latest version's order, then
        the session's, then the read version's.
        """
        parts: dict[PlanPart, None] = {}
        for version in (self.latest, self.session, self.read):
            for kind in (ManifestFieldPart, ItemPart, RoadmapPart):
                parts.update(dict.fromkeys(kind.parts_of(version)))
        return list(parts)

    def confirm_reads_back(self, merged: PlanVersion) -> None:
        """
        :param merged: The merged plan.
        :raises MergeDisagreesError: If any part of *merged* differs from the value its
            resolution chose.
        """
        source = {
            PartResolution.KEEP_LATEST: self.latest,
            PartResolution.TAKE_SESSION: self.session,
        }
        disagreeing = tuple(
            part
            for part, resolution in self.resolutions.items()
            if part.value_in(merged) != part.value_in(source[resolution])
        )
        if disagreeing:
            raise MergeDisagreesError(
                plan_identifier=self.plan_identifier, parts=disagreeing
            )
