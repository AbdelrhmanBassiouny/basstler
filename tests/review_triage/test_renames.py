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


def test_a_moved_module_path_is_replaced_as_a_prefix():
    """
    A renamed dotted module path is replaced where an identifier starts with it, and
    only there.
    """
    renames = RenameMap((Rename("package.old", "package.new.old", "file move"),))
    assert [
        renames.renamed_identifier(identifier)
        for identifier in ("package.old.Member", "package.older", "other.package.old")
    ] == ["package.new.old.Member", "package.older", "other.package.old"]


def test_an_original_identifier_is_found_from_its_replacement():
    """
    The identifier the base commit used is found from the one replacing it.
    """
    assert RenameMap((DETECTED,)).original_identifier(DETECTED.new) == DETECTED.old


# %% file paths

MOVED_FILE = Rename(
    "repository.py", "storage/repository.py", "file path move", is_file_path=True
)
"""
A moved file's path from the first directory the move changes.
"""


def test_a_file_path_is_renamed_where_it_stands_whole():
    renames = RenameMap((MOVED_FILE,))
    assert renames.renamed_prose("see `repository.py`.") == (
        "see `storage/repository.py`."
    )


def test_a_file_path_is_not_renamed_as_the_end_of_a_longer_path():
    renames = RenameMap((MOVED_FILE,))
    assert renames.renamed_prose("see other/repository.py") == "see other/repository.py"


def test_a_file_path_is_not_a_module_prefix():
    renames = RenameMap((MOVED_FILE,))
    assert renames.renamed_identifier("repository.py") == "repository.py"
