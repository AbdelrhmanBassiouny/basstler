"""
Tests for the stacked-PR helper's pure logic (no git, no network) and its personal-notes
configuration layering (real scratch git repositories, no network).

The data layer is injected - :func:`build_stack` takes a merged-branch predicate - so
status derivation, topological ordering, promotion policy, and the restack plan are all
exercised against in-memory pull-request exports. Configuration layering genuinely needs a git
remote, so those tests run against a :class:`ScratchRepository` instead.
"""

from __future__ import annotations

import subprocess
from collections.abc import Container
from pathlib import Path

import pytest

import basstler.stack
from basstler.exit_codes import StackExitCode
from basstler.repository import Repository
from basstler.stack_configuration import StackSetting
from basstler.stack import (
    AmbiguousForkRemoteError,
    CommitMoveAction,
    BranchStatus,
    Configuration,
    ContradictoryLabelWriteError,
    ForkRemoteNotFoundError,
    LabelWrite,
    IntegrationStrategy,
    CommitMoveChecks,
    Command,
    ProposedCommitMove,
    RefusalReason,
    PromotionLink,
    PromotionLinkTooLongError,
    PullRequest,
    Remote,
    Reparent,
    build_stack,
    derive_status,
    landed_branches,
    load_configuration,
    next_to_promote,
    print_configuration,
    reparents,
    resolve_remotes,
    order,
    promotion_order,
    RestackPlanEntry,
    restack_plan,
)

from basstler.locations import ProjectLocation

from .constants import DatasetLocation, RemoteName, StackBranch, StackLabel
from .scratch_repository import ScratchRepository
from .script_runner import PythonModuleRunner

A_FORK = Repository("a-fork-owner", "a-fork")
"""
The fork a scratch checkout's remote points at.
"""

SOMEBODY_ELSES_FORK = Repository("someone-else", "their-fork")
"""
A fork other than the one the configuration names.
"""

ANOTHER_OWNERS_FORK = Repository("another-owner", "a-project")
"""
A second fork of the upstream, beside :data:`FORK`.
"""

STACK_MODULE = basstler.stack.__name__
"""
The tool under test, invoked as a subprocess wherever an exit status is the assertion.

Named off the module rather than spelled out, and run with ``-m`` rather than by path: a
module run by path puts its own directory on ``sys.path`` in place of the project root,
so its absolute imports of its siblings would not resolve.
"""


def make_configuration(upstream_setup_command: str | None = None) -> Configuration:
    return Configuration(
        in_review_label=StackLabel.IN_REVIEW,
        rebase_label=StackLabel.REBASE,
        needs_resolution_label=StackLabel.NEEDS_RESOLUTION,
        fork_repository=A_FORK,
        fork_remote=RemoteName.ORIGIN,
        upstream_repository=Repository("an-upstream-owner", "a-project"),
        upstream_remote=RemoteName.UPSTREAM,
        upstream_base=StackBranch.BASE,
        upstream_setup_command=upstream_setup_command,
    )


def build(prs: list[PullRequest], merged: Container[str] = frozenset()):
    return build_stack(make_configuration(), prs, lambda name: name in merged)


# %% derive_status


def test_merged_wins_over_everything():
    assert derive_status(draft=True, merged=True, in_review=True) == BranchStatus.MERGED


def test_in_review_label_beats_draft_flag():
    assert (
        derive_status(draft=True, merged=False, in_review=True)
        == BranchStatus.IN_REVIEW
    )


def test_undrafted_is_ready():
    assert (
        derive_status(draft=False, merged=False, in_review=False) == BranchStatus.READY
    )


def test_drafted_is_draft():
    assert (
        derive_status(draft=True, merged=False, in_review=False) == BranchStatus.DRAFT
    )


# %% status from the export


def test_in_review_derived_from_label():
    stack = build(
        [
            PullRequest(
                3,
                StackBranch.FEATURE,
                StackBranch.BASE,
                draft=False,
                labels=[StackLabel.IN_REVIEW],
            )
        ]
    )
    assert stack.branches[0].status == BranchStatus.IN_REVIEW


def test_merged_derived_from_predicate_not_labels():
    stack = build(
        [PullRequest(9, StackBranch.LANDED, StackBranch.BASE, draft=False, labels=[])],
        merged={StackBranch.LANDED},
    )
    assert stack.branches[0].status == BranchStatus.MERGED


def test_rebase_label_sets_strategy():
    stack = build(
        [
            PullRequest(
                1,
                StackBranch.FEATURE,
                StackBranch.BASE,
                draft=True,
                labels=[StackLabel.REBASE],
            )
        ]
    )
    assert stack.branches[0].strategy == IntegrationStrategy.REBASE
    stack = build(
        [PullRequest(1, StackBranch.FEATURE, StackBranch.BASE, draft=True, labels=[])]
    )
    assert stack.branches[0].strategy == IntegrationStrategy.MERGE


# %% ordering: parent before child, even when declared out of order


def test_order_places_parent_before_child():
    prs = [
        PullRequest(3, StackBranch.CHILD, StackBranch.PARENT, draft=True),
        PullRequest(2, StackBranch.PARENT, StackBranch.BASE, draft=True),
    ]
    names = [b.name for b in order(build(prs))]
    assert names.index(StackBranch.PARENT) < names.index(StackBranch.CHILD)


# %% promotion policy - simplified: every ready, unblocked branch, no cap or turn order


def test_promotes_ready_root():
    prs = [PullRequest(11, StackBranch.FEATURE, StackBranch.BASE, draft=False)]
    assert next_to_promote(build(prs)).name == StackBranch.FEATURE


