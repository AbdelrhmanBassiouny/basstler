"""
Tests for :mod:`basstler.code_rules.prose_length`: finding docstrings and comment blocks
longer than a limit.
"""

from __future__ import annotations

from basstler.code_rules.prose_length import ProseLengthChecker, SourceProse

from ..constants.paths import ProseSnippet

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
    module_first_line = 1

    assert overlong_first_lines(ProseSnippet.OVERLONG_MODULE_DOCSTRING) == [
        module_first_line
    ]


def test_field_lists_and_literal_blocks_are_not_prose():
    """
    Only the summary and the line introducing the literal block count as prose.
    """
    summary_and_literal_block_introduction_lines = 2

    (block,) = SourceProse(
        ProseSnippet.FIELDS_AND_LITERAL_BLOCKS.read_text(encoding="utf-8")
    ).blocks

    assert block.prose_lines == summary_and_literal_block_introduction_lines


def test_an_attribute_docstring_is_measured():
    """
    A docstring directly below a field is measured like any other.
    """
    attribute_docstring_line = 10

    assert overlong_first_lines(ProseSnippet.OVERLONG_ATTRIBUTE_DOCSTRING) == [
        attribute_docstring_line
    ]


def test_a_comment_block_over_its_limit_is_reported_and_section_headers_are_not_prose():
    """
    Only the four-line comment block is reported; the section header does not lengthen
    the three-line block below it.
    """
    four_line_comment_block_line = 10

    assert overlong_first_lines(ProseSnippet.COMMENT_BLOCKS) == [
        four_line_comment_block_line
    ]


def test_a_raised_limit_lets_the_block_through():
    """
    A five-line docstring passes a five-line limit.
    """
    module_docstring_prose_lines = 5
    checker = ProseLengthChecker(docstring_lines=module_docstring_prose_lines)

    assert list(checker.violations(ProseSnippet.OVERLONG_MODULE_DOCSTRING)) == []
