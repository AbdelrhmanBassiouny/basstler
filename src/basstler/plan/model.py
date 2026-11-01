"""
The parts of a plan's data model that more than one tool has to agree on.

Nothing here imports anything the tools reading it do not already have: the plan site's
build imports jinja2 and markdown of its own, and the bootstrap tool imports neither.
The dependency runs one way only.
"""

from __future__ import annotations

import re
import sys
import textwrap
from dataclasses import dataclass
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any

import yaml

from basstler.locations import ProjectLocation
from basstler.repository import Repository


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


class PlanDocument(StrEnum):
    """
    The two files a plan is kept in, beside each other on the personal-notes branch.
    """

    MANIFEST = "plan.yaml"
    """
    The structured manifest, whose schema ``plan-schema.md`` documents.
    """

    ROADMAP = "roadmap.md"
    """
    The narrative companion, a fixed sibling filename rather than a configurable one.
    """

    def path_within_notes_branch(self, plan_identifier: str) -> str:
        """
        Where this document lives for one plan.

        :param plan_identifier: The plan's id.
        :return: The path, relative to the personal-notes branch's root.
        """
        return str(ProjectLocation.PLANS / plan_identifier / self.value)


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

    NESTING_STEP = " " * 2
    """
    One level of YAML indentation, which separates a key from the lines its own value
    occupies beneath it.
    """


@dataclass(frozen=True)
class ItemIndentation:
    """
    How far one manifest's item blocks are indented, read off the manifest rather than
    assumed, since YAML admits items flush with ``items:`` as well as one level in.
    """

    marker: str = ItemLayout.MARKER.value
    """
    What opens an item block: the whitespace before the list marker, and the marker.
    """

    field_indent: str = ItemLayout.FIELD_INDENT.value
    """
    The whitespace an item's own fields are indented by.
    """

    @property
    def nested(self) -> str:
        """
        What a line of a value written beneath its own key begins with - a sequence
        entry's dash, or a folded scalar's body.
        """
        return self.field_indent + ItemLayout.NESTING_STEP