def test_nothing_promotes_when_all_draft():
    prs = [PullRequest(5, StackBranch.WORK_IN_PROGRESS, StackBranch.BASE, draft=True)]
    assert next_to_promote(build(prs)) is None


def test_ready_child_blocked_until_parent_lands():
    prs = [
        PullRequest(
            1, StackBranch.PARENT, StackBranch.BASE, draft=True
        ),  # still draft, not upstream
        PullRequest(
            2, StackBranch.CHILD, StackBranch.PARENT, draft=False
        ),  # approved but parent hasn't landed
    ]
    assert next_to_promote(build(prs)) is None


def test_child_promotable_once_parent_reaches_review():
    # there is no per-stack review-slot limit anymore, so a child may promote alongside
    # its own parent the moment the parent has reached in-review - it does not have to
    # wait for the parent to fully merge.
    prs = [
        PullRequest(
            1,
            StackBranch.PARENT,
            StackBranch.BASE,
            draft=False,
            labels=[StackLabel.IN_REVIEW],
        ),
        PullRequest(2, StackBranch.CHILD, StackBranch.PARENT, draft=False),
    ]
    assert next_to_promote(build(prs)).name == StackBranch.CHILD


def test_child_promotable_once_parent_merged():
    prs = [
        PullRequest(1, StackBranch.PARENT, StackBranch.BASE, draft=False),
        PullRequest(2, StackBranch.CHILD, StackBranch.PARENT, draft=False),
    ]
    assert (
        next_to_promote(build(prs, merged={StackBranch.PARENT})).name
        == StackBranch.CHILD
    )


def test_promotion_order_includes_every_ready_unblocked_branch_in_dependency_order():
    # two independent ready roots plus one ready child whose own parent has not yet
    # reached review - all ready roots promote together (no cap), the blocked child does
    # not.
    prs = [
        PullRequest(1, StackBranch.FIRST_ROOT, StackBranch.BASE, draft=False),
        PullRequest(
            2, StackBranch.CHILD_OF_FIRST_ROOT, StackBranch.FIRST_ROOT, draft=False
        ),  # its parent is only ready
        PullRequest(3, StackBranch.SECOND_ROOT, StackBranch.BASE, draft=False),
    ]
    names = [b.name for b in promotion_order(build(prs))]
    assert names == [StackBranch.FIRST_ROOT, StackBranch.SECOND_ROOT]


def test_promotion_order_withholds_a_branch_delegated_for_conflict_resolution():
    # a branch the routine delegated (needs-resolution) is stuck mid-restack, so it must
    # not be promoted even though it is otherwise ready and unblocked.
    prs = [
        PullRequest(
            1,
            StackBranch.STUCK,
            StackBranch.BASE,
            draft=False,
            labels=[StackLabel.NEEDS_RESOLUTION],
        ),
        PullRequest(2, StackBranch.FINE, StackBranch.BASE, draft=False),
    ]
    names = [b.name for b in promotion_order(build(prs))]
    assert names == [StackBranch.FINE]


def test_ci_and_session_carried_onto_branch():
    stack = build(
        [
            PullRequest(
                11,
                StackBranch.FEATURE,
                StackBranch.BASE,
                draft=False,
                ci="failure",
                session="https://claude.ai/code/session_x",
            )
        ]
    )
    assert stack.branches[0].ci == "failure"
    assert stack.branches[0].session == "https://claude.ai/code/session_x"


# %% restack plan


def test_restack_plan_excludes_merged_only():
    prs = [
        PullRequest(1, StackBranch.LANDED, StackBranch.BASE, draft=False),
        PullRequest(
            2,
            StackBranch.UNDER_REVIEW,
            StackBranch.BASE,
            draft=False,
            labels=[StackLabel.IN_REVIEW],
        ),
        PullRequest(
            3, StackBranch.WORK_IN_PROGRESS, StackBranch.UNDER_REVIEW, draft=True
        ),
    ]
    plan = restack_plan(build(prs, merged={StackBranch.LANDED}))
    names = [entry.branch for entry in plan]
    assert StackBranch.LANDED not in names
    assert names == [
        StackBranch.UNDER_REVIEW,
        StackBranch.WORK_IN_PROGRESS,
    ]  # in-review included, parent before child


def test_restack_plan_carries_parent_and_strategy():
    prs = [
        PullRequest(
            2,
            StackBranch.WORK_IN_PROGRESS,
            StackBranch.OFF_BOARD_PARENT,
            draft=True,
            labels=[StackLabel.REBASE],
        )
    ]
    plan = restack_plan(build(prs))
    assert plan == [
        RestackPlanEntry(
            branch=StackBranch.WORK_IN_PROGRESS,
            parent=StackBranch.OFF_BOARD_PARENT,
            strategy=IntegrationStrategy.REBASE,
        )
    ]


def test_restack_plan_reparents_child_of_merged_parent_onto_base():
    # parent merged into main -> its commits are in the base, so the child is reparented
    # onto main (the routine mirrors this by retargeting the child PR's base on GitHub).
    prs = [
        PullRequest(1, StackBranch.PARENT, StackBranch.BASE, draft=False),
        PullRequest(2, StackBranch.CHILD, StackBranch.PARENT, draft=False),
    ]
    plan = restack_plan(build(prs, merged={StackBranch.PARENT}))
    assert plan == [
        RestackPlanEntry(
            branch=StackBranch.CHILD,
            parent=StackBranch.BASE,
            strategy=IntegrationStrategy.MERGE,
        )
    ]


# %% landed parents that no open pull request describes


