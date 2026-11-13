"""
Reading the renames a pull request's description declares.
"""

from __future__ import annotations

from basstler.review_triage.declaration import TriageDeclaration

from .samples import DescriptionSample


def test_a_declaration_comment_is_read():
    """
    The YAML of a description's declaration comment becomes its renames and rejections.
    """
    assert TriageDeclaration.of_description(
        DescriptionSample.DECLARING.read()
    ) == TriageDeclaration({"read_value": "value"}, ("write_value",))


def test_a_description_without_a_declaration_declares_nothing():
    """
    A description with no declaration comment declares no renames.
    """
    assert (
        TriageDeclaration.of_description(DescriptionSample.WITHOUT_DECLARATION.read())
        == TriageDeclaration()
    )
