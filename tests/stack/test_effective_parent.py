"""
Tests for where a branch's parent went when no open pull request describes it any more,
and what that makes the branch build on.
"""

from __future__ import annotations

from basstler.stack.model import (
    BranchStatus,
    EffectiveParent,
    ParentSituation,
    PullRequest,
    Reparent,
    RestackPlanEntry,
    IntegrationStrategy,
    Stack,
    StackBranch as BranchOfStack,
)

from ..constants.stack import StackBranch

from .dataset import StackRepository, build

# %% the board


def a_board(*branches: tuple[str, str]) -> list[PullRequest]:
    """
    :param branches: Each pull request's head and base.
    :return: An export of one ready pull request per pair, numbered from one.
    """
    return [
        PullRequest(
            number,
            head,
            base,
            draft=False,
            head_repository=StackRepository.FORK.value.full_name,
        )
        for number, (head, base) in enumerate(branches, start=1)
    ]


def the_branch(stack: Stack, name: str) -> BranchOfStack:
    """
    :param stack: The stack to look in.
    :param name: A branch of it.
    :return: That branch.
    """
    return next(branch for branch in stack.branches if branch.name == name)


# %% placing a parent


def test_a_parent_still_on_the_board_is_left_alone():
    stack = build(
        a_board(
            (StackBranch.PARENT, StackBranch.BASE),
            (StackBranch.CHILD, StackBranch.PARENT),
        )
    )

    assert stack.effective_parent(the_branch(stack, StackBranch.CHILD)) == (
        EffectiveParent(StackBranch.PARENT, ParentSituation.TRACKED)
    )


def test_a_parent_that_landed_upstream_sends_its_child_to_the_upstream_base():
    stack = build(
        a_board((StackBranch.CHILD, StackBranch.LANDED_ELSEWHERE)),
        merged={StackBranch.LANDED_ELSEWHERE},
    )

    assert stack.effective_parent(stack.branches[0]) == EffectiveParent(
        StackBranch.BASE, ParentSituation.LANDED
    )


def test_a_parent_that_merged_into_another_open_branch_sends_its_child_there():
    stack = build(
        a_board(
            (StackBranch.GRANDPARENT, StackBranch.BASE),
            (StackBranch.CHILD, StackBranch.PARENT),
        ),
        carried_by={StackBranch.PARENT: StackBranch.GRANDPARENT},
    )

    assert stack.effective_parent(the_branch(stack, StackBranch.CHILD)) == (
        EffectiveParent(StackBranch.GRANDPARENT, ParentSituation.IN_ANOTHER_BRANCH)
    )


def test_a_parent_whose_commits_reached_nothing_is_gone():
    stack = build(a_board((StackBranch.CHILD, StackBranch.UNLANDED_ELSEWHERE)))

    assert stack.effective_parent(stack.branches[0]) == EffectiveParent(
        StackBranch.UNLANDED_ELSEWHERE, ParentSituation.GONE
    )


def test_a_branch_stacked_on_the_one_being_placed_does_not_carry_its_parent():
    """
    Everything cut from a branch contains that branch's own parent, and none of it is
    somewhere for the branch to move to.
    """
    stack = build(
        a_board(
            (StackBranch.CHILD, StackBranch.UNLANDED_ELSEWHERE),
            (StackBranch.GRANDCHILD, StackBranch.CHILD),
        ),
        carried_by={StackBranch.UNLANDED_ELSEWHERE: StackBranch.GRANDCHILD},
    )

    assert (
        stack.effective_parent(the_branch(stack, StackBranch.CHILD)).situation
        is ParentSituation.GONE
    )


def test_a_branch_that_does_not_contain_the_parent_is_not_chosen_to_carry_it():
    stack = build(
        a_board(
            (StackBranch.PARSER, StackBranch.BASE),
            (StackBranch.GRANDPARENT, StackBranch.BASE),
            (StackBranch.CHILD, StackBranch.PARENT),
        ),
        carried_by={StackBranch.PARENT: StackBranch.GRANDPARENT},
    )

    assert (
        stack.effective_parent(the_branch(stack, StackBranch.CHILD)).branch
        == StackBranch.GRANDPARENT
    )


def test_a_grandparent_the_child_also_merged_into_is_still_where_its_parent_went():
    """
    Git containment alone would rule out the one right answer here, since the
    grandparent contains the child as well as the parent.
    """
    stack = build(
        a_board(
            (StackBranch.GRANDPARENT, StackBranch.BASE),
            (StackBranch.CHILD, StackBranch.PARENT),
        ),
        carried_by={
            StackBranch.PARENT: StackBranch.GRANDPARENT,
            StackBranch.CHILD: StackBranch.GRANDPARENT,
        },
    )

    assert stack.effective_parent(the_branch(stack, StackBranch.CHILD)) == (
        EffectiveParent(StackBranch.GRANDPARENT, ParentSituation.IN_ANOTHER_BRANCH)
    )


# %% what the placement decides


def test_a_child_is_reparented_onto_the_branch_its_parent_merged_into():
    stack = build(
        a_board(
            (StackBranch.GRANDPARENT, StackBranch.BASE),
            (StackBranch.CHILD, StackBranch.PARENT),
        ),
        carried_by={StackBranch.PARENT: StackBranch.GRANDPARENT},
    )

    assert stack.reparents() == [
        Reparent(
            branch=StackBranch.CHILD,
            pull_request_number=2,
            current_base=StackBranch.PARENT,
            target_base=StackBranch.GRANDPARENT,
        )
    ]


def test_a_child_whose_parent_is_gone_is_not_reparented():
    stack = build(a_board((StackBranch.CHILD, StackBranch.UNLANDED_ELSEWHERE)))

    assert stack.reparents() == []


def test_the_restack_plan_is_integrated_with_the_branch_carrying_the_parent():
    stack = build(
        a_board(
            (StackBranch.GRANDPARENT, StackBranch.BASE),
            (StackBranch.CHILD, StackBranch.PARENT),
        ),
        carried_by={StackBranch.PARENT: StackBranch.GRANDPARENT},
    )

    assert stack.restack_plan()[1] == RestackPlanEntry(
        branch=StackBranch.CHILD,
        parent=StackBranch.GRANDPARENT,
        strategy=IntegrationStrategy.MERGE,
    )


def test_the_restack_plan_names_a_gone_parent_as_it_stands():
    stack = build(a_board((StackBranch.CHILD, StackBranch.UNLANDED_ELSEWHERE)))

    assert stack.restack_plan() == [
        RestackPlanEntry(
            branch=StackBranch.CHILD,
            parent=StackBranch.UNLANDED_ELSEWHERE,
            strategy=IntegrationStrategy.MERGE,
        )
    ]


def test_a_child_is_not_promotable_while_its_parent_is_gone():
    stack = build(a_board((StackBranch.CHILD, StackBranch.UNLANDED_ELSEWHERE)))

    assert stack.promotion_order() == []


def test_a_child_is_not_promotable_when_its_parent_only_merged_into_an_unlanded_branch():
    stack = build(
        a_board(
            (StackBranch.GRANDPARENT, StackBranch.BASE),
            (StackBranch.CHILD, StackBranch.PARENT),
        ),
        carried_by={StackBranch.PARENT: StackBranch.GRANDPARENT},
    )

    assert [branch.name for branch in stack.promotion_order()] == [
        StackBranch.GRANDPARENT
    ]
    assert the_branch(stack, StackBranch.CHILD).status is BranchStatus.READY