def test_restack_plan_reparents_child_of_a_landed_parent_with_no_open_pull_request():
    # the board only carries OPEN pull requests, so a parent whose own PR was closed is
    # absent from it entirely - yet its commits are in the upstream base, so its child
    # must still be reparented onto that base rather than left on the landed branch.
    prs = [PullRequest(2, StackBranch.CHILD, StackBranch.LANDED_ELSEWHERE, draft=False)]
    plan = restack_plan(build(prs, merged={StackBranch.LANDED_ELSEWHERE}))
    assert plan == [
        RestackPlanEntry(
            branch=StackBranch.CHILD,
            parent=StackBranch.BASE,
            strategy=IntegrationStrategy.MERGE,
        )
    ]


def test_ready_child_blocked_when_its_only_parent_is_an_unlanded_off_board_branch():
    # an off-board parent is not evidence of a root branch: this one has not landed, so
    # the child is not promotable even though no PR describes the parent.
    prs = [
        PullRequest(2, StackBranch.CHILD, StackBranch.UNLANDED_ELSEWHERE, draft=False)
    ]
    assert next_to_promote(build(prs)) is None


def test_ready_child_promotable_when_its_off_board_parent_has_landed():
    prs = [PullRequest(2, StackBranch.CHILD, StackBranch.LANDED_ELSEWHERE, draft=False)]
    assert (
        next_to_promote(build(prs, merged={StackBranch.LANDED_ELSEWHERE})).name
        == StackBranch.CHILD
    )


# %% configuration layering (personal-notes overrides)

DEFAULT_STACK_TOML = """\
in_review_label = "in-review"
rebase_label = "rebase"
needs_resolution_label = "needs-resolution"
fork_remote = "origin"
upstream_repository = "an-upstream-owner/a-project"
upstream_remote = "upstream"
upstream_base = "main"
"""


def _committed_configuration_path(scratch_repository: ScratchRepository) -> Path:
    """
    Write and commit the repo-default ``stack.toml`` into a scratch repository, beside
    the shell file the personal-notes override is fetched through.

    :param scratch_repository: The scratch repository to write into.
    :return: The path :func:`load_configuration` should be pointed at.
    """
    path = scratch_repository.install_stack_configuration(DEFAULT_STACK_TOML)
    scratch_repository.run_git(
        "remote",
        "add",
        "a-name-nobody-expects",
        A_FORK.clone_url,
    )
    return path


def test_load_configuration_uses_committed_defaults_when_no_personal_notes_branch(
    scratch_repository: ScratchRepository, monkeypatch
):
    configuration_path = _committed_configuration_path(scratch_repository)
    scratch_repository.resolve_notes_remote_to()
    monkeypatch.chdir(scratch_repository.project_root)

    configuration = load_configuration(configuration_path)

    assert configuration.upstream_remote == RemoteName.UPSTREAM


def test_load_configuration_layers_personal_notes_override_on_top_of_defaults(
    scratch_repository: ScratchRepository, monkeypatch
):
    configuration_path = _committed_configuration_path(scratch_repository)
    scratch_repository.publish_notes_branch(
        {
            ProjectLocation.PERSONAL_STACK_CONFIGURATION: 'upstream_remote = "my-own-upstream-name"\n'
        }
    )
    scratch_repository.resolve_notes_remote_to()
    monkeypatch.chdir(scratch_repository.project_root)

    configuration = load_configuration(configuration_path)

    assert configuration.upstream_remote == "my-own-upstream-name"
    assert configuration.upstream_base == StackBranch.BASE  # untouched default


def test_load_configuration_ignores_personal_notes_branch_without_a_stack_file(
    scratch_repository: ScratchRepository, monkeypatch
):
    configuration_path = _committed_configuration_path(scratch_repository)
    scratch_repository.publish_notes_branch({"README.md": "unrelated\n"})
    scratch_repository.resolve_notes_remote_to()
    monkeypatch.chdir(scratch_repository.project_root)

    configuration = load_configuration(configuration_path)

    assert configuration.upstream_remote == RemoteName.UPSTREAM


def test_load_configuration_resolves_the_fork_whatever_the_remote_is_called(
    scratch_repository: ScratchRepository, monkeypatch
):
    """
    Nothing has to be configured: a checkout already knows its own fork.
    """
    configuration_path = _committed_configuration_path(scratch_repository)
    scratch_repository.resolve_notes_remote_to()
    monkeypatch.chdir(scratch_repository.project_root)

    configuration = load_configuration(configuration_path)

    assert configuration.fork_repository == A_FORK
    assert configuration.fork_remote == "a-name-nobody-expects"


def test_load_configuration_takes_the_fork_from_a_personal_notes_override(
    scratch_repository: ScratchRepository, monkeypatch
):
    """
    An override picks between real remotes; it cannot name a fork the checkout cannot
    push to.
    """
    configuration_path = _committed_configuration_path(scratch_repository)
    scratch_repository.run_git(
        "remote", "add", RemoteName.THEIRS, SOMEBODY_ELSES_FORK.clone_url
    )
    scratch_repository.publish_notes_branch(
        {
            ProjectLocation.PERSONAL_STACK_CONFIGURATION: 'fork_repository = "someone-else/their-fork"\n'
        }
    )
    scratch_repository.resolve_notes_remote_to()
    monkeypatch.chdir(scratch_repository.project_root)

    configuration = load_configuration(configuration_path)

    assert configuration.fork_repository == SOMEBODY_ELSES_FORK
    assert configuration.fork_remote == RemoteName.THEIRS


# %% resolving which remote is the fork

UPSTREAM = Repository("an-upstream-owner", "a-project")
FORK = Repository("a-fork-owner", "a-project")


