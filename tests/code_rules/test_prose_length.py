"""
Tests for :mod:`basstler.code_rules.prose_length`: finding docstrings and comment blocks
longer than a limit.
"""

from __future__ import annotations

from basstler.code_rules.prose_length import ProseLengthChecker, SourceProse

from ..constants.paths import ProseSnippet
from ..constants.source_lines import (
    FIELDS_AND_LITERAL_BLOCKS_PROSE_LINES,
    LONG_COMMENT_BLOCK_LINE,
    MODULE_FIRST_LINE,
    OVERLONG_ATTRIBUTE_DOCSTRING_LINE,
    OVERLONG_MODULE_DOCSTRING_PROSE_LINES,
)

# %% measuring


def overlong_first_lines(snippet: ProseSnippet) -> list[int]:
    """
    :return: The first line of each overlong block of *snippet*.
    """
    return [
        violation.first_line for violation in ProseLengthChecker().violations(snippet)
    ]


def test_a_docstring_over_its_limit_is_reported():
    """
    A module docstring of five prose lines breaks the four-line limit.
    """
    assert overlong_first_lines(ProseSnippet.OVERLONG_MODULE_DOCSTRING) == [
        MODULE_FIRST_LINE
    ]


def test_field_lists_and_literal_blocks_are_not_prose():
    """
    Only the summary and the line introducing the literal block count as prose.
    """
    (block,) = SourceProse(ProseSnippet.FIELDS_AND_LITERAL_BLOCKS.read_text()).blocks

    assert block.prose_lines == FIELDS_AND_LITERAL_BLOCKS_PROSE_LINES


def test_an_attribute_docstring_is_measured():
    """
    A docstring directly below a field is measured like any other.
    """
    assert overlong_first_lines(ProseSnippet.OVERLONG_ATTRIBUTE_DOCSTRING) == [
        OVERLONG_ATTRIBUTE_DOCSTRING_LINE
    ]


def test_a_comment_block_over_its_limit_is_reported_and_section_headers_are_not_prose():
    """
    Only the four-line comment block is reported; the section header does not lengthen
    the three-line block below it.
    """
    assert overlong_first_lines(ProseSnippet.COMMENT_BLOCKS) == [
        LONG_COMMENT_BLOCK_LINE
    ]


def test_a_raised_limit_lets_the_block_through():
    """
    A five-line docstring passes a five-line limit.
    """
    checker = ProseLengthChecker(docstring_lines=OVERLONG_MODULE_DOCSTRING_PROSE_LINES)

    assert list(checker.violations(ProseSnippet.OVERLONG_MODULE_DOCSTRING)) == []
