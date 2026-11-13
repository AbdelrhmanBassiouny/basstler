"""
Tests for :mod:`basstler.code_rules.package_boundaries`: reporting imports of a
distribution the importing module's distribution does not list.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from basstler.code_rules.package_boundaries import (
    BoundaryCrossing,
    PackageBoundaryChecker,
    PackageCrossings,
)
from basstler.package_map import (
    Distribution,
    DistributionDeclaration,
    Layer,
    PackageMap,
)

from ..constants.paths import PackageBoundarySnippet

# %% the dataset's package


@pytest.fixture
def checker() -> PackageBoundaryChecker:
    """
    :return: A checker of the dataset's package, where a higher distribution lists a
        lower one.
    """
    return PackageBoundaryChecker(
        PackageMap(
            (
                DistributionDeclaration(Distribution.CORE, Layer.CORE, ("low",)),
                DistributionDeclaration(
                    Distribution.GIT,
                    Layer.LOCAL_TOOLS,
                    ("high",),
                    (Distribution.CORE,),
                ),
            )
        ),
        PackageBoundarySnippet.PACKAGE.value,
    )


def violation_lines(checker: PackageBoundaryChecker, path: Path) -> list[int]:
    """
    :return: The first line of each violation *checker* reports in *path*.
    """
    return [violation.first_line for violation in checker.violations(path)]


# %% imports


def test_an_import_of_a_listed_distribution_is_not_reported(checker):
    """
    The higher distribution lists the lower one, so both its imports of it are allowed.
    """
    assert violation_lines(checker, PackageBoundarySnippet.LISTED_IMPORT) == []


def test_an_import_of_an_unlisted_distribution_is_reported(checker):
    """
    The lower distribution does not list the higher one.
    """
    import_line = 7

    assert violation_lines(checker, PackageBoundarySnippet.UNLISTED_IMPORT) == [
        import_line
    ]


def test_a_from_import_of_a_module_names_that_module(checker):
    """
    ``from basstler.high import caller`` imports the module ``high.caller``.
    """
    (crossing,) = checker.crossings(PackageBoundarySnippet.UNLISTED_IMPORT)

    assert crossing.imported_module == "high.caller"


# %% modules


def test_a_module_no_distribution_claims_is_reported_on_its_first_line(checker):
    """
    Neither distribution claims ``stray``.
    """
    first_line = 1

    assert violation_lines(checker, PackageBoundarySnippet.UNCLAIMED_MODULE) == [
        first_line
    ]


def test_a_file_outside_the_package_is_not_checked(checker):
    """
    A test or a script belongs to no distribution.
    """
    assert violation_lines(checker, Path(__file__)) == []


# %% the package's crossings


def test_the_package_s_crossings_are_listed_by_module(checker):
    """
    The dataset's one crossing is the lower distribution's import of the higher one.
    """
    assert checker.package_crossings().crossings == (
        BoundaryCrossing(importing_module="low.upward", imported_module="high.caller"),
    )


def test_a_crossing_the_base_does_not_hold_is_new(checker):
    """
    Against a base with no crossings, every crossing of the package is new.
    """
    crossings = checker.package_crossings()

    assert crossings.added_since(PackageCrossings(crossings=())) == (
        crossings.crossings
    )


def test_a_crossing_the_base_holds_is_not_new(checker):
    """
    A crossing the base already had is left for the item that moves its code.
    """
    crossings = checker.package_crossings()

    assert crossings.added_since(crossings) == ()