def resolve(remote_urls: dict[str, str], fork_repository: Repository | None = None):
    return resolve_remotes(remote_urls, UPSTREAM, "an-upstream-remote", fork_repository)


def test_the_fork_is_the_remote_that_is_not_the_upstream():
    """
    Names carry no meaning: the fork is identified by the repository its URL points at.
    """
    resolution = resolve(
        {
            RemoteName.ORIGIN: UPSTREAM.clone_url,
            RemoteName.MINE: FORK.clone_url,
        }
    )

    assert resolution.fork == Remote(RemoteName.MINE, FORK)
    assert resolution.upstream == Remote(RemoteName.ORIGIN, UPSTREAM)


def test_the_fork_resolves_the_same_when_origin_happens_to_be_the_fork():
    resolution = resolve(
        {
            RemoteName.ORIGIN: FORK.clone_url,
            RemoteName.UPSTREAM: UPSTREAM.clone_url,
        }
    )

    assert resolution.fork == Remote(RemoteName.ORIGIN, FORK)


def test_the_fork_resolves_from_a_checkout_that_has_only_the_fork():
    """
    A fresh cloud clone has one remote and no upstream at all.
    """
    resolution = resolve({RemoteName.ORIGIN: FORK.clone_url})

    assert resolution.fork == Remote(RemoteName.ORIGIN, FORK)
    assert resolution.upstream is None


def test_a_checkout_without_an_upstream_remote_is_told_how_to_add_one():
    resolution = resolve({RemoteName.ORIGIN: FORK.clone_url})

    assert resolution.upstream_setup_command == (
        "git remote add an-upstream-remote "
        "https://github.com/an-upstream-owner/a-project.git"
    )
    assert resolution.upstream_name == "an-upstream-remote"


def test_nothing_to_add_when_the_upstream_remote_is_already_there():
    resolution = resolve(
        {
            RemoteName.ORIGIN: FORK.clone_url,
            RemoteName.UPSTREAM: UPSTREAM.clone_url,
        }
    )

    assert resolution.upstream_setup_command is None
    assert resolution.upstream_name == RemoteName.UPSTREAM


def test_a_checkout_with_only_the_upstream_is_rejected_rather_than_guessed():
    """
    Treating the upstream as the fork would target every push at the review repository.
    """
    with pytest.raises(ForkRemoteNotFoundError):
        resolve({RemoteName.ORIGIN: UPSTREAM.clone_url})


def test_two_possible_forks_are_rejected_rather_than_guessed():
    with pytest.raises(AmbiguousForkRemoteError):
        resolve(
            {
                RemoteName.MINE: FORK.clone_url,
                RemoteName.THEIRS: ANOTHER_OWNERS_FORK.clone_url,
            }
        )


def test_configuration_disambiguates_two_possible_forks():
    resolution = resolve(
        {
            RemoteName.MINE: FORK.clone_url,
            RemoteName.THEIRS: ANOTHER_OWNERS_FORK.clone_url,
        },
        fork_repository=FORK,
    )

    assert resolution.fork == Remote(RemoteName.MINE, FORK)


def test_a_remote_that_names_no_repository_is_ignored():
    """
    A local-path remote is not a candidate, and must not make the fork ambiguous.
    """
    resolution = resolve(
        {
            RemoteName.ORIGIN: FORK.clone_url,
            RemoteName.BACKUP: "/srv/git/mirror",
        }
    )

    assert resolution.fork == Remote(RemoteName.ORIGIN, FORK)


# %% the configuration the shell tooling reads


def test_every_setting_is_printed_under_its_own_field_name(capsys):
    """
    Callers read one setting by name out of this output, so a key that is not a field name
    is a key nobody can look up - and a field that never prints is a setting nobody can read.
    """
    print_configuration(make_configuration())

    printed = dict(line.split("\t") for line in capsys.readouterr().out.splitlines())

    assert printed == {
        StackSetting.IN_REVIEW_LABEL: StackLabel.IN_REVIEW,
        StackSetting.REBASE_LABEL: StackLabel.REBASE,
        StackSetting.NEEDS_RESOLUTION_LABEL: StackLabel.NEEDS_RESOLUTION,
        StackSetting.FORK_REPOSITORY: "a-fork-owner/a-fork",
        StackSetting.FORK_REMOTE: RemoteName.ORIGIN,
        StackSetting.UPSTREAM_REPOSITORY: "an-upstream-owner/a-project",
        StackSetting.UPSTREAM_REMOTE: RemoteName.UPSTREAM,
        StackSetting.UPSTREAM_BASE: StackBranch.BASE,
    }


def test_a_checkout_missing_its_upstream_remote_is_printed_the_command_that_adds_it(
    capsys,
):
    print_configuration(
        make_configuration(upstream_setup_command="git remote add upstream a-url")
    )

    printed = dict(line.split("\t") for line in capsys.readouterr().out.splitlines())

    assert printed["upstream_setup_command"] == "git remote add upstream a-url"


def test_nothing_is_printed_for_a_setup_command_that_is_not_needed(capsys):
    """
    An empty value would read as a command to run, so the line is absent rather than
    blank.
    """
    print_configuration(make_configuration())

    assert "upstream_setup_command" not in capsys.readouterr().out


# %% a whole stack through its lifecycle

# The unit tests above each exercise one function against one or two pull requests.
# These walk a single realistic stack through the transitions the README describes -
# approve, promote, land, restack - asserting the derived state at each step, because
# the interactions between those stages are what a per-function test cannot reach.


