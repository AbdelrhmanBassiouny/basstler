"""
Tests for resolving a branch to its items and writing one owner's blockers on them.
"""

from __future__ import annotations

from basstler.plan.item_bootstrap.blockers import BranchReport, OwnedBlocker
from basstler.plan.item_bootstrap.vocabulary import PlanItemBootstrapExitCode
from basstler.plan.model import (
    ItemStatus,
    ManifestKey,
    PlanDocument,
)

from ...scratch_repository import ScratchRepository
from .bootstrap_scenario import (
    CONFLICT_REASON,
    EXISTING_ITEM,
    HAND_WRITTEN_BLOCKER,
    NO_PLANS_BRANCH,
    OWNER,
    PLAN_IDENTIFIER,
    PLAN_MANIFEST,
    SECOND_ITEM,
    item_named,
    publish_the_branch_index,
    published_items,
    published_plan,
    put_both_items_on_one_branch,
    second_item_branch,
    update_request,
)

# %% resolving a branch to the items it carries


def test_resolving_a_branch_names_the_plan_that_tracks_it(
    bootstrap_repository: ScratchRepository,
):
    publish_the_branch_index(bootstrap_repository)

    resolution = BranchReport.of_branch(
        second_item_branch(), bootstrap_repository.project_root
    )

    assert resolution.plan_identifier == PLAN_IDENTIFIER
    assert [item.item_identifier for item in resolution.items] == [SECOND_ITEM]


def test_resolving_reports_the_status_and_blockers_each_item_records(
    bootstrap_repository: ScratchRepository,
):
    publish_the_branch_index(bootstrap_repository)

    resolution = BranchReport.of_branch(
        second_item_branch(), bootstrap_repository.project_root
    )

    recorded = item_named(PLAN_MANIFEST, SECOND_ITEM)
    assert resolution.items[0].status is ItemStatus(recorded[ManifestKey.STATUS.key])
    assert resolution.items[0].blockers == ()


def test_resolving_a_branch_two_items_ride_on_answers_with_both(
    bootstrap_repository: ScratchRepository,
):
    put_both_items_on_one_branch(bootstrap_repository)

    resolution = BranchReport.of_branch(
        second_item_branch(), bootstrap_repository.project_root
    )

    assert [item.item_identifier for item in resolution.items] == [
        EXISTING_ITEM,
        SECOND_ITEM,
    ]


def test_a_branch_no_plan_claims_is_reported_rather_than_refused(
    bootstrap_repository: ScratchRepository,
):
    publish_the_branch_index(bootstrap_repository)

    resolution = BranchReport.of_branch(
        NO_PLANS_BRANCH, bootstrap_repository.project_root
    )

    assert resolution.plan_identifier is None
    assert resolution.items == ()
    assert resolution.exit_code is PlanItemBootstrapExitCode.BRANCH_TRACKS_NO_ITEM


# %% owning a blocker on every item a branch carries


def owned_blocker(reason: str = CONFLICT_REASON) -> str:
    """
    :param reason: Why the owner blocked the branch.
    :return: The blocker as :class:`OwnedBlocker` writes it for :data:`OWNER`.
    """
    return f"{OWNER}{OwnedBlocker.owner_separator}{reason}"


def block_second_items_branch(
    repository: ScratchRepository, reason: str = CONFLICT_REASON
) -> BranchReport:
    """
    :param repository: The scratch repository to write within.
    :param reason: Why the branch is blocked.
    :return: What blocking the underway item's branch wrote.
    """
    return OwnedBlocker(branch=second_item_branch(), owner=OWNER, reason=reason).write(
        repository.project_root
    )


def unblock_branch(repository: ScratchRepository, branch: str) -> BranchReport:
    """
    :param repository: The scratch repository to write within.
    :param branch: The branch to withdraw :data:`OWNER`'s blocker from.
    :return: What withdrawing it wrote.
    """
    return OwnedBlocker(branch=branch, owner=OWNER).write(repository.project_root)


def hand_write_blocker_on_second_item(repository: ScratchRepository) -> None:
    """
    Record :data:`HAND_WRITTEN_BLOCKER` on the underway item, the way a person would.

    :param repository: The scratch repository to write within.
    """
    update_request(
        item_identifier=SECOND_ITEM,
        values_by_key={ManifestKey.BLOCKERS: [HAND_WRITTEN_BLOCKER]},
    ).update(repository.project_root)


