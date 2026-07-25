"""
Tests for render_common.py's markdown-to-HTML rendering.
"""

from render_common import escape_html, render_inline_markdown, render_markdown_to_html

# %% escape_html


def test_escape_html_escapes_special_characters():
    assert escape_html("<script>") == "&lt;script&gt;"


def test_escape_html_treats_none_as_empty_string():
    assert escape_html(None) == ""


def test_escape_html_stringifies_non_string_values():
    assert escape_html(42) == "42"


# %% render_inline_markdown


def test_render_inline_markdown_renders_bold_italic_code_and_links():
    rendered = render_inline_markdown(
        "**bold** *italic* `code` [text](https://example.com)"
    )
    assert "<strong>bold</strong>" in rendered
    assert "<em>italic</em>" in rendered
    assert "<code>code</code>" in rendered
    assert (
        '<a href="https://example.com" target="_blank" rel="noopener">text</a>'
        in rendered
    )


def test_render_inline_markdown_escapes_html_before_formatting():
    assert render_inline_markdown("<b>raw</b>") == "&lt;b&gt;raw&lt;/b&gt;"


# %% render_markdown_to_html - block structure


def test_heading_level_is_shifted_and_capped():
    # h1 -> h4 (shifted by 3), h6 -> h6 (capped, not h9)
    assert render_markdown_to_html("# Title") == "<h4>Title</h4>"
    assert render_markdown_to_html("###### Deep") == "<h6>Deep</h6>"


def test_paragraph_joins_wrapped_continuation_lines():
    rendered = render_markdown_to_html("This is a\nwrapped paragraph.")
    assert rendered == "<p>This is a wrapped paragraph.</p>"


def test_blank_line_separates_paragraphs():
    rendered = render_markdown_to_html("First.\n\nSecond.")
    assert rendered == "<p>First.</p>\n<p>Second.</p>"


def test_unordered_list_with_wrapped_item():
    rendered = render_markdown_to_html("- first item\n  continues here\n- second item")
    assert rendered == "<ul><li>first item continues here</li><li>second item</li></ul>"


def test_ordered_list():
    rendered = render_markdown_to_html("1. one\n2. two")
    assert rendered == "<ol><li>one</li><li>two</li></ol>"


def test_fenced_code_block_is_not_interpreted_as_markdown():
    rendered = render_markdown_to_html("```\n**not bold**\n```")
    assert rendered == "<pre><code>**not bold**</code></pre>"


def test_gfm_table_renders_header_and_rows():
    markdown_text = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"
    rendered = render_markdown_to_html(markdown_text)
    assert "<th>A</th><th>B</th>" in rendered
    assert "<td>1</td><td>2</td>" in rendered
    assert "<td>3</td><td>4</td>" in rendered


def test_mixed_blocks_render_in_source_order():
    markdown_text = "# Title\n\nParagraph.\n\n- item"
    rendered = render_markdown_to_html(markdown_text)
    assert rendered == "<h4>Title</h4>\n<p>Paragraph.</p>\n<ul><li>item</li></ul>"