def a_deep_stack_beside_an_independent_branch(
    approved: Container[str] = frozenset(),
    promoted: Container[str] = frozenset(),
    withheld: Container[str] = frozenset(),
    landed: Container[str] = frozenset(),
):
    """
    Two independent stacks off `main`, the first three deep and the second a single
    branch.

    :param approved: Branches the developer has un-drafted.
    :param promoted: Branches carrying the in-review label.
    :param withheld: Branches delegated for conflict resolution.
    :param landed: Branches that are ancestors of the upstream base.
    :return: The stack as the tooling derives it.
    """
    deep = [
        (StackBranch.ENGINE, StackBranch.BASE),
        (StackBranch.ENGINE_UI, StackBranch.ENGINE),
        (StackBranch.ENGINE_DOCS, StackBranch.ENGINE_UI),
    ]
    aside = [(StackBranch.PARSER, StackBranch.BASE)]
    pull_requests = [
        PullRequest(
            number,
            name,
            parent,
            draft=name not in approved,
            labels=([StackLabel.IN_REVIEW] if name in promoted else [])
            + ([StackLabel.NEEDS_RESOLUTION] if name in withheld else []),
        )
        for number, (name, parent) in enumerate([*deep, *aside], start=1)
    ]
    return build(pull_requests, merged=landed)


def test_nothing_promotes_while_the_whole_stack_is_still_draft():
    assert promotion_order(a_deep_stack_beside_an_independent_branch()) == []


def test_approving_a_root_promotes_it_and_nothing_above_it():
    """
    Un-drafting is the approval gate, and it approves one branch rather than a whole
    stack.
    """
    stack = a_deep_stack_beside_an_independent_branch(
        approved={StackBranch.ENGINE, StackBranch.ENGINE_UI}
    )

    assert [branch.name for branch in promotion_order(stack)] == [StackBranch.ENGINE]


def test_promoting_a_parent_unblocks_the_child_behind_it():
    """
    A child may follow its parent upstream once the parent is in review - it does not
    wait for the parent to merge.
    """
    stack = a_deep_stack_beside_an_independent_branch(
        approved={StackBranch.ENGINE, StackBranch.ENGINE_UI},
        promoted={StackBranch.ENGINE},
    )

    assert [branch.name for branch in promotion_order(stack)] == [StackBranch.ENGINE_UI]


def test_both_stacks_promote_together_since_they_do_not_depend_on_each_other():
    stack = a_deep_stack_beside_an_independent_branch(
        approved={StackBranch.ENGINE, StackBranch.PARSER}
    )

    assert [branch.name for branch in promotion_order(stack)] == [
        StackBranch.ENGINE,
        StackBranch.PARSER,
    ]


def test_a_branch_delegated_for_conflict_resolution_is_held_back_alone():
    """
    Withholding one branch must not withhold an unrelated stack.
    """
    stack = a_deep_stack_beside_an_independent_branch(
        approved={StackBranch.ENGINE, StackBranch.PARSER}, withheld={StackBranch.ENGINE}
    )

    assert [branch.name for branch in promotion_order(stack)] == [StackBranch.PARSER]


def test_landing_a_root_reparents_only_its_own_child():
    """
    The landed branch drops out of the plan and its child moves onto the base, while the
    branch above keeps the parent it still has and the untouched stack keeps its own.
    """
    stack = a_deep_stack_beside_an_independent_branch(landed={StackBranch.ENGINE})

    assert restack_plan(stack) == [
        RestackPlanEntry(
            branch=StackBranch.ENGINE_UI,
            parent=StackBranch.BASE,
            strategy=IntegrationStrategy.MERGE,
        ),
        RestackPlanEntry(
            branch=StackBranch.ENGINE_DOCS,
            parent=StackBranch.ENGINE_UI,
            strategy=IntegrationStrategy.MERGE,
        ),
        RestackPlanEntry(
            branch=StackBranch.PARSER,
            parent=StackBranch.BASE,
            strategy=IntegrationStrategy.MERGE,
        ),
    ]


def test_landing_a_root_that_no_open_pull_request_describes_still_reparents():
    """
    The case that motivated deciding `merged` by git ancestry: a parent whose own pull
    request was closed rather than merged is absent from the board entirely, and the
    child must still be moved off it.
    """
    orphaned = build(
        [PullRequest(2, StackBranch.ENGINE_UI, StackBranch.ENGINE, draft=True)],
        merged={StackBranch.ENGINE},
    )

    assert restack_plan(orphaned) == [
        RestackPlanEntry(
            branch=StackBranch.ENGINE_UI,
            parent=StackBranch.BASE,
            strategy=IntegrationStrategy.MERGE,
        )
    ]
    assert orphaned.has_landed_upstream(StackBranch.ENGINE)


def test_a_stack_lands_bottom_up_over_successive_runs():
    """
    Each branch reaches the base only after the one below it has, so the plan shortens
    from the bottom as the stack drains.
    """
    after_first = a_deep_stack_beside_an_independent_branch(landed={StackBranch.ENGINE})
    after_second = a_deep_stack_beside_an_independent_branch(
        landed={StackBranch.ENGINE, StackBranch.ENGINE_UI}
    )

    assert [entry.branch for entry in restack_plan(after_first)] == [
        StackBranch.ENGINE_UI,
        StackBranch.ENGINE_DOCS,
        StackBranch.PARSER,
    ]
    assert [entry.branch for entry in restack_plan(after_second)] == [
        StackBranch.ENGINE_DOCS,
        StackBranch.PARSER,
    ]
    assert restack_plan(after_second)[0] == RestackPlanEntry(
        branch=StackBranch.ENGINE_DOCS,
        parent=StackBranch.BASE,
        strategy=IntegrationStrategy.MERGE,
    )


# %% label writes


