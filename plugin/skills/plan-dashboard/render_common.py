"""
Shared, dependency-free rendering helpers for the plan-dashboard scripts.

No plan-specific content belongs here - this module only knows how to turn
generic markdown into HTML fragments. build_dashboard.py and build_index.py
both import it rather than duplicating the logic.
"""

from __future__ import annotations

import html
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


def escape_html(value: object) -> str:
    """
    HTML-escape a value.

    :param value: The value to escape. Rendered via ``str()`` first; ``None`` becomes an
        empty string rather than the literal ``"None"``.
    :return: The HTML-escaped string.
    """
    return html.escape(str(value)) if value is not None else ""


def render_inline_markdown(text: str) -> str:
    """
    Render a single line of minimal inline markdown to HTML.

    Supports links, bold, italic and inline code - not a full CommonMark
    implementation, deliberately just enough for a plan's roadmap.md, which
    is plain prose/lists/tables, not full Markdown with nested emphasis or
    reference-style links.

    :param text: The raw markdown line (not yet HTML-escaped).
    :return: The rendered HTML fragment.
    """
    text = escape_html(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2" target="_blank" rel="noopener">\1</a>',
        text,
    )
    return text


class MarkdownBlock(ABC):
    """
    A single block-level markdown element, able to render itself to HTML.

    Polymorphic rendering (one ``render_to_html`` per concrete block type) replaces a
    central dispatch-by-tag switch, so adding a new block kind never means touching
    every other block's rendering code.
    """

    @abstractmethod
    def render_to_html(self) -> str:
        """
        Render this block to its HTML representation.
        """


@dataclass
class Heading(MarkdownBlock):
    """
    A markdown heading (``#`` through ``######``).
    """

    level: int
    """
    The number of leading ``#`` characters (1-6) in the source markdown.
    """

    text: str
    """
    The heading's raw (not yet HTML-escaped) text.
    """

    def render_to_html(self) -> str:
        # +3, capped at 6: a roadmap's own h1 renders as the embedding
        # dashboard page's h4, staying below the dashboard's own h1-h3.
        heading_level = min(self.level + 3, 6)
        rendered_text = render_inline_markdown(self.text)
        return f"<h{heading_level}>{rendered_text}</h{heading_level}>"


@dataclass
class Paragraph(MarkdownBlock):
    """
    A paragraph: one or more wrapped source lines joined into one block.
    """

    lines: list[str] = field(default_factory=list)
    """
    The paragraph's source lines, joined with a space at render time.
    """

    def render_to_html(self) -> str:
        return "<p>" + render_inline_markdown(" ".join(self.lines)) + "</p>"


@dataclass
class UnorderedList(MarkdownBlock):
    """
    A bullet (``-``/``*``) list.
    """

    items: list[str] = field(default_factory=list)
    """
    Each list item's raw text, one wrapped-continuation-joined string per item.
    """

    def render_to_html(self) -> str:
        list_items = "".join(
            f"<li>{render_inline_markdown(item)}</li>" for item in self.items
        )
        return f"<ul>{list_items}</ul>"


@dataclass
class OrderedList(MarkdownBlock):
    """
    A numbered (``1.``, ``2.``, ...) list.
    """

    items: list[str] = field(default_factory=list)
    """
    Each list item's raw text, one wrapped-continuation-joined string per item.
    """

    def render_to_html(self) -> str:
        list_items = "".join(
            f"<li>{render_inline_markdown(item)}</li>" for item in self.items
        )
        return f"<ol>{list_items}</ol>"


@dataclass
class CodeBlock(MarkdownBlock):
    """
    A fenced (``` ```) code block, rendered verbatim (no syntax highlighting).
    """

    lines: list[str] = field(default_factory=list)
    """
    The code block's raw source lines, escaped but otherwise unmodified.
    """

    def render_to_html(self) -> str:
        return "<pre><code>" + escape_html("\n".join(self.lines)) + "</code></pre>"


@dataclass
class Table(MarkdownBlock):
    """
    A GitHub-flavored-markdown pipe table.
    """

    header_cells: list[str]
    """
    The header row's cell texts, in column order.
    """

    rows: list[list[str]]
    """
    The body rows, each a list of cell texts in column order.
    """

    def render_to_html(self) -> str:
        header_row = (
            "<tr>"
            + "".join(
                f"<th>{render_inline_markdown(cell)}</th>" for cell in self.header_cells
            )
            + "</tr>"
        )
        body_rows = "".join(
            "<tr>"
            + "".join(f"<td>{render_inline_markdown(cell)}</td>" for cell in row)
            + "</tr>"
            for row in self.rows
        )
        return f'<div class="roadmap-table-wrap"><table><thead>{header_row}</thead><tbody>{body_rows}</tbody></table></div>'


