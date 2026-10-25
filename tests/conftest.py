"""
Fixtures shared by every suite in this directory.

basstler is imported from its editable install, which is this clone's own source under
basstler/src, as CI installs it and as a session start installs it into basstler/.venv.

This suite runs in the lightweight test_basstler CI job with --confcutdir pointed
here, so the repository-root test/conftest.py - which imports the robotics stack that
job does not install - is never loaded for it.
"""

import os
from pathlib import Path

import pytest

# A session running the plugin exports BASSTLER_PLUGIN_ROOT as its synced copy, which
# basstler.locations reads on import; pinned before anything imports it, so the suite
# tests this checkout's plugin rather than whichever release that session synced.
os.environ["BASSTLER_PLUGIN_ROOT"] = str(Path(__file__).resolve().parents[1] / "plugin")

from .constants.paths import PersonalNotesPath
from .executable_stubs import ExecutableStubDirectory
from .maintenance_fork import ForkCheckout
from .scratch_repository import ScratchRepository
from .upstream_reviews_replay import RecordedResponse, ReplayingClient


@pytest.fixture
def scratch_repository(tmp_path: Path) -> ScratchRepository:
    """
    An initialized scratch project root and its bare notes remote, with nothing
    committed and no personal-notes branch published yet.

    :param tmp_path: pytest's per-test temporary directory.
    :return: The scratch repository.
    """
    return ScratchRepository.create(tmp_path)


@pytest.fixture
def notes_repository(scratch_repository: ScratchRepository) -> ScratchRepository:
    """
    A scratch repository on a work branch, whose configured notes remote carries a
    published notes branch.
    """
    scratch_repository.write("README.md", "scratch repo\n")
    scratch_repository.commit_everything("initial commit")
    scratch_repository.publish_notes_branch(
        {PersonalNotesPath.SAMPLE_NOTES: "- a rule\n"}
    )
    scratch_repository.resolve_notes_remote_to()
    return scratch_repository


@pytest.fixture
def stub_bin(tmp_path: Path) -> ExecutableStubDirectory:
    """
    An empty directory meant to be placed first on a test subprocess's PATH, into which
    a test installs whichever stubbed executable it needs.

    :param tmp_path: pytest's per-test temporary directory.
    :return: The stub directory.
    """
    return ExecutableStubDirectory.create(tmp_path)


@pytest.fixture
def paginated_client() -> ReplayingClient:
    """:return: A client replaying both pages of the recorded review threads."""
    return ReplayingClient(
        [
            RecordedResponse.PULL_REQUEST_PAGE_ONE.load(),
            RecordedResponse.PULL_REQUEST_PAGE_TWO.load(),
        ]
    )


@pytest.fixture
def fork_checkout(tmp_path: Path) -> ForkCheckout:
    """
    A real fork checkout with both remotes wired to local bare repositories.

    :param tmp_path: pytest's per-test temporary directory.
    :return: The checkout.
    """
    return ForkCheckout.create(tmp_path)
