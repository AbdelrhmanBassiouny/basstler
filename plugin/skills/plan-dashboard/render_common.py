"""Shared, dependency-free rendering helpers for the plan-dashboard scripts.

No plan-specific content belongs here - this module only knows how to turn
generic markdown into HTML fragments. build_dashboard.py and build_index.py
both import it rather than duplicating the logic.
"""

import html
import re


def esc(value):
    """HTML-escape a value, treating None as an empty string."""
    return html.escape(str(value)) if value is not None else ''


def markdown_inline(text):
    """Minimal inline markdown: links, bold, italic, inline code.

    Not a full CommonMark implementation - deliberately just enough for a
    plan's roadmap.md, which is plain prose/lists/tables, not full Markdown
    with nested emphasis or reference-style links.
    """
    text = esc(text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)
    return text


def markdown_to_html(text):
    """Minimal block-level markdown: headings, paragraphs, unordered/ordered
    lists, fenced code, GFM tables. Not full CommonMark - see markdown_inline
    for the same trade-off on inline formatting.

    Continuation lines (a paragraph or list item wrapped across multiple
    source lines, ended by a blank line or a new block starting) are joined
    into their block BEFORE inline formatting runs, so a `**bold**` span or
    a list item's sentence can cross a wrapped line without breaking.
    """
    lines = text.split('\n')
    blocks = []  # ('heading', (level, text)) | ('para'|'ul'|'ol', [line, ...]) | ('code', [line, ...]) | ('table', (header_cells, rows))
    current = None

    def push_current():
        nonlocal current
        if current is not None:
            blocks.append(current)
            current = None

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()

        if stripped.startswith('```'):
            if current is not None and current[0] == 'code':
                push_current()
            else:
                push_current()
                current = ('code', [])
            i += 1
            continue
        if current is not None and current[0] == 'code':
            current[1].append(line)
            i += 1
            continue

        heading = re.match(r'^(#{1,6})\s+(.*)$', stripped)
        if heading:
            push_current()
            blocks.append(('heading', (len(heading.group(1)), heading.group(2))))
            i += 1
            continue

        table_header = re.match(r'^\s*\|(.+)\|\s*$', stripped)
        if (table_header and i + 1 < len(lines)
                and re.match(r'^\s*\|?[\s:|-]+\|?\s*$', lines[i + 1].strip())
                and '-' in lines[i + 1]):
            push_current()
            header_cells = [c.strip() for c in table_header.group(1).split('|')]
            rows = []
            i += 2  # skip the header row and the --- separator row
            while i < len(lines) and re.match(r'^\s*\|(.+)\|\s*$', lines[i].rstrip()):
                row_cells = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                rows.append(row_cells)
                i += 1
            blocks.append(('table', (header_cells, rows)))
            continue

        if not stripped:
            push_current()
            i += 1
            continue

        bullet = re.match(r'^\s*[-*]\s+(.*)$', line)
        if bullet:
            if current is not None and current[0] == 'ul':
                current[1].append(bullet.group(1))
            else:
                push_current()
                current = ('ul', [bullet.group(1)])
            i += 1
            continue

        numbered = re.match(r'^\s*\d+\.\s+(.*)$', line)
        if numbered:
            if current is not None and current[0] == 'ol':
                current[1].append(numbered.group(1))
            else:
                push_current()
                current = ('ol', [numbered.group(1)])
            i += 1
            continue

        # continuation of whatever block is open (list item or paragraph)
        if current is not None and current[0] in ('ul', 'ol'):
            current[1][-1] += ' ' + stripped
        elif current is not None and current[0] == 'para':
            current[1].append(stripped)
        else:
            push_current()
            current = ('para', [stripped])
        i += 1

    push_current()

    html_parts = []
    for kind, data in blocks:
        if kind == 'heading':
            level, heading_text = data
            level = min(level + 3, 6)  # roadmap h1 -> page h4, staying below the dashboard's own h1-h3
            html_parts.append(f'<h{level}>{markdown_inline(heading_text)}</h{level}>')
        elif kind == 'para':
            html_parts.append('<p>' + markdown_inline(' '.join(data)) + '</p>')
        elif kind in ('ul', 'ol'):
            items = ''.join(f'<li>{markdown_inline(item)}</li>' for item in data)
            html_parts.append(f'<{kind}>{items}</{kind}>')
        elif kind == 'code':
            html_parts.append('<pre><code>' + esc('\n'.join(data)) + '</code></pre>')
        elif kind == 'table':
            header_cells, rows = data
            thead = '<tr>' + ''.join(f'<th>{markdown_inline(c)}</th>' for c in header_cells) + '</tr>'
            tbody = ''.join(
                '<tr>' + ''.join(f'<td>{markdown_inline(c)}</td>' for c in row) + '</tr>'
                for row in rows
            )
            html_parts.append(f'<div class="roadmap-table-wrap"><table><thead>{thead}</thead><tbody>{tbody}</tbody></table></div>')

    return '\n'.join(html_parts)
