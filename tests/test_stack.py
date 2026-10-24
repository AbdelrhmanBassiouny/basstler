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
from enum import Enum, StrEnum
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

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
    CommandOption,
    ProposedCommitMove,
    RefusalReason,
    PromotionLink,
    PromotionLinkParameter,
    PromotionLinkTooLongError,
    PrintedConfiguration,
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

from basstler.locations import PackageLocation, ProjectLocation

from .constants.paths import DatasetLocation
from .constants.stack import RemoteName, StackBranch, StackLabel
from .scratch_repository import ScratchRepository
from .script_runner import PythonModuleRunner


class StackRepository(Enum):
    """
    The repositories the stack suites' checkouts and configurations name.
    """

    FORK = Repository("a-fork-owner", "a-fork")
    """
    The fork a scratch checkout's remote points at.
    """

    SOMEBODY_ELSES_FORK = Repository("someone-else", "their-fork")
    """
    A fork other than the one the configuration names.
    """

    SAME_NAMED_FORK = Repository("a-fork-owner", "a-project")
    """
    A fork named like the upstream it was forked from.
    """

    ANOTHER_OWNERS_FORK = Repository("another-owner", "a-project")
    """
    A second fork of the upstream, beside :attr:`SAME_NAMED_FORK`.
    """

    UPSTREAM = Repository("an-upstream-owner", "a-project")
    """
    The upstream every fork here is forked from.
    """

    DIFFERENT_UPSTREAM = Repository("a-different-upstream", "a-project")
    """
    An upstream named on the command line in place of the committed one.
    """


class StackSampleText(StrEnum):
    """
    The text the stack suites feed in where only its shape matters.
    """

    CHECK_CONCLUSION = "failure"
    """
    A pull request's CI conclusion, carried through untouched.
    """

    SESSION_LINK = "https://claude.ai/code/session_x"
    """
    The session a pull request was opened from.
    """

    TITLE = "A title"
    """
    A promotion link's title.
    """

    BODY = "A body"
    """
    A promotion link's description.
    """

    SHORT_BODY = "short"
    """
    A description well within the link's length limit.
    """

    TITLE_WITH_SEPARATORS = "Fix A & B"
    """
    A title holding a character that would end a query parameter unencoded.
    """

    BODY_WITH_FRAGMENT = "see #106"
    """
    A description holding a character that would start a URL fragment unencoded.
    """

    FILLER = "x"
    """
    One character, repeated to make a text too long for a link.
    """

    LOCAL_PATH_REMOTE = "/srv/git/mirror"
    """
    A remote URL that is a local path rather than a repository.
    """

    UNRELATED_FILE = "README.md"
    """
    A notes-branch file that is not the stack configuration.
    """

    UNRELATED_CONTENT = "unrelated\n"
    """
    Its content.
    """

    UNKNOWN_COMMAND = "not-a-command"
    """
    A command the tool does not answer.
    """

    NOT_A_REPOSITORY = "not-a-repository"
    """
    A repository reference missing its ``owner/`` part.
    """


def make_configuration(upstream_setup_command: str | None = None) -> Configuration:
    return Configuration(
        in_review_label=StackLabel.IN_REVIEW,
        rebase_label=StackLabel.REBASE,
        needs_resolution_label=StackLabel.NEEDS_RESOLUTION,
        fork_repository=StackRepository.FORK.value,
        fork_remote=RemoteName.ORIGIN,
        upstream_repository=StackRepository.UPSTREAM.value,
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
    # a branch a maintenance pass delegated (needs-resolution) is stuck mid-restack, so it must
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
                ci=StackSampleText.CHECK_CONCLUSION,
                session=StackSampleText.SESSION_LINK,
            )
        ]
    )
    assert stack.branches[0].ci == StackSampleText.CHECK_CONCLUSION
    assert stack.branches[0].session == StackSampleText.SESSION_LINK


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
    # onto main (the maintenance skill mirrors this by retargeting the child PR's base on GitHub).
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


def a_setting_line(setting: StackSetting, value: object) -> str:
    """
    :param setting: The setting to write.
    :param value: Its value.
    :return: The ``stack.toml`` line giving *setting* that value.
    """
    return f'{setting} = "{value}"\n'


def a_remote_addition_command(name: str, repository: Repository) -> str:
    """
    :param name: What the remote is to be called.
    :param repository: The repository it is to point at.
    :return: The command adding that remote.
    """
    return f"git remote add {name} {repository.clone_url}"


