"""
Combining the renames of several sources and applying them to identifiers and prose.
"""

from __future__ import annotations

from basstler.review_triage.renames import Rename, RenameDecisions, RenameMap

# %% combining sources

DETECTED = Rename("old_name", "new_name", "diff")
"""
A rename an earlier source finds.
"""

DECLARED = Rename("old_name", "newer_name", "description")
"""
A later source's rename of the same identifier.
"""

OTHER = Rename("other", "renamed_other", "diff")
"""
A rename of another identifier.
"""


def test_a_later_source_outranks_an_earlier_one():
    """
    A rename of a later source replaces an earlier source's rename of the same
    identifier.
    """
    renames = RenameMap.of(
        [RenameDecisions((DETECTED, OTHER)), RenameDecisions((DECLARED,))]
    )
    assert renames.renames == (DECLARED, OTHER)


def test_a_rejection_drops_an_earlier_source_rename():
    """
    A rejection removes the rename an earlier source found.
    """
    renames = RenameMap.of(
        [
            RenameDecisions((DETECTED, OTHER)),
            RenameDecisions(rejected=frozenset({"old_name"})),
        ]
    )
    assert renames.renames == (OTHER,)


# %% applying renames


def test_every_renamed_component_of_a_dotted_identifier_is_replaced():
    """
    Each renamed component of a dotted path is replaced.
    """
    renames = RenameMap((DETECTED,))
    assert (
        renames.renamed_identifier("package.old_name.size") == "package.new_name.size"
    )


def test_prose_is_renamed_only_at_whole_words():
    """
    An identifier inside a longer word is left alone.
    """
    renames = RenameMap((DETECTED,))
    assert renames.renamed_prose("old_name, not old_names") == "new_name, not old_names"


def test_renames_swapping_two_identifiers_apply_together():
    """
    Renames apply simultaneously, so two identifiers can swap.
    """
    renames = RenameMap(
        (Rename("first", "second", "diff"), Rename("second", "first", "diff"))
    )
    assert renames.renamed_prose("first then second") == "second then first"
