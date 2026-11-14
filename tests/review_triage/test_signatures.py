"""
Reading the parameters a call may pass positionally from the definitions of a commit.
"""

from __future__ import annotations

import pytest

from basstler.review_triage.calls import (
    AttributeMethodTarget,
    ClassTarget,
    MethodTarget,
    NamedTarget,
)
from basstler.review_triage.definitions import DefinitionIndex, SourceDefinitions
from basstler.review_triage.keyword_arguments import KeywordConversion
from basstler.review_triage.renames import RenameMap
from basstler.review_triage.signatures import Signature, SignatureReader

from .samples import SIGNATURE_DEFINITIONS

# %% signatures


@pytest.fixture
def reader() -> SignatureReader:
    """
    :return: Reads the signatures of the sample definitions.
    """
    return SignatureReader(
        DefinitionIndex(SourceDefinitions((SIGNATURE_DEFINITIONS.read_text(),)))
    )


@pytest.mark.parametrize(
    ("name", "signature"),
    [
        ("Base", Signature(("identifier",))),
        ("Derived", Signature(("identifier", "label"))),
        ("Plain", Signature(("first", "second"), positional_only=1)),
        ("Inheriting", Signature(("first", "second"), positional_only=1)),
        ("gather", Signature((), variadic=True)),
        ("combine", Signature(("left", "right"))),
        ("size", None),
    ],
)
def test_the_positional_parameters_are_read_from_the_definition(
    reader: SignatureReader, name: str, signature: Signature | None
):
    """
    Dataclass fields follow their bases' and skip class variables, uninitialized and
    keyword-only fields; methods drop their instance, but static ones; a property cannot
    be read.
    """
    assert reader.agreed_signature(name) == signature


@pytest.mark.parametrize(
    ("conversion", "binds"),
    [
        (KeywordConversion(NamedTarget("Derived"), 1, ("label",)), True),
        (KeywordConversion(NamedTarget("Derived"), 0, ("label", "identifier")), False),
        (KeywordConversion(NamedTarget("Plain"), 0, ("first", "second")), False),
        (KeywordConversion(NamedTarget("gather"), 0, ("items",)), False),
        (KeywordConversion(NamedTarget("read"), 0, ("path",)), False),
        (KeywordConversion(MethodTarget("read", "FastReader"), 0, ("path",)), True),
        (KeywordConversion(ClassTarget("Derived"), 1, ("label",)), True),
        (
            KeywordConversion(
                AttributeMethodTarget("read", "Library", "reader"), 0, ("path",)
            ),
            True,
        ),
        (
            KeywordConversion(
                AttributeMethodTarget("read", "Library", "fallback"), 0, ("path",)
            ),
            True,
        ),
        (
            KeywordConversion(
                AttributeMethodTarget("read", "Library", "parser"), 0, ("text",)
            ),
            True,
        ),
        (
            KeywordConversion(
                AttributeMethodTarget("read", "Library", "undeclared"), 0, ("path",)
            ),
            False,
        ),
    ],
)
def test_a_keyword_binds_only_where_the_parameter_takes_it(
    reader: SignatureReader, conversion: KeywordConversion, binds: bool
):
    """
    A keyword binds as before only when it names the parameter at its position in every
    definition the call may reach: by name anywhere, through the class hierarchy, or
    through the class an attribute is declared to hold, by name where none is declared.
    """
    assert conversion.holds(reader, RenameMap()) is binds
