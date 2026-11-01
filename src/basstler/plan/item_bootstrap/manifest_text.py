"""
Patching one item's fields in a manifest's raw text.
"""

from __future__ import annotations

import itertools

from dataclasses import dataclass
from typing import Any

from basstler.plan.item_bootstrap.exceptions import UnknownItemError
from basstler.plan.item_bootstrap.vocabulary import (
    BlockScalarStyle,
    ManifestLinePattern,
)
from basstler.plan.model import (
    ItemIndentation,
    ManifestKey,
    ValueStyle,
)

# %% patching one item's fields


@dataclass
class ManifestText:
    """
    A manifest's raw lines, patched by line so every untouched line survives byte for
    byte: comments, key order, string wrapping and quoting.
    """

    lines: list[str]
    """
    The manifest, split into lines.
    """

    @classmethod
    def from_text(cls, manifest_text: str) -> ManifestText:
        """
        :param manifest_text: The manifest's raw text.
        :return: The manifest, split into lines.
        """
        return cls(lines=manifest_text.split("\n"))

    @property
    def text(self) -> str:
        """
        The manifest's raw text.
        """
        return "\n".join(self.lines)

    def item_block_bounds(self) -> list[tuple[int, int]]:
        """
        :return: The half-open line range of every item block, in manifest order.
        """
        starts = [
            index
            for index, line in enumerate(self.lines)
            if ManifestLinePattern.ITEM_START.matches(line)
        ]
        if not starts:
            return []
        end_of_items = next(
            (
                index
                for index in range(starts[-1] + 1, len(self.lines))
                if ManifestLinePattern.TOP_LEVEL_KEY.matches(self.lines[index])
            ),
            len(self.lines),
        )
        return list(itertools.pairwise([*starts, end_of_items]))

    def locate_item_block(
        self, plan_identifier: str, item_identifier: str
    ) -> tuple[int, int]:
        """
        Find one item's block.

        :param plan_identifier: The plan being edited, for the error message.
        :param item_identifier: The item's id.
        :raises UnknownItemError: If no block starts with that id.
        :return: The block's half-open line range.
        """
        block = self.item_block_named(item_identifier)
        if block is None:
            raise UnknownItemError(
                plan_identifier=plan_identifier, item_identifier=item_identifier
            )
        return block

    def item_block_named(self, item_identifier: str) -> tuple[int, int] | None:
        """
        :param item_identifier: The item's id.
        :return: The half-open line range of the block that starts with that id, or
            ``None`` when no block does.
        """
        opener = f"- {ManifestKey.IDENTIFIER.key}:"
        return next(
            (
                (start, end)
                for start, end in self.item_block_bounds()
                if self.lines[start].strip().removeprefix(opener).strip()
                == item_identifier
            ),
            None,
        )

    def top_level_section(self, key: str) -> tuple[int, int] | None:
        """
        :param key: A top-level manifest key.
        :return: The half-open line range from the key's line up to the next top-level
            key, or ``None`` when the manifest does not set the key.
        """
        starts = [
            index
            for index, line in enumerate(self.lines)
            if ManifestLinePattern.TOP_LEVEL_KEY.matches(line)
        ]
        return next(
            (
                (start, end)
                for start, end in itertools.pairwise([*starts, len(self.lines)])
                if self.lines[start].split(":", 1)[0] == key
            ),
            None,
        )

    def with_lines_replaced(
        self, bounds: tuple[int, int], replacement: list[str]
    ) -> str:
        """
        :param bounds: The half-open line range to replace.
        :param replacement: The lines to put in its place; empty removes the range.
        :return: The patched manifest text.
        """
        start, end = bounds
        return "\n".join(self.lines[:start] + replacement + self.lines[end:])

    def item_indentation(self, block: tuple[int, int] | None = None) -> ItemIndentation:
        """
        How this manifest indents its items, read off one item block so a written line
        lands beside its siblings and not under one.

        :param block: The half-open line range of the block to read, or ``None`` for the
            manifest's first item.
        :return: The block's indentation, or the default when the manifest has no item
            to read it from.
        """
        if block is None:
            bounds = self.item_block_bounds()
            if not bounds:
                return ItemIndentation()
            block = bounds[0]
        start, end = block
        opening = self.lines[start]
        marker = opening[: len(opening) - len(opening.lstrip(" "))] + "- "
        for line in self.lines[start + 1 : end]:
            if line.strip():
                return ItemIndentation(
                    marker=marker,
                    field_indent=line[: len(line) - len(line.lstrip(" "))],
                )
        return ItemIndentation(marker=marker, field_indent=" " * len(marker))

    def last_populated_line(self, start: int, end: int) -> int:
        """
        :param start: The block's first line.
        :param end: One past the block's last line.
        :return: The index of the block's last non-blank line.
        """
        return max(
            (index for index in range(start, end) if self.lines[index].strip()),
            default=start,
        )

    def with_item_fields(
        self,
        plan_identifier: str,
        item_identifier: str,
        values_by_key: dict[ManifestKey, Any],
    ) -> str:
        """
        Set each of *values_by_key* on one item, replacing every line an existing value
        occupies or inserting a new one.

        :param plan_identifier: The plan being edited.
        :param item_identifier: The item to patch.
        :param values_by_key: The value to write to each key, in insertion order, each
            in the form :meth:`ManifestKey.render` takes.
        :raises UnknownItemError: If the item has no block in the text.
        :return: The patched manifest text.
        """
        patched = ManifestText(lines=list(self.lines))
        lines = patched.lines
        start, end = patched.locate_item_block(plan_identifier, item_identifier)
        indentation = patched.item_indentation((start, end))
        for manifest_key, value in values_by_key.items():
            rendered = (
                manifest_key.render(value, indentation=indentation)
                .rstrip("\n")
                .split("\n")
            )
            existing = next(
                (
                    index
                    for index in range(start, end)
                    if manifest_key.pattern.match(lines[index])
                ),
                None,
            )
            if existing is not None:
                replaced = patched.value_end(existing, end, manifest_key)
                lines[existing:replaced] = rendered
                end += len(rendered) - (replaced - existing)
                continue
            insertion = next(
                (
                    index
                    for index in range(start, end)
                    if ManifestLinePattern.BLOCK_VALUE.matches(lines[index])
                ),
                patched.last_populated_line(start, end) + 1,
            )
            lines[insertion:insertion] = rendered
            end += len(rendered)
        return patched.text

    def value_end(self, key_line: int, end: int, manifest_key: ManifestKey) -> int:
        """
        One past the last line a key's value occupies.

        A value written beneath its key owns every following line indented past the key.
        A block sequence also owns the entries at the key's own depth, since YAML lets
        them sit flush with their key.

        :param key_line: The line the key sits on.
        :param end: One past the item block's last line.
        :param manifest_key: The key whose value is being measured.
        :return: One past the value's last line.
        """
        if not manifest_key.is_block_styled:
            return key_line + 1
        key_indent = self.indentation_width(self.lines[key_line])
        entries_sit_flush = manifest_key.style is ValueStyle.SEQUENCE
        last_value_line = key_line
        for index in range(key_line + 1, end):
            line = self.lines[index]
            if not line.strip():
                continue
            indent = self.indentation_width(line)
            if indent > key_indent:
                last_value_line = index
                continue
            if (
                indent < key_indent
                or not entries_sit_flush
                or not ManifestLinePattern.SEQUENCE_ENTRY.matches(line)
            ):
                break
            last_value_line = index
        return last_value_line + 1

    @staticmethod
    def indentation_width(line: str) -> int:
        """
        :param line: The line to measure.
        :return: How many columns its leading whitespace takes.
        """
        return len(line) - len(line.lstrip())

    def block_scalar_style(
        self, plan_identifier: str, item_identifier: str, manifest_key: ManifestKey
    ) -> BlockScalarStyle:
        """
        The style one item's key is written in, which parsing the manifest discards.

        :param plan_identifier: The plan being edited, for the error message.
        :param item_identifier: The item whose key to read.
        :param manifest_key: The key to read.
        :raises UnknownItemError: If the item has no block in the text.
        :return: :attr:`BlockScalarStyle.LITERAL` for a value opened with ``|``,
            otherwise :attr:`BlockScalarStyle.FOLDED`, which is also how a value written
            on the key's own line reads.
        """
        start, end = self.locate_item_block(plan_identifier, item_identifier)
        key_line = next(
            (
                line
                for line in self.lines[start:end]
                if manifest_key.pattern.match(line)
            ),
            None,
        )
        if key_line is None:
            return BlockScalarStyle.FOLDED
        indicator = key_line.split(":", 1)[1].strip()
        if indicator.startswith(BlockScalarStyle.LITERAL.value):
            return BlockScalarStyle.LITERAL
        return BlockScalarStyle.FOLDED

    def with_item(self, block: str) -> str:
        """
        Add a rendered item block after the manifest's last item.

        :param block: The block to append, as :meth:`ItemRecordRequest.render_new_item`
            renders it.
        :return: The extended manifest text.
        """
        bounds = self.item_block_bounds()
        insertion = bounds[-1][1] if bounds else len(self.lines)
        tail = "\n".join(self.lines[insertion:])
        head = "\n".join(self.lines[:insertion]).rstrip("\n")
        return f"{head}\n\n{block}{tail}"
