"""
Tests for checking an item's manifest entry against local git.
"""

from __future__ import annotations

import pytest

from basstler.plan.item_bootstrap.check import ItemCheckRequest
from basstler.plan.item_bootstrap.exceptions import UnknownItemError
from basstler.plan.item_bootstrap.vocabulary import PlanItemBootstrapExitCode
from basstler.plan.model import (
    ItemStatus,
    ManifestKey,
)

from ...scratch_repository import ScratchRepository
from .bootstrap_scenario import (
    EXISTING_ITEM,
    NEW_BRANCH,
    NEW_ITEM,
    PLAN_IDENTIFIER,
    PULL_REQUEST_NUMBER,
    opened_item_fields,
    publish_new_branch,
    update_request,
)

# %% checking what the manifest claims against local git


def check_existing_item(repository: ScratchRepository) -> object:
    """
    :param repository: The scratch repository to check within.
    :return: What checking the fixture's unstarted item reports.
    """
    return ItemCheckRequest(
        plan_identifier=PLAN_IDENTIFIER, item_identifier=EXISTING_ITEM
    ).check(repository.project_root)


def test_a_recorded_branch_that_was_never_published_is_reported_stale(
    bootstrap_repository: ScratchRepository,
):
    update_request(values_by_key={ManifestKey.BRANCH: NEW_BRANCH}).update(
        bootstrap_repository.project_root
    )

    report = check_existing_item(bootstrap_repository)

    assert [finding.manifest_key for finding in report.findings] == [ManifestKey.BRANCH]
    assert report.findings[0].recorded == NEW_BRANCH
    assert report.exit_code is PlanItemBootstrapExitCode.MANIFEST_IS_STALE


def test_an_item_recording_a_published_branch_reports_nothing_stale(
    bootstrap_repository: ScratchRepository,
):
    publish_new_branch(bootstrap_repository)
    update_request(values_by_key=opened_item_fields()).update(
        bootstrap_repository.project_root
    )

    report = check_existing_item(bootstrap_repository)

    assert report.findings == ()
    assert report.exit_code is PlanItemBootstrapExitCode.SUCCESS


def test_a_published_branch_with_no_session_recorded_is_reported_stale(
    bootstrap_repository: ScratchRepository,
):
    publish_new_branch(bootstrap_repository)
    update_request(
        values_by_key={
            ManifestKey.BRANCH: NEW_BRANCH,
            ManifestKey.STATUS: ItemStatus.IN_PROGRESS,
            ManifestKey.PULL_REQUEST_NUMBER: PULL_REQUEST_NUMBER,
        }
    ).update(bootstrap_repository.project_root)

    report = check_existing_item(bootstrap_repository)

    assert [finding.manifest_key for finding in report.findings] == [
        ManifestKey.SESSION
    ]


def test_a_branch_exists_while_the_item_is_still_not_started(
    bootstrap_repository: ScratchRepository,
):
    publish_new_branch(bootstrap_repository)
    update_request(values_by_key={ManifestKey.BRANCH: NEW_BRANCH}).update(
        bootstrap_repository.project_root
    )

    report = check_existing_item(bootstrap_repository)

    status_finding = next(
        finding
        for finding in report.findings
        if finding.manifest_key is ManifestKey.STATUS
    )
    assert ItemStatus(status_finding.recorded) is ItemStatus.NOT_STARTED


def test_checking_an_unknown_item_is_refused(bootstrap_repository: ScratchRepository):
    with pytest.raises(UnknownItemError):
        ItemCheckRequest(
            plan_identifier=PLAN_IDENTIFIER, item_identifier=NEW_ITEM
        ).check(bootstrap_repository.project_root)