def _committed_configuration_path(scratch_repository: ScratchRepository) -> Path:
    """
    Write and commit the repo-default ``stack.toml`` into a scratch repository, beside
    the shell file the personal-notes override is fetched through.

    :param scratch_repository: The scratch repository to write into.
    :return: The path :func:`load_configuration` should be pointed at.
    """
    path = scratch_repository.install_stack_configuration(
        DatasetLocation.COMMITTED_DEFAULT_STACK_CONFIGURATION.read_text()
    )
    scratch_repository.add_remote(
        RemoteName.UNEXPECTED, StackRepository.FORK.value.clone_url
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
            ProjectLocation.PERSONAL_STACK_CONFIGURATION: a_setting_line(
                StackSetting.UPSTREAM_REMOTE, RemoteName.PERSONAL_UPSTREAM
            )
        }
    )
    scratch_repository.resolve_notes_remote_to()
    monkeypatch.chdir(scratch_repository.project_root)

    configuration = load_configuration(configuration_path)

    assert configuration.upstream_remote == RemoteName.PERSONAL_UPSTREAM
    assert configuration.upstream_base == StackBranch.BASE  # untouched default


def test_load_configuration_ignores_personal_notes_branch_without_a_stack_file(
    scratch_repository: ScratchRepository, monkeypatch
):
    configuration_path = _committed_configuration_path(scratch_repository)
    scratch_repository.publish_notes_branch(
        {StackSampleText.UNRELATED_FILE: StackSampleText.UNRELATED_CONTENT}
    )
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

    assert configuration.fork_repository == StackRepository.FORK.value
    assert configuration.fork_remote == RemoteName.UNEXPECTED


def test_load_configuration_takes_the_fork_from_a_personal_notes_override(
    scratch_repository: ScratchRepository, monkeypatch
):
    """
    An override picks between real remotes; it cannot name a fork the checkout cannot
    push to.
    """
    configuration_path = _committed_configuration_path(scratch_repository)
    scratch_repository.add_remote(
        RemoteName.THEIRS, StackRepository.SOMEBODY_ELSES_FORK.value.clone_url
    )
    scratch_repository.publish_notes_branch(
        {
            ProjectLocation.PERSONAL_STACK_CONFIGURATION: a_setting_line(
                StackSetting.FORK_REPOSITORY,
                StackRepository.SOMEBODY_ELSES_FORK.value,
            )
        }
    )
    scratch_repository.resolve_notes_remote_to()
    monkeypatch.chdir(scratch_repository.project_root)

    configuration = load_configuration(configuration_path)

    assert configuration.fork_repository == StackRepository.SOMEBODY_ELSES_FORK.value
    assert configuration.fork_remote == RemoteName.THEIRS


# %% resolving which remote is the fork


def resolve(remote_urls: dict[str, str], fork_repository: Repository | None = None):
    return resolve_remotes(
        remote_urls,
        StackRepository.UPSTREAM.value,
        RemoteName.PREFERRED_UPSTREAM,
        fork_repository,
    )


def test_the_fork_is_the_remote_that_is_not_the_upstream():
    """
    Names carry no meaning: the fork is identified by the repository its URL points at.
    """
    resolution = resolve(
        {
            RemoteName.ORIGIN: StackRepository.UPSTREAM.value.clone_url,
            RemoteName.MINE: StackRepository.SAME_NAMED_FORK.value.clone_url,
        }
    )

    assert resolution.fork == Remote(
        RemoteName.MINE, StackRepository.SAME_NAMED_FORK.value
    )
    assert resolution.upstream == Remote(
        RemoteName.ORIGIN, StackRepository.UPSTREAM.value
    )


def test_the_fork_resolves_the_same_when_origin_happens_to_be_the_fork():
    resolution = resolve(
        {
            RemoteName.ORIGIN: StackRepository.SAME_NAMED_FORK.value.clone_url,
            RemoteName.UPSTREAM: StackRepository.UPSTREAM.value.clone_url,
        }
    )

    assert resolution.fork == Remote(
        RemoteName.ORIGIN, StackRepository.SAME_NAMED_FORK.value
    )


def test_the_fork_resolves_from_a_checkout_that_has_only_the_fork():
    """
    A fresh cloud clone has one remote and no upstream at all.
    """
    resolution = resolve(
        {RemoteName.ORIGIN: StackRepository.SAME_NAMED_FORK.value.clone_url}
    )

    assert resolution.fork == Remote(
        RemoteName.ORIGIN, StackRepository.SAME_NAMED_FORK.value
    )
    assert resolution.upstream is None


