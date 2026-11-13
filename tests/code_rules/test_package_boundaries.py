"""
Tests for :mod:`basstler.code_rules.package_boundaries`: reporting imports of a
distribution the importing module's distribution does not list.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from basstler.code_rules.package_boundaries import (
    BoundaryCrossing,
    ModuleRenames,
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
def package_map() -> PackageMap:
    """
    :return: The dataset's map, where a higher distribution lists a lower one.
    """
    return PackageMap(
        (
            DistributionDeclaration(Distribution.CORE, Layer.CORE, ("low",)),
            DistributionDeclaration(
                Distribution.GIT,
                Layer.LOCAL_TOOLS,
                ("high",),
                (Distribution.CORE,),
            ),
        )
    )


@pytest.fixture
def checker(package_map) -> PackageBoundaryChecker:
    """
    :return: A checker of the dataset's package.
    """
    return PackageBoundaryChecker(package_map, PackageBoundarySnippet.PACKAGE.value)


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


# %% renamed modules


def test_a_crossing_the_base_holds_under_a_module_s_old_name_is_not_new(checker):
    """
    A module that moved keeps the crossings it had under its old name.
    """
    crossings = checker.package_crossings()
    (crossing,) = crossings.crossings
    renames = ModuleRenames({"low.before_the_move": crossing.importing_module})
    base = PackageCrossings(
        crossings=(
            BoundaryCrossing(
                importing_module="low.before_the_move",
                imported_module=crossing.imported_module,
            ),
        )
    )

    assert crossings.added_since(base.renamed(renames)) == ()


@pytest.fixture
def moved_package(
    scratch_repository, package_map
) -> tuple[PackageBoundaryChecker, str]:
    """
    :return: A checker of the dataset's package committed in a scratch repository,
        and the commit before its lower distribution's importing module was moved.
    """
    package = scratch_repository.project_root / PackageBoundarySnippet.PACKAGE.name
    shutil.copytree(PackageBoundarySnippet.PACKAGE.value, package)
    scratch_repository.commit_everything("add the package")
    base_commit = scratch_repository.git.commit_at("HEAD")
    scratch_repository.run_git("mv", "basstler/low/upward.py", "basstler/low/moved.py")
    scratch_repository.commit_everything("move the importing module")
    return PackageBoundaryChecker(package_map, package), base_commit


def test_a_module_git_detects_as_moved_is_renamed(moved_package, scratch_repository):
    """
    The importing module's move is read as a rename from its old dotted name.
    """
    checker, base_commit = moved_package

    assert checker.module_renames(scratch_repository.git, base_commit) == (
        ModuleRenames({"low.upward": "low.moved"})
    )
