"""
Fixtures the code rule checker tests share.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from basstler.locations import PackageLocation

from ..constants.paths import DatasetLocation, RepositoryLocation

# %% this repository's sources


@pytest.fixture(scope="session")
def repository_sources() -> list[Path]:
    """
    :return: Every Python file of the package, its scripts and its tests, leaving out
        the test data, whose snippets break rules on purpose.
    """
    return [
        *PackageLocation.DIRECTORY.value.rglob("*.py"),
        *RepositoryLocation.SCRIPTS.value.rglob("*.py"),
        *(
            path
            for path in RepositoryLocation.TESTS.value.rglob("*.py")
            if not path.is_relative_to(DatasetLocation.DIRECTORY.value)
        ),
    ]
