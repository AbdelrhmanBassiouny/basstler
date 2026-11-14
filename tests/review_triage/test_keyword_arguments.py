"""
Judging calls that pass positional arguments by keyword, and parameters made keyword-
only, against the base commit's definitions.
"""

from __future__ import annotations

import ast

import pytest

from basstler.review_triage.comparison import (
    FileNeedingReview,
    FileTriage,
    FileTriager,
    JudgmentContext,
    MechanicalChange,
    MechanicalFile,
    ProseComparison,
)
from basstler.review_triage.keyword_arguments import (
    KEYWORD_RULES,
    KeywordArgumentComparison,
    KeywordChange,
)
from basstler.review_triage.python_source import ImportBindings, PythonSource
from basstler.review_triage.renames import RenameMap
from basstler.review_triage.tree_matching import TreeMatcher

from .samples import FileSample

# %% verdicts


def triaged(sample: FileSample, renames: RenameMap) -> FileTriage:
    """
    :param sample: A file in two versions.
    :param renames: The renames of the pull request.
    :return: The sample's verdict, its base version's definitions as the base commit's.
    """
    triager = FileTriager(
        JudgmentContext(renames, sample.base_definitions()),
        (KeywordArgumentComparison(), ProseComparison()),
    )
    return triager.triage(sample.change())


@pytest.mark.parametrize(
    ("sample", "kinds"),
    [
        (FileSample.KEYWORD_ARGUMENTS_ADDED, {KeywordChange.KEYWORD_ARGUMENTS}),
        (FileSample.KEYWORD_ONLY_PARAMETERS, {KeywordChange.KEYWORD_ONLY}),
        (FileSample.IDENTITY_DECORATOR_ADDED, {KeywordChange.IDENTITY_DECORATORS}),
        (FileSample.CODE_REFORMATTED, {MechanicalChange.FORMATTING}),
    ],
)
def test_a_call_binding_as_before_is_mechanical(
    sample: FileSample, kinds: set[KeywordChange]
):
    """
    Keywords naming the parameters the base definitions bound the arguments to, keyword-
    only parameters and added identity decorators are mechanical.
    """
    assert triaged(sample, RenameMap()) == MechanicalFile(
        sample.change(), frozenset(kinds)
    )


@pytest.mark.parametrize(
    "sample",
    [
        FileSample.KEYWORD_ARGUMENTS_SWAPPED,
        FileSample.KEYWORD_ARGUMENTS_REORDERED,
        FileSample.KEYWORD_ARGUMENTS_UNKNOWN_CALLEE,
        FileSample.BEHAVIOUR_CHANGED,
    ],
)
def test_a_call_that_may_bind_differently_needs_review(sample: FileSample):
    """
    Keywords naming other parameters, arguments evaluated in another order and calls of
    a callee the base commit does not define need review.
    """
    assert triaged(sample, RenameMap()) == FileNeedingReview(sample.change())


def test_the_plain_comparison_verdicts_are_kept(old_name_renamed: RenameMap):
    """
    A change the plain Python comparison finds mechanical keeps its kinds.
    """
    assert triaged(FileSample.IDENTIFIER_RENAMED, old_name_renamed).kinds == {
        MechanicalChange.IMPORTS,
        MechanicalChange.RENAME,
    }


# %% the comparison of trees


def test_a_failed_attempt_keeps_no_findings():
    """
    Trying a match that fails drops the findings its inner calls recorded.
    """
    base = ast.parse("total(scale(1.0), 2.0)").body[0]
    head = ast.parse("total(scale(value=1.0), 3.0)").body[0]
    matcher = TreeMatcher(KEYWORD_RULES, ImportBindings(frozenset()))
    assert (matcher.attempt(base, head), matcher.findings) == (False, [])


@pytest.mark.parametrize(
    ("function", "types"),
    [
        (
            "def f(shape: Shape, size: int | None, other): pass",
            {"shape": "Shape", "size": "int"},
        ),
        ("def f(shape: Shape):\n    shape = make()", {}),
        ("def f(items: list[Shape], maybe: Optional[Shape]): pass", {"maybe": "Shape"}),
    ],
)
def test_only_parameters_kept_as_annotated_have_a_class(function: str, types: dict):
    """
    A parameter has a class when its annotation allows one, ``None`` aside, and the
    function never assigns to it.
    """
    assert PythonSource.annotated_parameters(ast.parse(function).body[0]) == types
