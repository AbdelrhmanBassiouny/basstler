"""
Tests for the workflow that runs the personal-notes setup on Windows: that it runs only
for the pull requests it names, and that each name still matches something to change.
"""

from __future__ import annotations

import pytest

from basstler.workflows import Trigger, TriggerEvent, Workflow

from .constants.paths import RepositoryLocation

WINDOWS_SETUP = Workflow.at(RepositoryLocation.WINDOWS_SETUP_WORKFLOW.value)
"""
The workflow under test.
"""

# %% the changes it runs for


def only_trigger() -> Trigger:
    """
    :return: The one event the workflow answers to.
    """
    (trigger,) = WINDOWS_SETUP.triggers
    return trigger


def test_the_workflow_runs_only_for_pull_requests():
    """
    A push runs nothing on a Windows runner, so no change is paid for twice.
    """
    assert only_trigger().event is TriggerEvent.PULL_REQUEST


@pytest.mark.parametrize("pattern", sorted(only_trigger().paths))
def test_every_path_filter_matches_a_file_in_the_repository(pattern: str):
    """
    A filter left naming a moved file would stop the workflow running for it, silently.
    """
    assert any(path.is_file() for path in RepositoryLocation.ROOT.value.glob(pattern))


def test_the_workflow_runs_when_it_changes():
    """
    A change to the workflow itself is checked by running it.
    """
    workflow = RepositoryLocation.WINDOWS_SETUP_WORKFLOW.value.relative_to(
        RepositoryLocation.ROOT.value
    )

    assert workflow.as_posix() in only_trigger().paths
