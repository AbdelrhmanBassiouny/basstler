"""
The parts of a plan's data model that more than one tool has to agree on.

Nothing here imports anything the tools reading it do not already have: the dashboard
build imports jinja2 and markdown of its own, and the bootstrap tool imports neither.
The dependency runs one way only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any

import yaml


class ItemStatus(StrEnum):
    """
    The statuses ``plan.yaml``'s ``status`` field accepts.

    Deliberately thin: everything about a pull request's actual GitHub state - open,
    draft, merged, its checks, its reviews - is never stored in the manifest. It is
    live-fetched and represented separately.
    """

    NOT_STARTED = "not started"
    """
    Nothing has begun.
    """

    IN_PROGRESS = "in progress"
    """
    The work is underway - what bootstrapping an item sets.
    """

    BLOCKED = "blocked"
    """
    Something outside the item has to move first.
    """

    DEFERRED = "deferred"
    """
    Deliberately parked rather than stuck.
    """

    DONE = "done"
    """
    Landed.
    """

    @classmethod
    def underscore_spellings(cls) -> dict[str, ItemStatus]:
        """
        The spelling manifests were written in before the values took spaces, which
        ``plan.yaml`` files still carry until they are rewritten.

        :return: Each status by its value with underscores in place of spaces.
        """
        return {status.value.replace(" ", "_"): status for status in cls}

    @classmethod
    def accepted_spellings(cls) -> frozenset[str]:
        """
        :return: Every text a manifest's ``status`` field may hold: each value, and its
            underscore spelling.
        """
        return frozenset(
            {status.value for status in cls} | set(cls.underscore_spellings())
        )

    @classmethod
    def _missing_(cls, value: object) -> ItemStatus | None:
        """
        Read a status from its underscore spelling as well as its value.

        :param value: The text no value matched.
        :return: The status that text spells, or ``None`` when it spells none.
        """
        return cls.underscore_spellings().get(value)


# %% the vocabulary a plan manifest is written in


class ItemLayout(StrEnum):
    """
    The whitespace and markers an item block in ``plan.yaml`` is laid out with.
    """

    FIELD_INDENT = " " * 4
    """
    The indentation ``plan.yaml`` item fields carry, one level inside the list marker.
    """

    MARKER = " " * 2 + "- "
    """
    What opens an item block, the list marker its first field sits behind.
    """


class ValueStyle(StrEnum):
    """
    How a key's value is written, in YAML's own vocabulary.

    Mutually exclusive by construction, which the two booleans this replaced could not
    say: a value is written one of these ways, never two.
    """

    PLAIN = "plain"
    """
    A bare scalar on the key's own line.
    """

    DOUBLE_QUOTED = "double_quoted"
    """
    A quoted scalar, for prose that would otherwise need escaping.
    """

    BLOCK = "block"
    """
    A value written across the lines beneath the key - a folded scalar or a sequence.

    Anything inserted after such a key would be swallowed by its value, so a new key
    goes before the first block-styled one in an item rather than at the end.
    """


@dataclass(frozen=True)
class KeySpecification:
    """
    How one ``plan.yaml`` key is written, so no caller has to decide per key.
    """

    key: str
    """
    The key as it appears in the manifest.

    Named ``key`` rather than ``name`` for two reasons: it is YAML's own term for the
    left-hand side of a mapping, and :class:`ManifestKey` mixes this class into an
    ``Enum``, whose ``name`` is reserved for the member's own name.
    """

    style: ValueStyle = ValueStyle.PLAIN
    """
    How this key's value is written.
    """


class ManifestKey(KeySpecification, Enum):
    """
    Every ``plan.yaml`` key, each carrying how it is written - the one place a tool
    spells one.

    A member *is* a :class:`KeySpecification`, so ``isinstance`` and ``issubclass`` hold
    and a key's own style is reached directly: ``ManifestKey.TITLE.style``. That is what
    lets :meth:`render` produce a correct line from the key alone - a caller never
    chooses quoting, and every assertion about a manifest line derives from the same
    place the line is written. The schema itself is documented in ``plan-schema.md``.

    .. note::
       A member's value is the argument tuple its specification is built from, not a
       built :class:`KeySpecification`. Passing an instance is accepted silently by the
       enum machinery and lands the whole instance in :attr:`KeySpecification.key`, so a
       test asserts every key is a string.
    """

    IDENTIFIER = ("id",)
    """
    The item's own id, and the line that opens its block.
    """

    TITLE = ("title", ValueStyle.DOUBLE_QUOTED)
    """
    What the item does, quoted because it is prose.
    """

    BRANCH = ("branch",)
    """
    The git branch the work happens on, once one exists.
    """

    REPOSITORY = ("repository",)
    """
    The item's own repository, overriding the plan's default.
    """

    DEFAULT_REPOSITORY = ("default_repository",)
    """
    The repository every item uses unless it sets its own.
    """

    PULL_REQUEST_NUMBER = ("pull_request_number",)
    """
    The real pull request number, once one exists.
    """

    TRACK = ("track",)
    """
    The parallel line of work the item belongs to.
    """

    DEPENDS_ON = ("depends_on",)
    """
    The items this one stacks on, by id.
    """

    STATUS = ("status",)
    """
    The session's own planning assessment - see :class:`ItemStatus`.
    """

    SESSION = ("session",)
    """
    The session doing the work.
    """

    NOTES = ("notes", ValueStyle.BLOCK)
    """
    Freeform detail, routinely folded over many lines.
    """

    BLOCKERS = ("blockers", ValueStyle.BLOCK)
    """
    Why the item is stuck, written as a sequence.
    """

    ITEMS = ("items",)
    """
    The manifest's top-level list of items.
    """

    DESCRIPTION = ("description",)
    """
    What the plan is for.
    """

    TRACKING_ISSUE = ("tracking_issue",)
    """
    The issue structural changes to the plan are recorded on.
    """

    SCHEMA_VERSION = ("schema_version",)
    """
    The version of the schema the manifest is written against.
    """

    WAVES = ("waves",)
    """
    The plan's sequential phases.
    """

    TRACKS = ("tracks",)
    """
    The plan's parallel lines of work.
    """

    NAME = ("name",)
    """
    A wave's or a track's display name.
    """

    WAVE = ("wave",)
    """
    The wave a track belongs to.
    """

    def render(
        self,
        value: str,
        opening_the_item: bool = False,
        field_indent: str = ItemLayout.FIELD_INDENT.value,
    ) -> str:
        """
        The manifest line setting this key to *value*, newline included.

        Quoting comes from the key's own style rather than from the caller.

        :param value: The value to write.
        :param opening_the_item: Whether this is the item block's first line, which
            carries the list marker instead of the key indent.
        :param field_indent: The whitespace this item's own fields are indented by,
            read from the block being edited rather than assumed, since a manifest
            written before this module's own convention keeps whichever indentation
            it already has.
        :return: The rendered line.
        """
        prefix = ItemLayout.MARKER.value if opening_the_item else field_indent
        written = f'"{value}"' if self.style is ValueStyle.DOUBLE_QUOTED else value
        return f"{prefix}{self.key}: {written}\n"

    @property
    def pattern(self) -> re.Pattern[str]:
        """
        Matches this key wherever it already appears in an item block.
        """
        return re.compile(rf"^\s*{re.escape(self.key)}:\s*.*$")

    @property
    def is_block_styled(self) -> bool:
        """
        Whether this key's value runs over the lines beneath it.
        """
        return self.style is ValueStyle.BLOCK

    @classmethod
    def block_styled(cls) -> frozenset[ManifestKey]:
        """
        The keys whose values run over the lines beneath them, derived from the keys
        themselves rather than listed a second time.

        :return: Every block-styled key.
        """
        return frozenset(
            manifest_key for manifest_key in cls if manifest_key.is_block_styled
        )


# %% manifest reading


@dataclass(frozen=True)
class PlanItem:
    """
    One entry of a manifest's ``items`` list.
    """

    content: dict[str, Any]
    """
    The entry as parsed, every key kept so that writing it back loses nothing.
    """

    @property
    def identifier(self) -> str:
        """
        :return: The item's id.
        """
        return str(self.content[ManifestKey.IDENTIFIER.key])

    @property
    def status(self) -> ItemStatus:
        """
        :return: The item's status.
        """
        return ItemStatus(self.content[ManifestKey.STATUS.key])

    @property
    def notes(self) -> str:
        """
        :return: The item's notes with their line folding undone, empty when it has none.
        """
        return " ".join(str(self.content.get(ManifestKey.NOTES.key) or "").split())

    @property
    def blockers(self) -> list[str]:
        """
        :return: Each blocker with its line folding undone.
        """
        return [
            " ".join(str(blocker).split())
            for blocker in self.content.get(ManifestKey.BLOCKERS.key) or []
        ]

    @property
    def dependencies(self) -> list[str]:
        """
        :return: The ids of the items this one builds on.
        """
        return [
            str(dependency)
            for dependency in self.content.get(ManifestKey.DEPENDS_ON.key) or []
        ]

    def without_dependencies(self, identifiers: set[str]) -> PlanItem:
        """
        :param identifiers: Item ids to stop depending on.
        :return: This item with every dependency on *identifiers* removed.
        """
        if not identifiers & set(self.dependencies):
            return self
        remaining = [
            dependency
            for dependency in self.dependencies
            if dependency not in identifiers
        ]
        return PlanItem({**self.content, ManifestKey.DEPENDS_ON.key: remaining})


class ItemSummaryKey(StrEnum):
    """
    The keys an item summary adds to the plan fields it copies.
    """

    ITEM = "item"
    """
    The item's own entry.
    """


@dataclass(frozen=True)
class PlanManifest:
    """
    A parsed ``plan.yaml``.
    """

    content: dict[str, Any]
    """
    The manifest as parsed, every key kept so that writing it back loses nothing.
    """

    @classmethod
    def from_file(cls, path: Path) -> PlanManifest:
        """
        :param path: A ``plan.yaml`` file.
        :return: The manifest it holds.
        """
        return cls(yaml.safe_load(path.read_text()) or {})

    def write(self, path: Path) -> None:
        """
        Write the manifest in block style, keeping its keys in their order.

        :param path: Where to write it.
        """
        path.write_text(
            yaml.safe_dump(self.content, sort_keys=False, allow_unicode=True, width=88)
        )

    @property
    def identifier(self) -> str:
        """
        :return: The plan's id.
        """
        return str(self.content[ManifestKey.IDENTIFIER.key])

    @property
    def description(self) -> str:
        """
        :return: The plan's description with its line folding undone.
        """
        return " ".join(
            str(self.content.get(ManifestKey.DESCRIPTION.key) or "").split()
        )

    @property
    def items(self) -> list[PlanItem]:
        """
        :return: The plan's items, in manifest order.
        """
        return [
            PlanItem(item) for item in self.content.get(ManifestKey.ITEMS.key) or []
        ]

    @property
    def landed_identifiers(self) -> set[str]:
        """
        :return: The ids of the items whose work has landed.
        """
        return {
            item.identifier for item in self.items if item.status is ItemStatus.DONE
        }

    def item_named(self, identifier: str) -> PlanItem:
        """
        :param identifier: The id of the item to return.
        :raises ItemNotTrackedError: If the plan has no item with that id.
        :return: The item with that id.
        """
        for item in self.items:
            if item.identifier == identifier:
                return item
        raise ItemNotTrackedError(
            plan_identifier=self.identifier, item_identifier=identifier
        )

    def item_on_branch(self, branch: str) -> PlanItem:
        """
        :param branch: The branch whose item to return.
        :raises ItemNotTrackedError: If no item of the plan is worked on that branch.
        :return: The item worked on that branch.
        """
        for item in self.items:
            if item.content.get(ManifestKey.BRANCH.key) == branch:
                return item
        raise ItemNotTrackedError(
            plan_identifier=self.identifier, item_identifier=branch
        )

    def item_summary(self, item: PlanItem) -> str:
        """
        The part of the plan one item's session needs: the plan's id, title and
        tracking issue, and that item's own entry.

        :param item: The item to summarize.
        :return: The summary as YAML.
        """
        summary = {
            field_name.key: self.content.get(field_name.key)
            for field_name in (
                ManifestKey.IDENTIFIER,
                ManifestKey.TITLE,
                ManifestKey.TRACKING_ISSUE,
            )
        }
        summary[ItemSummaryKey.ITEM.value] = item.content
        return yaml.safe_dump(summary, sort_keys=False, allow_unicode=True, width=88)

    def without_landed_items(self) -> PlanManifest:
        """
        A landed item tells a future session nothing it needs: its work is in the code
        and its history in git. Dropping it also drops every dependency on it, since a
        dependency that has landed is already satisfied.

        :return: This manifest with every landed item removed.
        """
        landed = self.landed_identifiers
        remaining = [
            item.without_dependencies(landed).content
            for item in self.items
            if item.identifier not in landed
        ]
        return PlanManifest({**self.content, ManifestKey.ITEMS.key: remaining})


@dataclass
class ItemNotTrackedError(LookupError):
    """
    Raised when a plan is asked for an item it does not track.
    """

    plan_identifier: str
    """
    The plan that was searched.
    """

    item_identifier: str
    """
    The id, or the branch, that matched no item.
    """

    def __str__(self) -> str:
        """
        :return: Which item was missing from which plan.
        """
        return f"plan {self.plan_identifier!r} has no item {self.item_identifier!r}"
