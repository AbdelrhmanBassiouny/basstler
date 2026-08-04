"""
Tests for the maintenance executor - the half of the pass that moves commits.

``stack.py`` derives and prints; every assertion about it can be made against an
in-memory export. This module executes, so most of its behaviour is only true of a real
repository: whether a push happened, whether a refused push left the destination
untouched, which paths a merge conflicted on. Those run against real git in a scratch
fork built here, with bare repositories standing in for the fork and the upstream, so
nothing touches the network.

The board export and the report are pure, and are tested as such.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from scratch_repository import initialize_bare_repository

from stack import (
    BOARD_PATH,
    Configuration,
    IntegrationStrategy,
    PullRequest,
    RefusalReason,
    Repository,
    build_stack,
    load_board,
)

from maintenance import (
    BoardExport,
    Command,
    FastForwardOutcome,
    GitCommandFailed,
    GitCommandRunner,
    MaintenanceExitCode,
    MissingPullRequestFieldError,
    PullRequestField,
    RestackOutcome,
    build_report,
    fast_forward,
    push_arguments,
    restack,
    session_link_in,
)

MAINTENANCE_SCRIPT = Path(__file__).parent.parent / "maintenance.py"
"""
The executor under test, invoked as a subprocess wherever an exit status is the
assertion.
"""

UPSTREAM_BASE = "main"
"""
The branch every stack in these tests ultimately targets.
"""


def make_configuration() -> Configuration:
    """
    :return: The configuration a scratch fork checkout resolves to.
    """
    return Configuration(
        in_review_label="in-review",
        rebase_label="rebase",
        needs_resolution_label="needs-resolution",
        fork_repository=Repository("a-fork-owner", "a-fork"),
        fork_remote="origin",
        upstream_repository=Repository("an-upstream-owner", "a-project"),
        upstream_remote="cram2",
        upstream_base=UPSTREAM_BASE,
        upstream_setup_command=None,
    )


# %% a real fork checkout to execute against


@dataclass
class ForkCheckout:
    """
    A work clone plus the bare repositories standing in for its fork and its upstream.

    Bare repositories live at paths ending ``<owner>/<name>.git`` and are addressed as
    ``file://`` URLs, because a remote is matched by the repository its URL names and a
    plain local path deliberately names none.
    """

    project_root: Path
    """
    The clone the executor runs in.
    """

    fork_path: Path
    """
    The bare repository the fork remote points at.
    """

    upstream_path: Path
    """
    The bare repository the upstream remote points at.
    """

    @classmethod
    def create(cls, parent_directory: Path) -> ForkCheckout:
        """
        Build a checkout with both remotes wired up and ``main`` published to each.

        :param parent_directory: Where to put the clone and the bare repositories.
        :return: The new checkout.
        """
        project_root = parent_directory / "project"
        project_root.mkdir(parents=True)
        checkout = cls(
            project_root,
            cls._bare_repository(parent_directory / "a-fork-owner" / "a-fork.git"),
            cls._bare_repository(
                parent_directory / "an-upstream-owner" / "a-project.git"
            ),
        )
        checkout.run_git("init", "--quiet")
        checkout.run_git("symbolic-ref", "HEAD", f"refs/heads/{UPSTREAM_BASE}")
        checkout.run_git("config", "user.name", "Scratch Fork")
        checkout.run_git("config", "user.email", "scratch-fork@example.com")
        checkout.run_git("remote", "add", "origin", checkout.fork_path.as_uri())
        checkout.run_git("remote", "add", "cram2", checkout.upstream_path.as_uri())
        checkout.commit("a-file", "the first line\n")
        checkout.run_git("push", "--quiet", "origin", UPSTREAM_BASE)
        checkout.run_git("push", "--quiet", "cram2", UPSTREAM_BASE)
        checkout.run_git("fetch", "--quiet", "origin")
        checkout.run_git("fetch", "--quiet", "cram2")
        return checkout

    @staticmethod
    def _bare_repository(path: Path) -> Path:
        """
        :param path: Where to create the bare repository, parents included.
        :return: The same path.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        return initialize_bare_repository(path)

    def run_git(self, *arguments: str) -> str:
        """
        Run git in the clone, failing the test if it reports an error.

        :param arguments: The arguments to pass to git.
        :return: The command's stripped stdout.
        """
        result = subprocess.run(
            ["git", *arguments],
            cwd=self.project_root,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    def commit(self, name: str, content: str) -> str:
        """
        Write a file and commit it on the checked-out branch.

        :param name: The file to write.
        :param content: What to write into it.
        :return: The new commit's hash.
        """
        (self.project_root / name).write_text(content)
        self.run_git("add", name)
        self.run_git("commit", "--quiet", "-m", f"write {name}")
        return self.run_git("rev-parse", "HEAD")

    def branch_from(self, name: str, start_point: str) -> str:
        """
        Create a branch with a commit of its own, and publish it to the fork.

        The commit is what makes the branch a stack node rather than another name for
        its start point: a branch containing nothing of its own is an ancestor of the
        upstream base, which the derived stack reads - correctly - as already landed.

        :param name: The branch to create.
        :param start_point: What to start it from.
        :return: The branch's published commit hash.
        """
        self.run_git("checkout", "--quiet", "-B", name, start_point)
        commit = self.commit(f"{name}-file", f"the work on {name}\n")
        self.run_git("push", "--quiet", "origin", f"{name}:{name}")
        self.run_git("fetch", "--quiet", "origin")
        return commit

    def commit_on(self, branch: str, name: str, content: str) -> str:
        """
        Add a commit to a branch and publish it to the fork.

        :param branch: The branch to commit on.
        :param name: The file to write.
        :param content: What to write into it.
        :return: The branch's new published commit hash.
        """
        self.run_git("checkout", "--quiet", branch)
        commit = self.commit(name, content)
        self.run_git("push", "--quiet", "origin", f"{branch}:{branch}")
        self.run_git("fetch", "--quiet", "origin")
        return commit

    def published_commit(self, remote: str, branch: str) -> str:
        """
        :param remote: The remote to read from.
        :param branch: The branch to read.
        :return: The commit that branch points at on that remote.
        """
        return self.run_git("rev-parse", f"{remote}/{branch}")

    def commit_on_the_fork(self, branch: str) -> str:
        """
        Read a branch from the fork itself rather than from this clone's view of it.

        :param branch: The branch to read.
        :return: The commit the fork has that branch pointing at.
        """
        return self.run_git("ls-remote", "origin", f"refs/heads/{branch}").split()[0]

    @property
    def git(self) -> GitCommandRunner:
        """
        :return: The runner the executor drives this checkout through.
        """
        return GitCommandRunner(working_directory=self.project_root)


@pytest.fixture
def fork_checkout(tmp_path: Path) -> ForkCheckout:
    """
    A real fork checkout with both remotes wired to local bare repositories.

    :param tmp_path: pytest's per-test temporary directory.
    :return: The checkout.
    """
    return ForkCheckout.create(tmp_path)


def a_stack(checkout: ForkCheckout, pull_requests: list[PullRequest]):
    """
    Build the derived stack the executor consumes, with landedness read from real git.

    :param checkout: The checkout to answer ancestry questions from.
    :param pull_requests: The board entries.
    :return: The derived stack.
    """
    configuration = make_configuration()
    upstream = f"{configuration.upstream_remote}/{configuration.upstream_base}"

    def is_merged(name: str) -> bool:
        return checkout.git.succeeds(
            "merge-base",
            "--is-ancestor",
            f"{configuration.fork_remote}/{name}",
            upstream,
        )

    return build_stack(configuration, pull_requests, is_merged)


# %% running git


def test_a_failing_git_command_raises_rather_than_returning_nothing(
    fork_checkout: ForkCheckout,
):
    """
    ``stack.py``'s helper returns an empty string on failure, which here would make a
    push that did nothing indistinguishable from one that worked.
    """
    with pytest.raises(GitCommandFailed) as raised:
        fork_checkout.git.run("rev-parse", "a-ref-that-does-not-exist")

    assert raised.value.arguments == ("rev-parse", "a-ref-that-does-not-exist")
    assert raised.value.exit_status != 0


# %% the board export


def an_api_record(
    number: int = 7,
    head: str = "a-branch",
    base: str = UPSTREAM_BASE,
    draft: bool = False,
    labels: list[str] | None = None,
    body: str = "",
) -> dict:
    """
    :param number: The pull request number.
    :param head: The head branch reference.
    :param base: The base branch reference.
    :param draft: Whether the pull request is a draft.
    :param labels: The label names it carries.
    :param body: The description to read a session link out of.
    :return: One pull request in the shape the REST API returns it.
    """
    return {
        "number": number,
        "head": {"ref": head},
        "base": {"ref": base},
        "draft": draft,
        "labels": [{"name": name} for name in labels or []],
        "body": body,
    }


def test_the_written_board_parses_back_into_the_records_it_was_built_from(
    tmp_path: Path,
):
    """
    The export's only contract is that ``stack.load_board`` reads it, so the expected
    value is derived by reading it rather than by hand-writing the shape twice.
    """
    export = BoardExport.from_api_records(
        [
            an_api_record(number=41, head="a-child", base="a-parent", draft=True),
            an_api_record(number=40, head="a-parent", labels=["in-review"]),
        ]
    )
    destination = tmp_path / "board.json"

    export.write(destination)

    assert load_board(destination) == list(export.pull_requests)


def test_a_pull_request_missing_a_required_field_is_rejected_rather_than_defaulted():
    """
    A dropped field is what made #119's bad data indistinguishable from good data, so
    the parser refuses it at the point it enters rather than substituting a default.
    """
    record = an_api_record(number=41)
    del record["draft"]

    with pytest.raises(MissingPullRequestFieldError) as raised:
        BoardExport.from_api_records([record])

    assert raised.value.field_name == PullRequestField.DRAFT
    assert raised.value.pull_request_number == 41


def test_the_board_snapshot_is_never_committable():
    """
    ``board --write`` writes into the working tree, so nothing but ``.gitignore`` stands
    between a pass and a committed snapshot of a stack that has since moved.
    """
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", str(BOARD_PATH)],
        cwd=BOARD_PATH.parent,
        capture_output=True,
    )

    assert ignored.returncode == 0


