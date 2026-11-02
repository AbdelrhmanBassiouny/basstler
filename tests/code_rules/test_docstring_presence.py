"""
Tests for :mod:`basstler.code_rules.docstring_presence`: finding undocumented code.
"""

from __future__ import annotations

from basstler.code_rules.docstring_presence import MissingDocstringChecker

from ..constants.paths import DocstringSnippet
from ..constants.source_lines import (
    MODULE_FIRST_LINE,
    UNDOCUMENTED_FIELD_LINE,
    UNDOCUMENTED_METHOD_LINE,
    UNDOCUMENTED_OVERRIDING_METHOD_LINE,
    UNIMPORTABLE_UNDOCUMENTED_FUNCTION_LINE,
)

# %% undocumented code


def undocumented_first_lines(snippet: DocstringSnippet) -> list[int]:
    """
    :return: The first line of each undocumented piece of code in *snippet*, top to
        bottom.
    """
    return sorted(
        violation.first_line
        for violation in MissingDocstringChecker().violations(snippet)
    )


def test_undocumented_fields_and_methods_are_reported_but_abstract_implementations_are_not():
    """
    The field, the override of an implemented method and the new method without a
    docstring are reported; the implementation of an abstract method inherits its base's
    docstring.
    """
    assert undocumented_first_lines(DocstringSnippet.UNDOCUMENTED_DEFINITIONS) == [
        UNDOCUMENTED_FIELD_LINE,
        UNDOCUMENTED_OVERRIDING_METHOD_LINE,
        UNDOCUMENTED_METHOD_LINE,
    ]


def test_an_unimportable_module_is_checked_except_for_its_methods():
    """
    A module that raises on import still has its functions checked; only its methods,
    whose bases cannot be looked up, are skipped.
    """
    assert undocumented_first_lines(DocstringSnippet.UNIMPORTABLE_DEFINITIONS) == [
        UNIMPORTABLE_UNDOCUMENTED_FUNCTION_LINE
    ]


def test_a_module_without_a_docstring_is_reported():
    """
    A module's missing docstring is reported at its first line.
    """
    assert undocumented_first_lines(DocstringSnippet.NO_MODULE_DOCSTRING) == [
        MODULE_FIRST_LINE
    ]