def test_a_checkout_without_an_upstream_remote_is_told_how_to_add_one():
    resolution = resolve(
        {RemoteName.ORIGIN: StackRepository.SAME_NAMED_FORK.value.clone_url}
    )

    assert resolution.upstream_setup_command == a_remote_addition_command(
        RemoteName.PREFERRED_UPSTREAM, StackRepository.UPSTREAM.value
    )
    assert resolution.upstream_name == RemoteName.PREFERRED_UPSTREAM


def test_nothing_to_add_when_the_upstream_remote_is_already_there():
    resolution = resolve(
        {
            RemoteName.ORIGIN: StackRepository.SAME_NAMED_FORK.value.clone_url,
            RemoteName.UPSTREAM: StackRepository.UPSTREAM.value.clone_url,
        }
    )

    assert resolution.upstream_setup_command is None
    assert resolution.upstream_name == RemoteName.UPSTREAM


def test_a_checkout_with_only_the_upstream_is_rejected_rather_than_guessed():
    """
    Treating the upstream as the fork would target every push at the review repository.
    """
    with pytest.raises(ForkRemoteNotFoundError):
        resolve({RemoteName.ORIGIN: StackRepository.UPSTREAM.value.clone_url})


def test_two_possible_forks_are_rejected_rather_than_guessed():
    with pytest.raises(AmbiguousForkRemoteError):
        resolve(
            {
                RemoteName.MINE: StackRepository.SAME_NAMED_FORK.value.clone_url,
                RemoteName.THEIRS: StackRepository.ANOTHER_OWNERS_FORK.value.clone_url,
            }
        )


def test_configuration_disambiguates_two_possible_forks():
    resolution = resolve(
        {
            RemoteName.MINE: StackRepository.SAME_NAMED_FORK.value.clone_url,
            RemoteName.THEIRS: StackRepository.ANOTHER_OWNERS_FORK.value.clone_url,
        },
        fork_repository=StackRepository.SAME_NAMED_FORK.value,
    )

    assert resolution.fork == Remote(
        RemoteName.MINE, StackRepository.SAME_NAMED_FORK.value
    )


def test_a_remote_that_names_no_repository_is_ignored():
    """
    A local-path remote is not a candidate, and must not make the fork ambiguous.
    """
    resolution = resolve(
        {
            RemoteName.ORIGIN: StackRepository.SAME_NAMED_FORK.value.clone_url,
            RemoteName.BACKUP: StackSampleText.LOCAL_PATH_REMOTE,
        }
    )

    assert resolution.fork == Remote(
        RemoteName.ORIGIN, StackRepository.SAME_NAMED_FORK.value
    )


# %% the configuration the shell tooling reads


def test_every_setting_is_printed_under_its_own_field_name(capsys):
    """
    Callers read one setting by name out of this output, so a key that is not a field name
    is a key nobody can look up - and a field that never prints is a setting nobody can read.
    """
    print_configuration(make_configuration())

    printed = PrintedConfiguration.read(capsys.readouterr().out)

    assert printed == {
        StackSetting.IN_REVIEW_LABEL: StackLabel.IN_REVIEW,
        StackSetting.REBASE_LABEL: StackLabel.REBASE,
        StackSetting.NEEDS_RESOLUTION_LABEL: StackLabel.NEEDS_RESOLUTION,
        StackSetting.FORK_REPOSITORY: StackRepository.FORK.value.full_name,
        StackSetting.FORK_REMOTE: RemoteName.ORIGIN,
        StackSetting.UPSTREAM_REPOSITORY: StackRepository.UPSTREAM.value.full_name,
        StackSetting.UPSTREAM_REMOTE: RemoteName.UPSTREAM,
        StackSetting.UPSTREAM_BASE: StackBranch.BASE,
    }


def test_a_checkout_missing_its_upstream_remote_is_printed_the_command_that_adds_it(
    capsys,
):
    setup_command = a_remote_addition_command(
        RemoteName.UPSTREAM, StackRepository.UPSTREAM.value
    )
    print_configuration(make_configuration(upstream_setup_command=setup_command))

    printed = PrintedConfiguration.read(capsys.readouterr().out)

    assert printed[StackSetting.UPSTREAM_SETUP_COMMAND] == setup_command


def test_nothing_is_printed_for_a_setup_command_that_is_not_needed(capsys):
    """
    An empty value would read as a command to run, so the line is absent rather than
    blank.
    """
    print_configuration(make_configuration())

    assert StackSetting.UPSTREAM_SETUP_COMMAND not in capsys.readouterr().out


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