def test_a_session_link_is_read_out_of_the_description():
    body = "Some prose.\n\nSession: https://claude.ai/code/session_01ABCdef\n"

    assert session_link_in(body) == "https://claude.ai/code/session_01ABCdef"


def test_a_description_naming_no_session_yields_none():
    assert session_link_in("Some prose with no link.") is None


# %% fast-forward


def test_the_fork_base_is_fast_forwarded_to_the_upstream(fork_checkout: ForkCheckout):
    fork_checkout.run_git("checkout", "--quiet", UPSTREAM_BASE)
    advanced = fork_checkout.commit("another-file", "upstream moved\n")
    fork_checkout.run_git("push", "--quiet", "cram2", UPSTREAM_BASE)
    fork_checkout.run_git(
        "push", "--quiet", "--force", "origin", f"HEAD~1:{UPSTREAM_BASE}"
    )
    fork_checkout.run_git("fetch", "--quiet", "origin")

    report = fast_forward(make_configuration(), fork_checkout.git)

    assert report.outcome == FastForwardOutcome.PUSHED
    assert fork_checkout.published_commit("origin", UPSTREAM_BASE) == advanced


def test_a_fork_base_already_level_with_the_upstream_is_left_alone(
    fork_checkout: ForkCheckout,
):
    report = fast_forward(make_configuration(), fork_checkout.git)

    assert report.outcome == FastForwardOutcome.ALREADY_CURRENT