def test_adding_a_label_keeps_every_label_the_pull_request_already_carries():
    """
    The label write replaces the whole set, so computing it from the addition alone
    silently wipes the rest - which has happened, stripping `in-review` off branches that
    were already promoted.
    """
    configuration = make_configuration()

    write = LabelWrite.replacing(
        [configuration.in_review_label, StackLabel.SOMEBODY_ELSES],
        added=[configuration.needs_resolution_label],
    )

    assert write.labels == (
        configuration.in_review_label,
        StackLabel.SOMEBODY_ELSES,
        configuration.needs_resolution_label,
    )


def test_removing_a_label_keeps_every_other_label():
    configuration = make_configuration()

    write = LabelWrite.replacing(
        [configuration.in_review_label, StackLabel.SOMEBODY_ELSES],
        removed=[StackLabel.SOMEBODY_ELSES],
    )

    assert write.labels == (configuration.in_review_label,)


def test_adding_a_label_already_carried_leaves_the_set_unchanged():
    carried = make_configuration().in_review_label

    write = LabelWrite.replacing([carried], added=[carried])

    assert write.labels == (carried,)


def test_removing_a_label_that_is_not_there_leaves_the_set_unchanged():
    configuration = make_configuration()

    write = LabelWrite.replacing(
        [configuration.in_review_label], removed=[configuration.rebase_label]
    )

    assert write.labels == (configuration.in_review_label,)


def test_asking_to_add_and_remove_one_label_at_once_is_refused():
    """
    Either outcome would be a guess at what the caller meant, and the wrong guess is a
    label silently kept or silently dropped.
    """
    configuration = make_configuration()

    with pytest.raises(ContradictoryLabelWriteError):
        LabelWrite.replacing(
            [configuration.in_review_label],
            added=[configuration.rebase_label],
            removed=[configuration.rebase_label],
        )


# %% move check


def a_proposed_push(
    source: str = StackBranch.ENGINE,
    destination: str = StackBranch.ENGINE,
    destination_remote: str = RemoteName.ORIGIN,
) -> ProposedCommitMove:
    """
    A proposed push, defaulting to the one shape that is always allowed.

    :param source: The branch whose commits would move.
    :param destination: The branch they would land on.
    :param destination_remote: The remote holding the destination.
    :return: The proposed move.
    """
    return ProposedCommitMove(
        action=CommitMoveAction.PUSH,
        source=source,
        destination=destination,
        destination_remote=destination_remote,
    )


def checks_over_that_stack(
    checked_out_branch: str = StackBranch.ENGINE,
    ancestors: Container[str] = frozenset(),
) -> CommitMoveChecks:
    """
    A move check over the stack above.

    :param checked_out_branch: What ``git branch --show-current`` would report.
    :param ancestors: Branches already contained in the move's source.
    :return: The move check to ask for refusals.
    """
    return CommitMoveChecks(
        stack=a_deep_stack_beside_an_independent_branch(),
        checked_out_branch=checked_out_branch,
        is_ancestor=lambda candidate, _descendant: candidate in ancestors,
    )


def test_pushing_the_checked_out_branch_onto_itself_is_allowed():
    assert checks_over_that_stack().refusals(a_proposed_push()) == []


def test_pushing_while_another_branch_is_checked_out_is_refused():
    """
    The checked-out branch is the one whose content actually moves, so a mismatch moves
    something other than what was intended.
    """
    refusals = checks_over_that_stack(checked_out_branch=StackBranch.PARSER).refusals(
        a_proposed_push()
    )

    assert [refusal.reason for refusal in refusals] == [RefusalReason.NOT_CHECKED_OUT]
    assert StackBranch.PARSER in refusals[0].explanation


def test_a_push_naming_a_different_branch_on_each_side_is_refused():
    refusals = checks_over_that_stack().refusals(
        a_proposed_push(destination=StackBranch.ENGINE_UI)
    )

    assert [refusal.reason for refusal in refusals] == [
        RefusalReason.MISMATCHED_BRANCH_NAMES
    ]


def test_a_destination_on_the_upstream_remote_is_refused():
    """
    Every push in this workflow goes to the fork; the upstream is written only by
    opening a pull request against it.
    """
    refusals = checks_over_that_stack().refusals(
        a_proposed_push(destination_remote=RemoteName.UPSTREAM)
    )

    assert [refusal.reason for refusal in refusals] == [RefusalReason.NOT_THE_FORK]
    assert RemoteName.UPSTREAM in refusals[0].explanation


def test_a_push_that_would_make_a_child_an_ancestor_of_its_parent_is_refused():
    """
    GitHub reads a pull request whose head is contained in its base as merged, so this
    push would falsely close the child.
    """
    refusals = checks_over_that_stack(ancestors={StackBranch.ENGINE_UI}).refusals(
        a_proposed_push()
    )

    assert [refusal.reason for refusal in refusals] == [RefusalReason.FALSE_MERGE]
    assert StackBranch.ENGINE_UI in refusals[0].explanation


def test_an_unrelated_branch_contained_in_the_source_is_not_a_false_merge():
    """
    Only a child of the destination can be falsely merged by pushing to it.
    """
    assert (
        checks_over_that_stack(ancestors={StackBranch.PARSER}).refusals(
            a_proposed_push()
        )
        == []
    )


def test_every_reason_to_refuse_is_reported_rather_than_only_the_first():
    """
    Fixing one problem and re-running to discover the next is how a half-applied move
    gets made.
    """
    refusals = checks_over_that_stack(checked_out_branch=StackBranch.PARSER).refusals(
        a_proposed_push(
            destination=StackBranch.ENGINE_UI, destination_remote=RemoteName.UPSTREAM
        )
    )

    assert [refusal.reason for refusal in refusals] == [
        RefusalReason.NOT_CHECKED_OUT,
        RefusalReason.MISMATCHED_BRANCH_NAMES,
        RefusalReason.NOT_THE_FORK,
    ]