def a_promotion_link(
    title: str = StackSampleText.TITLE, body: str = StackSampleText.BODY
) -> PromotionLink:
    """
    The compare-and-create link for that stack's root branch.

    :param title: The title to prefill.
    :param body: The body to prefill.
    :return: The built link.
    """
    return PromotionLink.build(make_configuration(), StackBranch.ENGINE, title, body)


def prefilled(link: PromotionLink, parameter: PromotionLinkParameter) -> str:
    """
    :param link: The link to read.
    :param parameter: The prefill to read out of it.
    :return: That prefill, decoded.
    """
    return parse_qs(urlsplit(link.url).query)[parameter][0]


def test_the_link_compares_the_upstream_base_against_the_fork_branch():
    assert a_promotion_link().url.startswith(
        f"{StackRepository.UPSTREAM.value.url}/compare/{StackBranch.BASE}..."
        f"{StackRepository.FORK.value.owner}:{StackBranch.ENGINE}"
        f"?{PromotionLinkParameter.EXPAND}=1"
    )


def test_the_title_and_body_are_encoded_rather_than_pasted_in_raw():
    """
    An unencoded ``&`` or ``#`` truncates the query string at that character, so the
    prefill silently loses everything after it.
    """
    link = a_promotion_link(
        title=StackSampleText.TITLE_WITH_SEPARATORS,
        body=StackSampleText.BODY_WITH_FRAGMENT,
    )

    assert prefilled(link, PromotionLinkParameter.TITLE) == (
        StackSampleText.TITLE_WITH_SEPARATORS
    )
    assert prefilled(link, PromotionLinkParameter.BODY) == (
        StackSampleText.BODY_WITH_FRAGMENT
    )


def test_a_body_within_the_limit_is_left_whole():
    link = a_promotion_link(body=StackSampleText.SHORT_BODY)

    assert not link.body_was_truncated
    assert prefilled(link, PromotionLinkParameter.BODY) == StackSampleText.SHORT_BODY


def test_an_oversized_body_is_truncated_rather_than_silently_dropped():
    """
    Over the limit the whole prefill is discarded by the server, so the link arrives
    with an empty description and nobody is told.
    """
    link = a_promotion_link(
        body=StackSampleText.FILLER * (PromotionLink.url_character_limit + 1)
    )

    assert link.body_was_truncated
    assert link.url.endswith(PromotionLink.truncation_marker)
    assert len(link.url) <= PromotionLink.url_character_limit


def test_a_link_that_cannot_fit_even_without_a_description_is_refused():
    """
    Returning a link known to be over the limit would be the silent failure this class
    exists to prevent, so the one input that cannot be fixed by shortening the body says
    so.
    """
    with pytest.raises(PromotionLinkTooLongError):
        a_promotion_link(
            title=StackSampleText.FILLER * (PromotionLink.url_character_limit + 1),
            body="",
        )


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
    scratch_repository.add_remote(
        RemoteName.THEIRS, StackRepository.SOMEBODY_ELSES_FORK.value.clone_url
    )
    scratch_repository.resolve_notes_remote_to()
    monkeypatch.chdir(scratch_repository.project_root)

    with pytest.raises(AmbiguousForkRemoteError):
        load_configuration(configuration_path)

    configuration = load_configuration(
        configuration_path, fork_repository=StackRepository.SOMEBODY_ELSES_FORK.value
    )

    assert configuration.fork_repository == StackRepository.SOMEBODY_ELSES_FORK.value
    assert configuration.fork_remote == RemoteName.THEIRS


def test_a_project_committing_no_stack_file_takes_its_upstream_from_personal_notes(
    scratch_repository: ScratchRepository, monkeypatch
):
    """
    A project that commits nothing of basstler's still has an upstream: the user's own
    personal-notes layer names it.
    """
    configuration_path = scratch_repository.install_stack_configuration(
        PackageLocation.STACK_CONFIGURATION.value.read_text()
    )
    scratch_repository.add_remote(
        RemoteName.UNEXPECTED, StackRepository.FORK.value.clone_url
    )
    scratch_repository.publish_notes_branch(
        {
            ProjectLocation.PERSONAL_STACK_CONFIGURATION: a_setting_line(
                StackSetting.UPSTREAM_REPOSITORY,
                StackRepository.DIFFERENT_UPSTREAM.value.full_name,
            )
        }
    )
    scratch_repository.resolve_notes_remote_to()
    monkeypatch.chdir(scratch_repository.project_root)

    configuration = load_configuration(configuration_path)

    assert configuration.upstream_repository == StackRepository.DIFFERENT_UPSTREAM.value