def test_a_non_fast_forward_is_refused_and_the_fork_base_is_untouched(
    fork_checkout: ForkCheckout,
):
    """
    The doctrine says stop rather than force; this makes it unable to force, and the
    assertion is on the destination ref rather than on the command having failed.
    """
    fork_checkout.run_git("checkout", "--quiet", UPSTREAM_BASE)
    fork_checkout.commit("a-fork-only-file", "only on the fork\n")
    fork_checkout.run_git("push", "--quiet", "origin", UPSTREAM_BASE)
    fork_checkout.run_git("checkout", "--quiet", "-B", "a-divergent-line", "HEAD~1")
    fork_checkout.commit("an-upstream-only-file", "only upstream\n")
    fork_checkout.run_git(
        "push", "--quiet", "--force", "cram2", f"HEAD:{UPSTREAM_BASE}"
    )
    fork_checkout.run_git("fetch", "--quiet", "origin")
    fork_checkout.run_git("fetch", "--quiet", "cram2")
    before = fork_checkout.published_commit("origin", UPSTREAM_BASE)

    report = fast_forward(make_configuration(), fork_checkout.git)

    assert report.outcome == FastForwardOutcome.REFUSED_NOT_FAST_FORWARD
    assert fork_checkout.published_commit("origin", UPSTREAM_BASE) == before


