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


def test_an_undocumented_field_and_method_are_reported_and_an_override_is_not():
    """
    The field and the method without a docstring are reported; the method decorated with
    :func:`typing.override` inherits its base's docstring.
    """
    assert undocumented_first_lines(DocstringSnippet.UNDOCUMENTED_DEFINITIONS) == [
        32,
        38,
    ]


def test_a_module_without_a_docstring_is_reported():
    """
    A module's missing docstring is reported at its first line.
    """
    assert undocumented_first_lines(DocstringSnippet.NO_MODULE_DOCSTRING) == [1]