# %% promotion links


def a_promotion_link(title: str = "A title", body: str = "A body") -> PromotionLink:
    """
    The compare-and-create link for that stack's root branch.

    :param title: The title to prefill.
    :param body: The body to prefill.
    :return: The built link.
    """
    return PromotionLink.build(make_configuration(), StackBranch.ENGINE, title, body)


def test_the_link_compares_the_upstream_base_against_the_fork_branch():
    assert a_promotion_link().url.startswith(
        "https://github.com/an-upstream-owner/a-project/compare/"
        "main...a-fork-owner:engine?expand=1"
    )


def test_the_title_and_body_are_encoded_rather_than_pasted_in_raw():
    """
    An unencoded ``&`` or ``#`` truncates the query string at that character, so the
    prefill silently loses everything after it.
    """
    url = a_promotion_link(title="Fix A & B", body="see #106").url

    assert "title=Fix%20A%20%26%20B" in url
    assert "body=see%20%23106" in url


def test_a_body_within_the_limit_is_left_whole():
    link = a_promotion_link(body="short")

    assert not link.body_was_truncated
    assert "body=short" in link.url


def test_an_oversized_body_is_truncated_rather_than_silently_dropped():
    """
    Over the limit the whole prefill is discarded by the server, so the link arrives
    with an empty description and nobody is told.
    """
    link = a_promotion_link(body="x" * 20000)

    assert link.body_was_truncated
    assert link.url.endswith(PromotionLink.TRUNCATION_MARKER)
    assert len(link.url) <= PromotionLink.URL_CHARACTER_LIMIT


def test_a_link_that_cannot_fit_even_without_a_description_is_refused():
    """
    Returning a link known to be over the limit would be the silent failure this class
    exists to prevent, so the one input that cannot be fixed by shortening the body says
    so.
    """
    with pytest.raises(PromotionLinkTooLongError):
        a_promotion_link(title="t" * 20000, body="")


# %% landed parents


def test_a_child_of_a_landed_parent_is_named_with_the_base_it_should_get():
    stack = a_deep_stack_beside_an_independent_branch(landed={StackBranch.ENGINE})

    assert reparents(stack) == [
        Reparent(
            branch=StackBranch.ENGINE_UI,
            pull_request_number=2,
            current_base=StackBranch.ENGINE,
            target_base=StackBranch.BASE,
        )
    ]


def test_a_child_already_based_on_the_upstream_base_needs_no_reparent():
    assert reparents(a_deep_stack_beside_an_independent_branch()) == []


def test_a_child_of_a_landed_parent_with_no_open_pull_request_is_still_named():
    """
    The board carries only open pull requests, so a parent whose own was closed is absent
    from it entirely - the case that orphaned a real pull request for six days.
    """
    orphaned = build(
        [PullRequest(2, StackBranch.ENGINE_UI, StackBranch.ENGINE, draft=True)],
        merged={StackBranch.ENGINE},
    )

    assert [reparent.branch for reparent in reparents(orphaned)] == [
        StackBranch.ENGINE_UI
    ]


def test_a_branch_that_has_landed_is_named_for_labelling_and_closing():
    stack = a_deep_stack_beside_an_independent_branch(landed={StackBranch.ENGINE})

    assert [branch.name for branch in landed_branches(stack)] == [StackBranch.ENGINE]


def test_nothing_has_landed_while_the_whole_stack_is_still_open():
    assert landed_branches(a_deep_stack_beside_an_independent_branch()) == []


# %% configuration named rather than inferred


def test_a_named_fork_is_used_where_inference_would_have_refused_to_guess(
    scratch_repository: ScratchRepository, monkeypatch
):
    """
    Two candidate remotes are ambiguous to inference; naming the fork settles it without
    anything being written to the checkout.
    """
    configuration_path = _committed_configuration_path(scratch_repository)
    scratch_repository.run_git(
        "remote", "add", RemoteName.THEIRS, SOMEBODY_ELSES_FORK.clone_url
    )
    scratch_repository.resolve_notes_remote_to()
    monkeypatch.chdir(scratch_repository.project_root)

    with pytest.raises(AmbiguousForkRemoteError):
        load_configuration(configuration_path)

    configuration = load_configuration(
        configuration_path, fork_repository=SOMEBODY_ELSES_FORK
    )

    assert configuration.fork_repository == SOMEBODY_ELSES_FORK
    assert configuration.fork_remote == RemoteName.THEIRS


def test_a_named_upstream_replaces_the_committed_default(
    scratch_repository: ScratchRepository, monkeypatch
):
    configuration_path = _committed_configuration_path(scratch_repository)
    scratch_repository.resolve_notes_remote_to()
    monkeypatch.chdir(scratch_repository.project_root)

    configuration = load_configuration(
        configuration_path,
        upstream_repository=Repository("a-different-upstream", "a-project"),
    )

    assert configuration.upstream_repository == Repository(
        "a-different-upstream", "a-project"
    )
    assert configuration.upstream_setup_command == (
        "git remote add upstream https://github.com/a-different-upstream/a-project.git"
    )


# %% the command line a caller acts on the exit status of