# %% restack


def a_parent_and_child(fork_checkout: ForkCheckout) -> None:
    """
    Publish a two-branch stack: ``a-parent`` on the base, ``a-child`` on the parent.

    :param fork_checkout: The checkout to build the branches in.
    """
    fork_checkout.branch_from("a-parent", UPSTREAM_BASE)
    fork_checkout.branch_from("a-child", "a-parent")


def the_board(labels: list[str] | None = None) -> list[PullRequest]:
    """
    :param labels: The labels the child's pull request carries.
    :return: The two-branch board matching :func:`a_parent_and_child`.
    """
    return [
        PullRequest(number=40, head="a-parent", base=UPSTREAM_BASE, draft=False),
        PullRequest(
            number=41, head="a-child", base="a-parent", draft=False, labels=labels or []
        ),
    ]


def test_a_branch_whose_parent_has_not_moved_is_reported_up_to_date(
    fork_checkout: ForkCheckout,
):
    a_parent_and_child(fork_checkout)

    outcomes = restack(a_stack(fork_checkout, the_board()), fork_checkout.git)

    assert [outcome.outcome for outcome in outcomes] == [
        RestackOutcome.UP_TO_DATE,
        RestackOutcome.UP_TO_DATE,
    ]


def test_a_branch_whose_parent_moved_is_integrated_and_pushed(
    fork_checkout: ForkCheckout,
):
    a_parent_and_child(fork_checkout)
    fork_checkout.commit_on("a-parent", "a-parent-file", "the parent moved\n")
    before = fork_checkout.published_commit("origin", "a-child")

    outcomes = restack(a_stack(fork_checkout, the_board()), fork_checkout.git)

    child = next(outcome for outcome in outcomes if outcome.branch == "a-child")
    assert child.outcome == RestackOutcome.PUSHED
    after = fork_checkout.published_commit("origin", "a-child")
    assert after != before
    assert child.pushed_commit == after


def test_a_conflicting_integration_pushes_nothing_and_names_the_files(
    fork_checkout: ForkCheckout,
):
    a_parent_and_child(fork_checkout)
    fork_checkout.commit_on("a-parent", "a-contested-file", "the parent's version\n")
    fork_checkout.commit_on("a-child", "a-contested-file", "the child's version\n")
    before = fork_checkout.published_commit("origin", "a-child")

    outcomes = restack(a_stack(fork_checkout, the_board()), fork_checkout.git)

    child = next(outcome for outcome in outcomes if outcome.branch == "a-child")
    assert child.outcome == RestackOutcome.CONFLICT
    assert child.conflicting_paths == ("a-contested-file",)
    assert fork_checkout.published_commit("origin", "a-child") == before


