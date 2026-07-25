"""
Shared rendering helpers for the plan-dashboard scripts.

No plan-specific content belongs here - this module only knows how to (a)
build the Jinja2 environment every page template renders through and (b)
turn generic markdown into HTML. build_dashboard.py and build_index.py both
import it rather than duplicating the logic.
"""

from __future__ import annotations

import re
from pathlib import Path

import jinja2
import markdown as markdown_library

TEMPLATES_DIRECTORY = Path(__file__).parent / "templates"
"""
Where every page template (dashboard.html, index.html) lives.
"""

_HEADING_TAG_PATTERN = re.compile(r"<(/?)h([1-6])>")
_HEADING_LEVEL_SHIFT = 3
_MAXIMUM_HEADING_LEVEL = 6


def create_template_environment() -> jinja2.Environment:
    """
    Build the Jinja2 environment every page template renders through.

    Autoescaping is on for every value substituted into a template - the
    one deliberately unescaped value either script ever passes in
    (already-rendered roadmap markdown HTML) is marked with Jinja2's
    ``| safe`` filter at its point of use in the template itself, rather
    than disabling escaping globally and trusting every call site to
    remember to escape by hand.

    :return: A configured, ready-to-use Jinja2 environment.
    """
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATES_DIRECTORY),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_markdown_to_html(markdown_text: str) -> str:
    """
    Render GitHub-flavored markdown (headings, lists, code, tables) to HTML.

    Delegates to the ``markdown`` library (with its ``tables`` and
    ``fenced_code`` extensions) rather than a hand-rolled parser.

    :param markdown_text: The raw markdown source (typically a plan's
        ``roadmap.md``).
    :return: The rendered HTML. Callers embedding this into a Jinja2
        template must mark it ``| safe`` - it is HTML, not text to escape.
    """
    html_text = markdown_library.markdown(
        markdown_text, extensions=["tables", "fenced_code"]
    )
    return _HEADING_TAG_PATTERN.sub(_shift_heading_level, html_text)


def _shift_heading_level(heading_tag_match: re.Match[str]) -> str:
    """
    Shift one ``<h1>``-``<h6>`` tag match down by :data:`_HEADING_LEVEL_SHIFT`.

    Used as the substitution callback for :data:`_HEADING_TAG_PATTERN`, so a
    roadmap's own ``<h1>`` renders as the embedding dashboard page's
    ``<h4>``, staying below the dashboard's own h1-h3 - capped at h6 so a
    deeply-nested roadmap heading never overflows past the last valid level.

    :param heading_tag_match: A match of :data:`_HEADING_TAG_PATTERN` -
        group 1 is ``"/"`` for a closing tag or ``""`` for an opening one,
        group 2 is the original heading level.
    :return: The tag with its level shifted.
    """
    closing_slash, original_level = heading_tag_match.group(1), int(
        heading_tag_match.group(2)
    )
    shifted_level = min(original_level + _HEADING_LEVEL_SHIFT, _MAXIMUM_HEADING_LEVEL)
    return f"<{closing_slash}h{shifted_level}>"