def test_blocking_a_branch_blocks_every_item_it_carries(
    bootstrap_repository: ScratchRepository,
):
    put_both_items_on_one_branch(bootstrap_repository)

    block_second_items_branch(bootstrap_repository)

    for item in published_items(bootstrap_repository).values():
        assert item[ManifestKey.STATUS.key] == ItemStatus.BLOCKED
        assert item[ManifestKey.BLOCKERS.key] == [owned_blocker()]


def test_blocking_keeps_a_blocker_somebody_else_wrote(
    bootstrap_repository: ScratchRepository,
):
    publish_the_branch_index(bootstrap_repository)
    hand_write_blocker_on_second_item(bootstrap_repository)

    block_second_items_branch(bootstrap_repository)

    assert published_items(bootstrap_repository)[SECOND_ITEM][
        ManifestKey.BLOCKERS.key
    ] == [HAND_WRITTEN_BLOCKER, owned_blocker()]


def test_blocking_a_second_time_replaces_its_own_blocker_rather_than_repeating_it(
    bootstrap_repository: ScratchRepository,
):
    publish_the_branch_index(bootstrap_repository)
    block_second_items_branch(bootstrap_repository)

    block_second_items_branch(bootstrap_repository, "a different file conflicts now")

    assert published_items(bootstrap_repository)[SECOND_ITEM][
        ManifestKey.BLOCKERS.key
    ] == [owned_blocker("a different file conflicts now")]


def test_unblocking_removes_only_the_blocker_it_owns(
    bootstrap_repository: ScratchRepository,
):
    publish_the_branch_index(bootstrap_repository)
    hand_write_blocker_on_second_item(bootstrap_repository)
    block_second_items_branch(bootstrap_repository)

    unblock_branch(bootstrap_repository, second_item_branch())

    assert published_items(bootstrap_repository)[SECOND_ITEM][
        ManifestKey.BLOCKERS.key
    ] == [HAND_WRITTEN_BLOCKER]


def test_an_item_still_carrying_somebody_elses_blocker_stays_blocked(
    bootstrap_repository: ScratchRepository,
):
    publish_the_branch_index(bootstrap_repository)
    hand_write_blocker_on_second_item(bootstrap_repository)
    block_second_items_branch(bootstrap_repository)

    unblock_branch(bootstrap_repository, second_item_branch())

    assert (
        published_items(bootstrap_repository)[SECOND_ITEM][ManifestKey.STATUS.key]
        == ItemStatus.BLOCKED
    )


def test_clearing_the_last_blocker_returns_the_item_to_in_progress(
    bootstrap_repository: ScratchRepository,
):
    publish_the_branch_index(bootstrap_repository)
    block_second_items_branch(bootstrap_repository)

    unblock_branch(bootstrap_repository, second_item_branch())

    item = published_items(bootstrap_repository)[SECOND_ITEM]
    assert item[ManifestKey.STATUS.key] == ItemStatus.IN_PROGRESS
    assert item[ManifestKey.BLOCKERS.key] == []


def test_withdrawing_a_blocker_an_item_never_carried_leaves_it_alone(
    bootstrap_repository: ScratchRepository,
):
    """
    A pass withdraws its blocker from every branch it finds clean, most of which it
    never blocked, so writing each of those would spread noise across the manifest.
    """
    publish_the_branch_index(bootstrap_repository)
    before = published_plan(bootstrap_repository)[PlanDocument.MANIFEST]

    report = unblock_branch(bootstrap_repository, second_item_branch())

    assert [item.item_identifier for item in report.items] == [SECOND_ITEM]
    assert published_plan(bootstrap_repository)[PlanDocument.MANIFEST] == before


def test_unblocking_a_branch_no_plan_claims_writes_nothing(
    bootstrap_repository: ScratchRepository,
):
    publish_the_branch_index(bootstrap_repository)
    before = published_plan(bootstrap_repository)[PlanDocument.MANIFEST]

    report = unblock_branch(bootstrap_repository, NO_PLANS_BRANCH)

    assert report.exit_code is PlanItemBootstrapExitCode.BRANCH_TRACKS_NO_ITEM
    assert published_plan(bootstrap_repository)[PlanDocument.MANIFEST] == before
