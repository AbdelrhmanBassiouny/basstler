"""
Reading the parameters a call may pass positionally from the definitions of a commit.
"""

from __future__ import annotations

import pytest

from basstler.review_triage.calls import InstanceMethod, NamedCallee, OwnClass
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
        (KeywordConversion("Derived", 1, ("label",), NamedCallee(), None), True),
        (
            KeywordConversion(
                "Derived", 0, ("label", "identifier"), NamedCallee(), None
            ),
            False,
        ),
        (
            KeywordConversion("Plain", 0, ("first", "second"), NamedCallee(), None),
            False,
        ),
        (KeywordConversion("gather", 0, ("items",), NamedCallee(), None), False),
        (KeywordConversion("read", 0, ("path",), NamedCallee(), None), False),
        (
            KeywordConversion("read", 0, ("path",), InstanceMethod(), "FastReader"),
            True,
        ),
        (KeywordConversion("cls", 1, ("label",), OwnClass(), "Derived"), True),
    ],
)
def test_a_keyword_binds_only_where_the_parameter_takes_it(
    reader: SignatureReader, conversion: KeywordConversion, binds: bool
):
    """
    A keyword binds as before only when it names the parameter at its position in every
    definition the call may reach: by name anywhere, or through the class hierarchy.
    """
    assert conversion.holds(reader, RenameMap()) is binds
