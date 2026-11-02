"""
Tests for :mod:`basstler.plan_site.dispatch_check`: whether the notes branch's dispatch
has started the plan site's build.
"""

from __future__ import annotations

import json

import pytest

from basstler.locations import ClaudeCodeVariable
from basstler.plan_site import dispatch_check
from basstler.plan_site.dispatch_check import DispatchCheck
from basstler.plan_site.exceptions import NotesRepositoryUnresolvedError
from basstler.plan_site.run_listing import RunListing
from basstler.plan_site.workflows import DispatchWorkflow
from basstler.repository import Repository
from basstler.setup.steps import PersonalNotesSetting
from basstler.setup.report import CheckStatus

from ..constants.paths import DatasetLocation
from ..maintenance.fork import ForkCheckout
from ..upstream_reviews.replay import ReplayingRestClient

NOTES_REPOSITORY = Repository.parse("an-owner/a-repository")
"""
The notes repository whose dispatch runs are checked.
"""

NOTES_BRANCH = PersonalNotesSetting.BRANCH.default
"""
The notes branch the dispatch runs on.
"""

# %% the latest dispatch run


def replaying(listing: DatasetLocation) -> ReplayingRestClient:
    """
    :param listing: The recorded run listing of the notes branch.
    :return: A client answering with that listing.
    """
    return ReplayingRestClient(
        {
            RunListing.path(NOTES_REPOSITORY, NOTES_BRANCH): json.loads(
                listing.read_text()
            )
        }
    )


def check_against(listing: DatasetLocation) -> DispatchCheck:
    """
    :param listing: The recorded run listing of the notes branch.
    :return: The check, reading that listing.
    """
    return DispatchCheck(NOTES_REPOSITORY, NOTES_BRANCH, replaying(listing))


def test_a_succeeded_latest_dispatch_run_is_ok():
    result = check_against(DatasetLocation.PLAN_SITE_DISPATCH_RUNS_SUCCEEDED).result()

    assert result.status is CheckStatus.OK


def test_a_failed_latest_dispatch_run_needs_setup_after_an_earlier_one_succeeded():
    result = check_against(DatasetLocation.PLAN_SITE_DISPATCH_RUNS_FAILED).result()

    assert result.status is CheckStatus.NEEDS_SETUP


def test_a_failed_latest_dispatch_run_is_linked():
    listing = DatasetLocation.PLAN_SITE_DISPATCH_RUNS_FAILED
    latest = RunListing.read(replaying(listing), NOTES_REPOSITORY, NOTES_BRANCH).latest(
        DispatchWorkflow.location
    )

    assert latest.url in check_against(listing).result().detail


def test_a_dispatch_that_never_ran_needs_setup():
    result = check_against(DatasetLocation.WORKFLOW_RUNS_NONE).result()

    assert result.status is CheckStatus.NEEDS_SETUP


# %% the command


def test_a_notes_remote_off_github_cannot_be_checked(
    fork_checkout: ForkCheckout, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(fork_checkout.project_root)
    monkeypatch.delenv(ClaudeCodeVariable.PROJECT_DIRECTORY, raising=False)

    with pytest.raises(NotesRepositoryUnresolvedError):
        dispatch_check.main()