class _MarkdownBlockParser:
    """
    Parses plain-text markdown into a list of :class:`MarkdownBlock` objects.

    Not full CommonMark - see :func:`render_inline_markdown` for the same
    trade-off on inline formatting. Continuation lines (a paragraph or list
    item wrapped across multiple source lines, ended by a blank line or a
    new block starting) are joined into their block *before* inline
    formatting runs, so a ``**bold**`` span or a list item's sentence can
    cross a wrapped line without breaking.
    """

    _HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
    _TABLE_HEADER_PATTERN = re.compile(r"^\s*\|(.+)\|\s*$")
    _TABLE_SEPARATOR_PATTERN = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")
    _TABLE_ROW_PATTERN = re.compile(r"^\s*\|(.+)\|\s*$")
    _BULLET_PATTERN = re.compile(r"^\s*[-*]\s+(.*)$")
    _NUMBERED_PATTERN = re.compile(r"^\s*\d+\.\s+(.*)$")

    def __init__(self, markdown_text: str) -> None:
        self._lines = markdown_text.split("\n")
        self._blocks: list[MarkdownBlock] = []
        self._open_block: MarkdownBlock | None = None

    def parse(self) -> list[MarkdownBlock]:
        """
        Parse the full input and return its blocks in source order.
        """
        line_index = 0
        while line_index < len(self._lines):
            line_index = self._parse_one_line(line_index)
        self._close_open_block()
        return self._blocks

    def _parse_one_line(self, line_index: int) -> int:
        line = self._lines[line_index]
        stripped_line = line.rstrip()

        if stripped_line.startswith("```"):
            return self._parse_code_fence(line_index)
        if isinstance(self._open_block, CodeBlock):
            self._open_block.lines.append(line)
            return line_index + 1

        heading_match = self._HEADING_PATTERN.match(stripped_line)
        if heading_match:
            self._close_open_block()
            self._blocks.append(
                Heading(level=len(heading_match.group(1)), text=heading_match.group(2))
            )
            return line_index + 1

        table_end_index = self._try_parse_table(line_index, stripped_line)
        if table_end_index is not None:
            return table_end_index

        if not stripped_line:
            self._close_open_block()
            return line_index + 1

        bullet_match = self._BULLET_PATTERN.match(line)
        if bullet_match:
            self._append_list_item(UnorderedList, bullet_match.group(1))
            return line_index + 1

        numbered_match = self._NUMBERED_PATTERN.match(line)
        if numbered_match:
            self._append_list_item(OrderedList, numbered_match.group(1))
            return line_index + 1

        self._append_continuation_or_paragraph(stripped_line)
        return line_index + 1

    def _parse_code_fence(self, line_index: int) -> int:
        if isinstance(self._open_block, CodeBlock):
            self._close_open_block()
        else:
            self._close_open_block()
            self._open_block = CodeBlock()
        return line_index + 1

    def _try_parse_table(self, line_index: int, stripped_line: str) -> int | None:
        is_table_header = self._TABLE_HEADER_PATTERN.match(stripped_line)
        has_separator_row = (
            line_index + 1 < len(self._lines)
            and self._TABLE_SEPARATOR_PATTERN.match(self._lines[line_index + 1].strip())
            and "-" in self._lines[line_index + 1]
        )
        if not (is_table_header and has_separator_row):
            return None

        self._close_open_block()
        header_cells = [cell.strip() for cell in is_table_header.group(1).split("|")]
        rows: list[list[str]] = []
        next_line_index = (
            line_index + 2
        )  # skip the header row and the --- separator row
        while next_line_index < len(self._lines) and self._TABLE_ROW_PATTERN.match(
            self._lines[next_line_index].rstrip()
        ):
            row_cells = [
                cell.strip()
                for cell in self._lines[next_line_index].strip().strip("|").split("|")
            ]
            rows.append(row_cells)
            next_line_index += 1
        self._blocks.append(Table(header_cells=header_cells, rows=rows))
        return next_line_index

    def _append_list_item(
        self, list_type: type[UnorderedList] | type[OrderedList], item_text: str
    ) -> None:
        if isinstance(self._open_block, list_type):
            self._open_block.items.append(item_text)
        else:
            self._close_open_block()
            self._open_block = list_type(items=[item_text])

    def _append_continuation_or_paragraph(self, stripped_line: str) -> None:
        # .strip(), not just the already-rstripped stripped_line: a
        # continuation line indented to align under its list marker (a
        # common markdown style) must not leak that leading whitespace into
        # the joined text as literal double spaces.
        content = stripped_line.strip()
        if isinstance(self._open_block, (UnorderedList, OrderedList)):
            self._open_block.items[-1] += " " + content
        elif isinstance(self._open_block, Paragraph):
            self._open_block.lines.append(content)
        else:
            self._close_open_block()
            self._open_block = Paragraph(lines=[content])

    def _close_open_block(self) -> None:
        if self._open_block is not None:
            self._blocks.append(self._open_block)
            self._open_block = None


def render_markdown_to_html(markdown_text: str) -> str:
    """
    Render block-level markdown (headings, lists, code, GFM tables) to HTML.

    :param markdown_text: The raw markdown source (typically a plan's ``roadmap.md``).
    :return: The rendered HTML, one block's output per line.
    """
    blocks = _MarkdownBlockParser(markdown_text).parse()
    return "\n".join(block.render_to_html() for block in blocks)