@dataclass(frozen=True)
class Prose:
    """
    Text as its author wrote it, about to be written as the body of a folded scalar.

    A blank line separates paragraphs; a single newline is a hard-wrapped line within
    one, which is how a person writes the file a value comes from.
    """

    text: str
    """
    The text, as its author wrote it.
    """

    line_width: int = 100
    """
    The column a wrapped body line is kept under.
    """

    @property
    def paragraphs(self) -> list[str]:
        """
        The paragraphs the text breaks into, stripped.

        A hyphen immediately before a wrapped line break closes up rather than becoming
        a space, since that is where its author wrapped a word they wrote whole -
        ``blank-\\nline`` is *blank-line*. A suspended hyphen typed on one line keeps its
        space.
        """
        return [
            re.sub(r"-\n", "-", paragraph.strip())
            for paragraph in re.split(r"\n\s*\n", self.text.strip())
        ]

    def folded(self, indent: str) -> str:
        """
        Wrap the text as the body of a folded scalar, breaking only between words.

        A folded scalar reads a line break back as a space, so a break inside a word
        would return a different string than it was given; a word wider than the column
        overflows it instead.

        :param indent: The indentation every body line carries.
        :return: The body's lines, its paragraphs separated by blank lines,
            newline-terminated.
        """
        wrapped = [
            textwrap.fill(
                paragraph,
                width=self.line_width,
                initial_indent=indent,
                subsequent_indent=indent,
                break_long_words=False,
                break_on_hyphens=False,
            )
            for paragraph in self.paragraphs
        ]
        return "\n\n".join(wrapped) + "\n"


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
    A folded scalar, written across the lines beneath the key.

    Anything inserted after such a key would be swallowed by its value, so a new key
    goes before the first block-styled one in an item rather than at the end.
    """

    SEQUENCE = "sequence"
    """
    A list, one entry per dash beneath the key.

    Spans the lines beneath the key exactly as :attr:`BLOCK` does. A list with no
    entries is written inline as ``[]``, since a key with nothing beneath it parses as
    null rather than as an empty list.
    """

    @property
    def spans_lines_beneath(self) -> bool:
        """
        Whether this style's value continues below the key's own line.
        """
        return self in {ValueStyle.BLOCK, ValueStyle.SEQUENCE}


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

    DEPENDS_ON = ("depends_on", ValueStyle.SEQUENCE)
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

    BLOCKERS = ("blockers", ValueStyle.SEQUENCE)
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
        value: Any,
        opening_the_item: bool = False,
        indentation: ItemIndentation = ItemIndentation(),
    ) -> str:
        """
        The manifest text setting this key to *value*, newline-terminated.

        How the value is written comes from the key's own style rather than from the
        caller, so a style that spans the lines beneath the key returns those lines too.
        Every value reads back as exactly what it was given.

        :param value: The value to write: a sequence of strings for a sequence-styled
            key, otherwise a scalar in the type it is to be read back as.
        :param opening_the_item: Whether this is the item block's first line, which
            carries the list marker instead of the key indent.
        :param indentation: How the manifest being edited indents its items.
        :return: The rendered text.
        """
        prefix = indentation.marker if opening_the_item else indentation.field_indent
        if self.style is ValueStyle.SEQUENCE:
            if not value:
                return f"{prefix}{self.key}: []\n"
            entries = "".join(
                self.render_sequence_entry(str(entry), indentation) for entry in value
            )
            return f"{prefix}{self.key}:\n{entries}"
        if self.style is ValueStyle.BLOCK:
            return (
                f"{prefix}{self.key}: >\n{Prose(str(value)).folded(indentation.nested)}"
            )
        return f"{prefix}{self.render_scalar(value)}\n"

    def render_scalar(self, value: Any) -> str:
        """
        One ``key: value`` line, quoted however YAML needs it to read back as *value*.

        A double-quoted key asks for that style outright; every other key leaves the
        quoting to the dumper, which knows that a space before ``#`` opens a comment and
        a trailing colon opens a mapping.

        :param value: The value to write.
        :return: The line, without its indentation or its newline.
        """
        written = str(value) if isinstance(value, str) else value
        if self.style is ValueStyle.DOUBLE_QUOTED:
            quoted = yaml.safe_dump(
                str(written), default_style='"', width=sys.maxsize, allow_unicode=True
            )
            return f"{self.key}: {quoted.rstrip()}"
        return yaml.safe_dump(
            {self.key: written},
            default_flow_style=False,
            width=sys.maxsize,
            allow_unicode=True,
            sort_keys=False,
        ).rstrip("\n")

    @staticmethod
    def render_sequence_entry(entry: str, indentation: ItemIndentation) -> str:
        """
        One entry of a sequence-styled value, newline-terminated.

        An entry that fits on its own line is written as a quoted scalar and a longer
        one as a folded block stripping its trailing newline (``>-``), so it parses back
        as exactly the string it was given.

        :param entry: The entry's text.
        :param indentation: How the manifest the entry is written into indents its
            items.
        :return: The entry's lines.
        """
        prose = Prose(entry)
        quoted = f'{indentation.nested}- "{entry}"'
        fits_one_line = "\n" not in entry and len(quoted) <= prose.line_width
        if fits_one_line and '"' not in entry and "\\" not in entry:
            return f"{quoted}\n"
        body = prose.folded(indentation.nested + ItemLayout.NESTING_STEP)
        return f"{indentation.nested}- >-\n{body}"

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
        return self.style.spans_lines_beneath

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
    def branch(self) -> str | None:
        """
        :return: The branch the item's work happens on, or ``None`` when it has none yet.
        """
        return self.content.get(ManifestKey.BRANCH.key)

    @property
    def session(self) -> str | None:
        """
        :return: The session doing the item's work, or ``None`` when none is recorded.
        """
        return self.content.get(ManifestKey.SESSION.key)

    @property
    def pull_request_number(self) -> int | None:
        """
        :return: The number of the item's pull request, or ``None`` when it has none yet.
        """
        return self.content.get(ManifestKey.PULL_REQUEST_NUMBER.key)

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
    def default_repository(self) -> Repository:
        """
        :return: The repository every item's pull request is on unless it names its own.
        """
        return Repository.parse(self.content[ManifestKey.DEFAULT_REPOSITORY.key])

    def repository_of(self, item: PlanItem) -> Repository:
        """
        :param item: An item of this plan.
        :return: The repository the item's pull request is on: its own, else the plan's
            default.
        """
        own_repository = item.content.get(ManifestKey.REPOSITORY.key)
        if not own_repository:
            return self.default_repository
        return Repository.parse(own_repository)

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

    def item_header(self, item: PlanItem) -> dict[str, Any]:
        """
        The part of the plan one item's session needs: the plan's id, title and
        tracking issue, and that item's own entry.

        :param item: The item to summarize.
        :return: The summary, keyed as the manifest keys it.
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
        return summary

    def item_summary(self, item: PlanItem) -> str:
        """
        :param item: The item to summarize.
        :return: :meth:`item_header` as YAML.
        """
        return self.summary_text(self.item_header(item))

    @staticmethod
    def summary_text(summary: dict[str, Any]) -> str:
        """
        :param summary: A summary of part of a plan.
        :return: The summary as YAML, in block style with its keys in their order.
        """
        return yaml.safe_dump(summary, sort_keys=False, allow_unicode=True, width=88)

    def without_dependencies(self, identifiers: set[str]) -> PlanManifest:
        """
        :param identifiers: ``depends_on`` entries to stop depending on.
        :return: This manifest with every item's dependency on *identifiers* removed.
        """
        return PlanManifest(
            {
                **self.content,
                ManifestKey.ITEMS.key: [
                    item.without_dependencies(identifiers).content
                    for item in self.items
                ],
            }
        )

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