@pytest.fixture
def offline_checkout(scratch_repository: ScratchRepository) -> ScratchRepository:
    """
    A checkout naming its upstream, whose personal-notes remote is a local bare
    repository.

    Resolving configuration fetches that branch, so pointing it at a local path is what
    keeps these tests off the network.

    :param scratch_repository: The scratch repository to point.
    :return: The same repository, now resolving its notes remote locally.
    """
    scratch_repository.resolve_notes_remote_to()
    scratch_repository.write(
        ProjectLocation.PROJECT_STACK_CONFIGURATION,
        DatasetLocation.SCRATCH_FORK_STACK_CONFIGURATION.read_text(),
    )
    return scratch_repository


def run_stack(
    checkout: ScratchRepository, *arguments: str
) -> subprocess.CompletedProcess[str]:
    """
    Invoke the tool as a caller does, so its exit status is exercised rather than
    assumed.

    :param checkout: The repository to run in.
    :param arguments: The command and its flags.
    :return: The finished subprocess.
    """
    return PythonModuleRunner(
        project_root=checkout.project_root, module_name=STACK_MODULE
    ).run(*arguments)


def test_an_unknown_command_is_a_usage_error(offline_checkout: ScratchRepository):
    assert (
        run_stack(offline_checkout, "not-a-command").returncode == StackExitCode.USAGE
    )


def test_a_label_write_prints_the_complete_set_one_label_per_line(
    offline_checkout: ScratchRepository,
):
    """
    One per line rather than a joined list: a label may contain whatever a separator
    would have been.
    """
    result = run_stack(
        offline_checkout,
        Command.LABELS,
        "--current",
        StackLabel.IN_REVIEW,
        "--current",
        StackLabel.BUG,
        "--add",
        StackLabel.REBASE,
    )

    assert result.returncode == StackExitCode.SUCCESS
    assert result.stdout.splitlines() == [
        StackLabel.IN_REVIEW,
        StackLabel.BUG,
        StackLabel.REBASE,
    ]


def test_a_contradictory_label_write_is_refused_rather_than_guessed_at(
    offline_checkout: ScratchRepository,
):
    result = run_stack(
        offline_checkout,
        Command.LABELS,
        "--add",
        StackLabel.REBASE,
        "--remove",
        StackLabel.REBASE,
    )

    assert result.returncode == StackExitCode.USAGE
    assert StackLabel.REBASE in result.stderr


def test_a_checkout_whose_fork_cannot_be_identified_says_so_by_status(
    offline_checkout: ScratchRepository,
):
    """
    A caller has to tell "I cannot know which remote is yours" from every other failure
    without reading stderr, because that one is the question it can put to the user.
    """
    result = run_stack(offline_checkout, Command.CONFIGURATION)

    assert result.returncode == StackExitCode.REMOTES_UNRESOLVED


def test_a_project_naming_no_upstream_says_so_by_status(
    offline_checkout: ScratchRepository,
):
    """
    The upstream is the one setting only the project knows, and its absence is a setup
    step a caller can name, not a failure to read the checkout.
    """
    (
        offline_checkout.project_root / ProjectLocation.PROJECT_STACK_CONFIGURATION
    ).unlink()
    offline_checkout.run_git("remote", "add", RemoteName.MINE, A_FORK.clone_url)

    result = run_stack(offline_checkout, Command.CONFIGURATION)

    assert result.returncode == StackExitCode.UPSTREAM_UNCONFIGURED
    assert str(ProjectLocation.PROJECT_STACK_CONFIGURATION) in result.stderr


def test_a_readable_checkout_with_no_board_reports_the_missing_board_instead(
    offline_checkout: ScratchRepository,
):
    offline_checkout.run_git("remote", "add", RemoteName.MINE, A_FORK.clone_url)

    result = run_stack(offline_checkout, Command.STATUS)

    assert result.returncode == StackExitCode.BOARD_UNAVAILABLE


def test_a_named_fork_and_upstream_are_used_where_inference_would_have_refused(
    offline_checkout: ScratchRepository,
):
    """
    Two candidate remotes are ambiguous, so a caller that already knows the answer must
    be able to say so rather than be blocked by the guess it does not need.
    """
    offline_checkout.run_git("remote", "add", RemoteName.MINE, A_FORK.clone_url)
    offline_checkout.run_git(
        "remote", "add", RemoteName.THEIRS, SOMEBODY_ELSES_FORK.clone_url
    )

    assert (
        run_stack(offline_checkout, Command.CONFIGURATION).returncode
        == StackExitCode.REMOTES_UNRESOLVED
    )

    result = run_stack(
        offline_checkout,
        Command.CONFIGURATION,
        "--fork",
        "a-fork-owner/a-fork",
        "--upstream",
        "an-upstream-owner/a-project",
    )

    assert result.returncode == StackExitCode.SUCCESS
    printed = dict(line.split("\t") for line in result.stdout.splitlines())
    assert printed["fork_repository"] == "a-fork-owner/a-fork"
    assert printed["fork_remote"] == RemoteName.MINE
    assert printed["upstream_repository"] == "an-upstream-owner/a-project"


def test_a_fork_that_is_not_owner_and_name_is_a_usage_error(
    offline_checkout: ScratchRepository,
):
    result = run_stack(
        offline_checkout, Command.CONFIGURATION, "--fork", "not-a-repository"
    )

    assert result.returncode == StackExitCode.USAGE


def test_a_promotion_link_is_built_from_the_resolved_repositories(
    offline_checkout: ScratchRepository,
):
    offline_checkout.run_git("remote", "add", RemoteName.MINE, A_FORK.clone_url)

    result = run_stack(
        offline_checkout,
        Command.PROMOTION_LINK,
        "--branch",
        StackBranch.ENGINE,
        "--title",
        "A title",
    )

    assert result.returncode == StackExitCode.SUCCESS
    assert result.stdout.strip().endswith(
        "...a-fork-owner:engine?expand=1&title=A%20title&body="
    )