def test_a_rebase_labelled_branch_is_rebased_rather_than_merged(
    fork_checkout: ForkCheckout,
):
    """
    The strategy is the only thing that authorises a force-push, so it has to come from
    the label rather than from the executor's own judgement.
    """
    a_parent_and_child(fork_checkout)
    fork_checkout.commit_on("a-parent", "a-parent-file", "the parent moved\n")

    outcomes = restack(
        a_stack(fork_checkout, the_board(labels=["rebase"])), fork_checkout.git
    )

    child = next(outcome for outcome in outcomes if outcome.branch == "a-child")
    assert child.strategy == IntegrationStrategy.REBASE
    assert child.outcome == RestackOutcome.PUSHED
    merges = fork_checkout.run_git(
        "rev-list", "--merges", "--count", f"origin/{UPSTREAM_BASE}..origin/a-child"
    )
    assert merges == "0"


def test_only_the_rebase_strategy_authorises_rewriting_published_history():
    """
    Forcing is decided in exactly one place, so that is where it is pinned - a test that
    a push happened cannot tell a fast-forward from an overwrite.
    """
    configuration = make_configuration()

    merging = push_arguments(configuration, "a-branch", IntegrationStrategy.MERGE)
    rebasing = push_arguments(configuration, "a-branch", IntegrationStrategy.REBASE)

    assert not [argument for argument in merging if argument.startswith("--force")]
    assert "--force-with-lease" in rebasing


def test_a_branch_that_moved_under_the_pass_is_incorporated_rather_than_overwritten(
    fork_checkout: ForkCheckout,
):
    """
    The integration starts from the branch's published tip, not from whatever this
    checkout last saw, so work pushed by somebody else survives the restack.
    """
    a_parent_and_child(fork_checkout)
    fork_checkout.commit_on("a-parent", "a-parent-file", "the parent moved\n")
    fork_checkout.run_git("checkout", "--quiet", "-B", "a-side-line", "origin/a-child")
    somebody_else_s = fork_checkout.commit("a-file-somebody-else-pushed", "not ours\n")
    fork_checkout.run_git("push", "--quiet", "origin", "a-side-line:a-child")
    fork_checkout.run_git("fetch", "--quiet", "origin")

    outcomes = restack(a_stack(fork_checkout, the_board()), fork_checkout.git)

    child = next(outcome for outcome in outcomes if outcome.branch == "a-child")
    assert child.outcome == RestackOutcome.PUSHED
    assert fork_checkout.git.succeeds(
        "merge-base", "--is-ancestor", somebody_else_s, "origin/a-child"
    )


def test_a_rebase_whose_lease_has_expired_is_rejected_rather_than_forced_through(
    fork_checkout: ForkCheckout,
):
    """
    The lease is what stops a rebase overwriting a push this pass never saw.

    Staleness is arranged by winding the remote-tracking ref back, which is the state a
    concurrent push leaves this checkout in.
    """
    a_parent_and_child(fork_checkout)
    fork_checkout.commit_on("a-parent", "a-parent-file", "the parent moved\n")
    stale = fork_checkout.published_commit("origin", "a-child")
    somebody_else_s = fork_checkout.commit_on(
        "a-child", "a-file-somebody-else-pushed", "not ours\n"
    )
    fork_checkout.run_git("update-ref", "refs/remotes/origin/a-child", stale)

    outcomes = restack(
        a_stack(fork_checkout, the_board(labels=["rebase"])), fork_checkout.git
    )

    child = next(outcome for outcome in outcomes if outcome.branch == "a-child")
    assert child.outcome == RestackOutcome.PUSH_REJECTED
    assert fork_checkout.commit_on_the_fork("a-child") == somebody_else_s