def test_a_named_upstream_replaces_the_committed_default(
    scratch_repository: ScratchRepository, monkeypatch
):
    configuration_path = _committed_configuration_path(scratch_repository)
    scratch_repository.resolve_notes_remote_to()
    monkeypatch.chdir(scratch_repository.project_root)

    configuration = load_configuration(
        configuration_path,
        upstream_repository=StackRepository.DIFFERENT_UPSTREAM.value,
    )

    assert configuration.upstream_repository == StackRepository.DIFFERENT_UPSTREAM.value
    assert configuration.upstream_setup_command == a_remote_addition_command(
        RemoteName.UPSTREAM, StackRepository.DIFFERENT_UPSTREAM.value
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
        project_root=checkout.project_root, module_name=basstler.stack.__name__
    ).run(*arguments)


def test_an_unknown_command_is_a_usage_error(offline_checkout: ScratchRepository):
    assert (
        run_stack(offline_checkout, StackSampleText.UNKNOWN_COMMAND).returncode
        == StackExitCode.USAGE
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
        CommandOption.CURRENT,
        StackLabel.IN_REVIEW,
        CommandOption.CURRENT,
        StackLabel.BUG,
        CommandOption.ADD,
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
        CommandOption.ADD,
        StackLabel.REBASE,
        CommandOption.REMOVE,
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
    offline_checkout.add_remote(RemoteName.MINE, StackRepository.FORK.value.clone_url)

    result = run_stack(offline_checkout, Command.CONFIGURATION)

    assert result.returncode == StackExitCode.UPSTREAM_UNCONFIGURED
    assert str(ProjectLocation.PROJECT_STACK_CONFIGURATION) in result.stderr
    assert str(ProjectLocation.PERSONAL_STACK_CONFIGURATION) in result.stderr


def test_a_readable_checkout_with_no_board_reports_the_missing_board_instead(
    offline_checkout: ScratchRepository,
):
    offline_checkout.add_remote(RemoteName.MINE, StackRepository.FORK.value.clone_url)

    result = run_stack(offline_checkout, Command.STATUS)

    assert result.returncode == StackExitCode.BOARD_UNAVAILABLE


def test_a_named_fork_and_upstream_are_used_where_inference_would_have_refused(
    offline_checkout: ScratchRepository,
):
    """
    Two candidate remotes are ambiguous, so a caller that already knows the answer must
    be able to say so rather than be blocked by the guess it does not need.
    """
    offline_checkout.add_remote(RemoteName.MINE, StackRepository.FORK.value.clone_url)
    offline_checkout.add_remote(
        RemoteName.THEIRS, StackRepository.SOMEBODY_ELSES_FORK.value.clone_url
    )

    assert (
        run_stack(offline_checkout, Command.CONFIGURATION).returncode
        == StackExitCode.REMOTES_UNRESOLVED
    )

    result = run_stack(
        offline_checkout,
        Command.CONFIGURATION,
        CommandOption.FORK,
        StackRepository.FORK.value.full_name,
        CommandOption.UPSTREAM,
        StackRepository.UPSTREAM.value.full_name,
    )

    assert result.returncode == StackExitCode.SUCCESS
    printed = PrintedConfiguration.read(result.stdout)
    assert printed[StackSetting.FORK_REPOSITORY] == StackRepository.FORK.value.full_name
    assert printed[StackSetting.FORK_REMOTE] == RemoteName.MINE
    assert (
        printed[StackSetting.UPSTREAM_REPOSITORY]
        == StackRepository.UPSTREAM.value.full_name
    )


def test_a_fork_that_is_not_owner_and_name_is_a_usage_error(
    offline_checkout: ScratchRepository,
):
    result = run_stack(
        offline_checkout,
        Command.CONFIGURATION,
        CommandOption.FORK,
        StackSampleText.NOT_A_REPOSITORY,
    )

    assert result.returncode == StackExitCode.USAGE


def test_a_promotion_link_is_built_from_the_resolved_repositories(
    offline_checkout: ScratchRepository,
):
    offline_checkout.add_remote(RemoteName.MINE, StackRepository.FORK.value.clone_url)

    result = run_stack(
        offline_checkout,
        Command.PROMOTION_LINK,
        CommandOption.BRANCH,
        StackBranch.ENGINE,
        CommandOption.TITLE,
        StackSampleText.TITLE,
    )

    assert result.returncode == StackExitCode.SUCCESS
    assert result.stdout.strip() == (
        PromotionLink.build(
            make_configuration(),
            StackBranch.ENGINE,
            StackSampleText.TITLE,
            "",
        ).url
    )
