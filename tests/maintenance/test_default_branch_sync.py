"""
Catching the fork's default branch up with the upstream at session start.

Run against a scratch clone whose fork and upstream are local bare repositories named the
way GitHub names them, so the stacked-PR configuration resolves them exactly as it resolves
the real ones - no network access involved.
"""

from __future__ import annotations

import pytest

from basstler.maintenance.default_branch_sync import (
    BaseOutcome,
    DefaultBranchReport,
    DefaultBranchSync,
)
from basstler.maintenance.fast_forward import FastForwardOutcome
from basstler.locations import PluginLocation
from basstler.shell_configuration import FetchedBranchReference

from ..constants.notes import ScratchBranch
from .forked_scratch_repository import (
    DEFAULT_BRANCH,
    FORK_REMOTE,
    SESSION_BRANCH,
    SHARED_FILE,
    UPSTREAM_REMOTE,
    ForkedScratchRepository,
)
from ..scratch_repository import ScratchRepository
from ..hooks.session_start_summary import SummaryLine, summary_value


@pytest.fixture
def forked(
    scratch_repository: ScratchRepository, monkeypatch
) -> ForkedScratchRepository:
    """
    :param scratch_repository: The initialized scratch repository and notes remote.
    :param monkeypatch: Moves the test into the clone, which the configuration resolves
        the project from.
    :return: A fork, its upstream and a clone of it, all at one commit.
    """
    monkeypatch.chdir(scratch_repository.project_root)
    return ForkedScratchRepository.laid_out_in(scratch_repository)


def sync(forked: ForkedScratchRepository) -> DefaultBranchReport:
    """
    :param forked: The clone to catch up.
    :return: What the pass reported.
    """
    return DefaultBranchSync.catch_up_checkout(forked.repository.project_root)


# %% catching up


def test_fast_forwards_a_stale_base_and_the_fork_behind_it(
    forked: ForkedScratchRepository,
):
    upstream_tip = forked.advance_upstream(3)

    report = sync(forked)

    assert report.outcome is BaseOutcome.FAST_FORWARDED
    assert report.commits_behind == 3
    assert forked.local_default_branch_tip() == upstream_tip
    assert report.fork_fast_forward is FastForwardOutcome.PUSHED
    assert forked.fork_default_branch_tip() == upstream_tip


def test_never_moves_the_checked_out_branch_but_says_how_far_behind_it_is(
    forked: ForkedScratchRepository,
):
    work_tip = forked.commit_at("HEAD")
    forked.advance_upstream(2)

    report = sync(forked)

    assert forked.commit_at("HEAD") == work_tip
    assert report.checked_out_branch_behind == 2
    assert str(report.checked_out_branch_behind) in report.render().splitlines()[-1]


def test_fast_forwards_a_session_branch_with_no_commits_of_its_own(
    forked: ForkedScratchRepository,
):
    upstream_tip = forked.advance_upstream(2)
    forked.start_a_session_branch()

    report = sync(forked)

    assert forked.commit_at(f"refs/heads/{SESSION_BRANCH}") == upstream_tip
    assert report.checked_out_branch == SESSION_BRANCH
    assert report.checked_out_branch_fast_forwarded == 2
    assert report.checked_out_branch_behind == 0


def test_leaves_a_session_branch_alone_when_its_uncommitted_changes_are_in_the_way(
    forked: ForkedScratchRepository,
):
    forked.advance_upstream(1)
    forked.start_a_session_branch()
    starting_point = forked.commit_at("HEAD")
    forked.repository.write(SHARED_FILE, "an uncommitted edit\n")

    report = sync(forked)

    assert forked.commit_at("HEAD") == starting_point
    assert report.checked_out_branch_fast_forwarded == 0
    assert report.checked_out_branch_behind == 1


def test_reports_a_base_that_already_matches(forked: ForkedScratchRepository):
    report = sync(forked)

    assert report.outcome is BaseOutcome.CURRENT
    assert report.fork_fast_forward is FastForwardOutcome.ALREADY_CURRENT
    assert report.follow_up_rows == ()


def test_catches_the_fork_up_even_when_this_clone_already_is(
    forked: ForkedScratchRepository,
):
    """
    An earlier session moved its clone but its push was refused: every later clone of
    the fork still starts stale unless the fork is judged on its own evidence.
    """
    upstream_tip = forked.advance_upstream(1)
    forked.set_local_default_branch_to(upstream_tip)

    report = sync(forked)

    assert report.outcome is BaseOutcome.CURRENT
    assert report.fork_fast_forward is FastForwardOutcome.PUSHED
    assert forked.fork_default_branch_tip() == upstream_tip


def test_creates_the_base_in_a_clone_that_has_none(forked: ForkedScratchRepository):
    upstream_tip = forked.advance_upstream(1)
    forked.delete_local_default_branch()

    report = sync(forked)

    assert report.outcome is BaseOutcome.CURRENT
    assert forked.local_default_branch_tip() == upstream_tip


def test_fast_forwards_a_base_that_is_checked_out(forked: ForkedScratchRepository):
    upstream_tip = forked.advance_upstream(1)
    forked.check_out_default_branch()

    report = sync(forked)

    assert report.outcome is BaseOutcome.FAST_FORWARDED
    assert forked.commit_at("HEAD") == upstream_tip


def test_reaches_the_upstream_through_its_remote_when_the_clone_has_one(
    forked: ForkedScratchRepository,
):
    upstream_tip = forked.advance_upstream(1)
    forked.reach_the_upstream_only_through_its_remote()

    report = sync(forked)

    assert report.outcome is BaseOutcome.FAST_FORWARDED
    assert forked.commit_at(f"{UPSTREAM_REMOTE}/{DEFAULT_BRANCH}") == upstream_tip