def test_a_push_the_preflight_refuses_is_not_made(fork_checkout: ForkCheckout):
    """
    A parent that has swallowed its own child would, once pushed, make the child an
    ancestor of its own base - which GitHub reads as the child having merged and closes
    its pull request. The refusal is asserted as its reason rather than as the sentence
    explaining it.
    """
    a_parent_and_child(fork_checkout)
    fork_checkout.run_git("checkout", "--quiet", "a-parent")
    fork_checkout.run_git("merge", "--quiet", "--no-edit", "a-child")
    fork_checkout.run_git("push", "--quiet", "origin", "a-parent:a-parent")
    fork_checkout.commit_on(UPSTREAM_BASE, "a-base-file", "the base moved\n")
    before = fork_checkout.published_commit("origin", "a-parent")

    outcomes = restack(a_stack(fork_checkout, the_board()), fork_checkout.git)

    parent = next(outcome for outcome in outcomes if outcome.branch == "a-parent")
    assert parent.outcome == RestackOutcome.REFUSED
    assert RefusalReason.FALSE_MERGE in parent.refusals
    assert fork_checkout.published_commit("origin", "a-parent") == before


# %% the report


def test_the_report_serialises_every_command_s_outcome(fork_checkout: ForkCheckout):
    a_parent_and_child(fork_checkout)
    fork_checkout.commit_on("a-parent", "a-parent-file", "the parent moved\n")
    stack = a_stack(fork_checkout, the_board())

    report = build_report(
        stack,
        fast_forward(make_configuration(), fork_checkout.git),
        restack(stack, fork_checkout.git),
    )
    document = json.loads(report.as_json())

    assert document["fast_forward"]["outcome"] == FastForwardOutcome.ALREADY_CURRENT
    assert {entry["branch"] for entry in document["restacked"]} == {
        "a-parent",
        "a-child",
    }
    assert document["promotable"] == ["a-parent"]
    assert document["landed"] == []
    assert document["reparents"] == []


# %% the command line a caller acts on the exit status of


def run_maintenance(
    checkout: ForkCheckout, *arguments: str
) -> subprocess.CompletedProcess[str]:
    """
    Invoke the executor as a caller does, so its exit status is exercised.

    :param checkout: The checkout to run in.
    :param arguments: The command and its flags.
    :return: The finished subprocess.
    """
    return subprocess.run(
        [sys.executable, str(MAINTENANCE_SCRIPT), *arguments],
        capture_output=True,
        text=True,
        cwd=checkout.project_root,
    )


def test_an_unknown_command_is_a_usage_error(fork_checkout: ForkCheckout):
    assert (
        run_maintenance(fork_checkout, "not-a-command").returncode
        == MaintenanceExitCode.USAGE
    )


def test_every_command_is_reachable_from_the_command_line(fork_checkout: ForkCheckout):
    """
    A command in the enum that the parser never registers is unreachable, and nothing
    else would notice.
    """
    for command in Command:
        result = run_maintenance(fork_checkout, command, "--help")
        assert result.returncode == MaintenanceExitCode.SUCCESS, result.stderr


def test_a_missing_board_is_its_own_exit_status(fork_checkout: ForkCheckout):
    """
    Distinguishable from a usage error, so a caller can export the board and retry
    rather than reporting a broken invocation.

    The upstream remote is dropped first because a subprocess reads the committed
    ``stack.toml``, whose upstream is this repository's own - against which both of the
    fixture's remotes look like candidate forks, and inference rightly refuses to guess.
    """
    fork_checkout.run_git("remote", "remove", "cram2")

    assert (
        run_maintenance(fork_checkout, Command.RESTACK).returncode
        == MaintenanceExitCode.BOARD_UNAVAILABLE
    )
