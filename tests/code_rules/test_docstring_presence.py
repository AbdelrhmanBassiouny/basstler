"""
Tests for :mod:`basstler.code_rules.docstring_presence`: finding undocumented code.
"""

from __future__ import annotations

from basstler.code_rules.docstring_presence import MissingDocstringChecker

from ..constants.paths import DocstringSnippet

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
    undocumented_field_line = 38
    overriding_method_line = 43
    new_method_line = 46

    assert undocumented_first_lines(DocstringSnippet.UNDOCUMENTED_DEFINITIONS) == [
        undocumented_field_line,
        overriding_method_line,
        new_method_line,
    ]


def test_an_unimportable_module_is_checked_except_for_its_methods():
    """
    A module that raises on import still has its functions checked; only its methods,
    whose bases cannot be looked up, are skipped.
    """
    undocumented_function_line = 19

    assert undocumented_first_lines(DocstringSnippet.UNIMPORTABLE_DEFINITIONS) == [
        undocumented_function_line
    ]


def test_a_module_without_a_docstring_is_reported():
    """
    A module's missing docstring is reported at its first line.
    """
    module_first_line = 1

    assert undocumented_first_lines(DocstringSnippet.NO_MODULE_DOCSTRING) == [
        module_first_line
    ]
