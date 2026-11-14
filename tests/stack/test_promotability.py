"""
Tests for :mod:`basstler.stack.promotability`: the one rule saying whether a branch may
be promoted to the upstream, and the link target the promotion link is built for.
"""

from __future__ import annotations

import pytest

from basstler.stack.model import BranchStatus, PullRequest
from basstler.stack.promotability import PromotionBlocker, PromotionReadiness
from basstler.stack.promotion_link import PromotionLink, PromotionTarget

from ..constants.stack import StackBranch
from .dataset import StackRepository, StackSampleText, build, make_configuration

# %% the blockers of one branch


def a_promotable_branch() -> PromotionReadiness:
    """
    :return: The readiness of a branch nothing holds back.
    """
    return PromotionReadiness(
        status=BranchStatus.READY,
        parent_landed=True,
        withheld=False,
        checks_failed=False,
    )


def test_a_branch_nothing_holds_back_is_promotable():
    readiness = a_promotable_branch()
    assert readiness.blockers == []
    assert readiness.is_promotable


@pytest.mark.parametrize(
    ("status", "blocker"),
    [
        (BranchStatus.DRAFT, PromotionBlocker.DRAFT),
        (BranchStatus.IN_REVIEW, PromotionBlocker.IN_REVIEW),
        (BranchStatus.MERGED, PromotionBlocker.MERGED),
    ],
)
def test_a_status_other_than_ready_blocks_promotion(status, blocker):
    readiness = PromotionReadiness(
        status=status, parent_landed=True, withheld=False, checks_failed=False
    )
    assert readiness.blockers == [blocker]
    assert not readiness.is_promotable


def test_a_parent_that_has_not_landed_blocks_promotion():
    readiness = PromotionReadiness(
        status=BranchStatus.READY,
        parent_landed=False,
        withheld=False,
        checks_failed=False,
    )
    assert readiness.blockers == [PromotionBlocker.PARENT_NOT_LANDED]


def test_a_withheld_branch_is_blocked():
    readiness = PromotionReadiness(
        status=BranchStatus.READY,
        parent_landed=True,
        withheld=True,
        checks_failed=False,
    )
    assert readiness.blockers == [PromotionBlocker.WITHHELD]


def test_failed_checks_block_promotion():
    readiness = PromotionReadiness(
        status=BranchStatus.READY,
        parent_landed=True,
        withheld=False,
        checks_failed=True,
    )
    assert readiness.blockers == [PromotionBlocker.CHECKS_FAILED]


def test_every_blocker_is_listed_in_declaration_order():
    readiness = PromotionReadiness(
        status=BranchStatus.DRAFT,
        parent_landed=False,
        withheld=True,
        checks_failed=True,
    )
    assert readiness.blockers == [
        PromotionBlocker.DRAFT,
        PromotionBlocker.PARENT_NOT_LANDED,
        PromotionBlocker.WITHHELD,
        PromotionBlocker.CHECKS_FAILED,
    ]


# %% the stack asks the same rule


def test_the_stack_promotes_exactly_the_branches_its_rule_finds_promotable():
    fork = StackRepository.FORK.value.full_name
    stack = build(
        [
            PullRequest(
                1,
                StackBranch.PARENT,
                StackBranch.BASE,
                draft=False,
                head_repository=fork,
            ),
            PullRequest(
                2,
                StackBranch.CHILD,
                StackBranch.PARENT,
                draft=False,
                head_repository=fork,
            ),
            PullRequest(
                3,
                StackBranch.FEATURE,
                StackBranch.BASE,
                draft=True,
                head_repository=fork,
            ),
        ]
    )
    assert [branch.name for branch in stack.promotion_order()] == [
        branch.name
        for branch in stack.maintained_branches()
        if stack.readiness_of(branch).is_promotable
    ]
    assert [branch.name for branch in stack.promotion_order()] == [StackBranch.PARENT]


# %% the link target


def test_the_target_of_a_configuration_names_its_upstream_and_fork_owner():
    configuration = make_configuration()
    assert PromotionTarget.from_configuration(configuration) == PromotionTarget(
        upstream_repository=configuration.upstream_repository,
        upstream_base=configuration.upstream_base,
        fork_owner=configuration.fork_repository.owner,
    )


def test_a_link_built_for_a_target_is_the_link_built_for_its_configuration():
    configuration = make_configuration()
    target = PromotionTarget.from_configuration(configuration)
    assert PromotionLink.for_target(
        target, StackBranch.FEATURE, StackSampleText.TITLE, StackSampleText.SHORT_BODY
    ) == PromotionLink.build(
        configuration,
        StackBranch.FEATURE,
        StackSampleText.TITLE,
        StackSampleText.SHORT_BODY,
    )