def test_leaves_the_personal_notes_reference_where_the_notes_fetch_put_it(
    forked: ForkedScratchRepository,
):
    """
    session-start.sh reads the personal-notes branch through
    :attr:`FetchedBranchReference.PERSONAL_NOTES`, so a fetch of the upstream must not
    take it over.
    """
    forked.advance_upstream(1)

    report = sync(forked)

    assert report.outcome is BaseOutcome.FAST_FORWARDED
    assert forked.commit_at(FetchedBranchReference.PERSONAL_NOTES) == forked.commit_at(
        f"refs/heads/{ScratchBranch.PERSONAL_NOTES}"
    )


# %% refusing, never forcing


def test_leaves_a_base_with_commits_of_its_own_alone(forked: ForkedScratchRepository):
    fork_tip = forked.fork_default_branch_tip()
    forked.advance_upstream(1)
    local_tip = forked.advance_local_default_branch()

    report = sync(forked)

    assert report.outcome is BaseOutcome.DIVERGED
    assert forked.local_default_branch_tip() == local_tip
    assert forked.fork_default_branch_tip() == fork_tip


def test_leaves_a_checked_out_base_with_uncommitted_changes_alone(
    forked: ForkedScratchRepository,
):
    forked.advance_upstream(1)
    starting_point = forked.local_default_branch_tip()
    forked.check_out_default_branch()
    forked.repository.write(SHARED_FILE, "an uncommitted edit\n")

    report = sync(forked)

    assert report.outcome is BaseOutcome.LOCAL_UPDATE_REFUSED
    assert forked.local_default_branch_tip() == starting_point


def test_reports_a_refused_push_to_the_fork(forked: ForkedScratchRepository):
    fork_tip = forked.fork_default_branch_tip()
    upstream_tip = forked.advance_upstream(1)
    forked.refuse_pushes_to_the_fork()

    report = sync(forked)

    assert report.outcome is BaseOutcome.FAST_FORWARDED
    assert forked.local_default_branch_tip() == upstream_tip
    assert report.fork_fast_forward is FastForwardOutcome.PUSH_REFUSED
    assert forked.fork_default_branch_tip() == fork_tip


def test_leaves_a_fork_with_commits_of_its_own_alone(
    forked: ForkedScratchRepository,
):
    starting_point = forked.local_default_branch_tip()
    fork_tip = forked.advance_local_default_branch()
    forked.publish_default_branch_to(FORK_REMOTE)
    forked.set_local_default_branch_to(starting_point)
    upstream_tip = forked.advance_upstream(1)

    report = sync(forked)

    assert forked.local_default_branch_tip() == upstream_tip
    assert report.fork_fast_forward is FastForwardOutcome.REFUSED_NOT_FAST_FORWARD
    assert forked.fork_default_branch_tip() == fork_tip


def test_reports_an_unreachable_upstream(forked: ForkedScratchRepository):
    starting_point = forked.local_default_branch_tip()
    forked.make_the_upstream_unreachable()

    report = sync(forked)

    assert report.outcome is BaseOutcome.UPSTREAM_UNREACHABLE
    assert forked.local_default_branch_tip() == starting_point


def test_follows_its_own_remote_when_no_upstream_is_named(
    forked: ForkedScratchRepository,
):
    """
    A project that is not a fork still goes stale against the repository it was cloned
    from, and its own remote is all there is to catch up with.
    """
    fork_tip = forked.advance_fork(2)
    forked.start_a_session_branch()
    forked.forget_the_stack_configuration()

    report = sync(forked)

    assert report.outcome is BaseOutcome.FAST_FORWARDED
    assert report.upstream == forked.fork.repository.full_name
    assert report.fork_fast_forward is None
    assert forked.local_default_branch_tip() == fork_tip
    assert forked.commit_at("HEAD") == fork_tip


def test_reports_a_clone_with_nothing_to_catch_up_with(
    forked: ForkedScratchRepository,
):
    forked.forget_the_stack_configuration()
    forked.forget_the_fork_remote()

    report = sync(forked)

    assert report.outcome is BaseOutcome.NOT_SYNCED
    assert report.reason in report.render()
    assert report.reason != ""


# %% the session-start line


def test_session_start_reports_the_catching_up_and_still_starts(
    forked: ForkedScratchRepository,
):
    repository = forked.repository
    repository.install_hook_scripts(
        PluginLocation.PERSONAL_NOTES_CONFIGURATION_SCRIPT.name,
        PluginLocation.SESSION_START_MESSAGES_SCRIPT.name,
        PluginLocation.SESSION_START_SCRIPT.name,
    )
    repository.install_package()
    repository.install_package_environment()
    upstream_tip = forked.advance_upstream(2)

    result = repository.run_hook_script(PluginLocation.SESSION_START_SCRIPT.name)

    assert result.returncode == 0, result.stderr
    assert forked.local_default_branch_tip() == upstream_tip
    line = summary_value(result.stdout, SummaryLine.DEFAULT_BRANCH)
    assert (
        line
        == DefaultBranchReport(
            BaseOutcome.FAST_FORWARDED,
            base_branch=DEFAULT_BRANCH,
            upstream=forked.upstream.repository.full_name,
            commits_behind=2,
        ).outcome_line
    )
    assert summary_value(result.stdout, SummaryLine.PLAN_STATE_SHA).startswith(
        forked.commit_at(f"refs/heads/{ScratchBranch.PERSONAL_NOTES}")
    )
