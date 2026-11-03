"""
Tests for the stack helper's merge probe, which decides from git alone whether one
branch merges into another.
"""

from __future__ import annotations

import json
import subprocess

import basstler.stack.__main__
from basstler.exit_codes import StackExitCode
from basstler.stack.__main__ import Command, CommandOption
from basstler.stack.report import MergeVerdict

from ..constants.stack import RemoteName, StackBranch
from ..maintenance.fork import ForkCheckout
from ..script_runner import PythonModuleRunner

# %% running the probe


def probe(
    checkout: ForkCheckout, base: str, head: str
) -> subprocess.CompletedProcess[str]:
    """
    Run the merge probe as a caller does.

    :param checkout: The checkout to run in.
    :param base: The branch merged into.
    :param head: The branch merged.
    :return: The finished subprocess.
    """
    return PythonModuleRunner(
        project_root=checkout.project_root,
        module_name=basstler.stack.__main__.__name__,
    ).run(
        Command.MERGE_PROBE,
        CommandOption.REMOTE,
        RemoteName.ORIGIN,
        CommandOption.BASE,
        base,
        CommandOption.HEAD,
        head,
    )


def conflicting_feature(checkout: ForkCheckout) -> str:
    """
    Publish a feature branch and a base that both rewrite the same file differently.

    :param checkout: The checkout to build them in.
    :return: The file both sides changed.
    """
    shared_file = checkout.own_file(StackBranch.BASE)
    checkout.commit_on(StackBranch.BASE, shared_file, "the base's line\n")
    checkout.branch_from(StackBranch.FEATURE, f"{StackBranch.BASE}~1")
    checkout.commit_on(StackBranch.FEATURE, shared_file, "the feature's line\n")
    return shared_file


# %% the verdict


def test_a_branch_that_merges_cleanly_is_clean(fork_checkout: ForkCheckout):
    checkout = fork_checkout
    checkout.branch_from(StackBranch.FEATURE, StackBranch.BASE)

    result = probe(checkout, StackBranch.BASE, StackBranch.FEATURE)

    report = json.loads(result.stdout)
    assert result.returncode == StackExitCode.SUCCESS
    assert report["verdict"] == MergeVerdict.CLEAN
    assert report["conflicting_paths"] == []


def test_a_conflicting_branch_names_every_conflicting_path(
    fork_checkout: ForkCheckout,
):
    shared_file = conflicting_feature(fork_checkout)

    result = probe(fork_checkout, StackBranch.BASE, StackBranch.FEATURE)

    report = json.loads(result.stdout)
    assert result.returncode == StackExitCode.MERGE_CONFLICTS
    assert report["verdict"] == MergeVerdict.CONFLICTS
    assert report["conflicting_paths"] == [shared_file]


def test_the_probe_reports_the_commits_it_merged(fork_checkout: ForkCheckout):
    conflicting_feature(fork_checkout)

    report = json.loads(
        probe(fork_checkout, StackBranch.BASE, StackBranch.FEATURE).stdout
    )

    assert report["base_commit"] == fork_checkout.commit_on_the_fork(StackBranch.BASE)
    assert report["head_commit"] == fork_checkout.commit_on_the_fork(
        StackBranch.FEATURE
    )


def test_the_probe_reads_the_remote_rather_than_a_stale_local_copy(
    fork_checkout: ForkCheckout,
):
    fork_checkout.branch_from(StackBranch.FEATURE, StackBranch.BASE)
    probe(fork_checkout, StackBranch.BASE, StackBranch.FEATURE)
    shared_file = fork_checkout.own_file(StackBranch.BASE)
    fork_checkout.commit_on(StackBranch.FEATURE, shared_file, "the feature's line\n")
    fork_checkout.commit_on(StackBranch.BASE, shared_file, "the base's line\n")

    result = probe(fork_checkout, StackBranch.BASE, StackBranch.FEATURE)

    assert result.returncode == StackExitCode.MERGE_CONFLICTS


def test_two_probes_of_the_same_state_report_the_same(fork_checkout: ForkCheckout):
    conflicting_feature(fork_checkout)

    first = probe(fork_checkout, StackBranch.BASE, StackBranch.FEATURE)
    second = probe(fork_checkout, StackBranch.BASE, StackBranch.FEATURE)

    assert first.stdout == second.stdout


def test_a_branch_the_remote_does_not_have_is_a_failed_git_command(
    fork_checkout: ForkCheckout,
):
    result = probe(fork_checkout, StackBranch.BASE, StackBranch.LANDED)

    assert result.returncode == StackExitCode.GIT_COMMAND_FAILED
    assert result.stdout == ""
