#!/usr/bin/env python3
"""
Report the review threads a fork's pull request has collected upstream.

Thread resolved-state is only exposed by GitHub's GraphQL API, which is unreachable from
a Claude session, so this runs in the fork's own GitHub Actions runner and the session
reads its job log. ``gh`` is the transport rather than a hand-rolled client: runners
ship it and ``GITHUB_TOKEN`` authenticates it, so no access rule is implemented here a
fourth time.

Every repository name comes from configuration or the runner's own environment, so the
script works unchanged in any contributor's fork.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

# ``stack.py`` is a single-file script rather than an installed package, so its
# directory joins the path the same way the test suites do it. Reusing its
# ``Repository`` keeps one parser for ``owner/name`` references.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "stack"))

import tomllib  # noqa: E402
from stack import CONFIGURATION_PATH, Repository  # noqa: E402

# %% errors


class UpstreamReviewError(Exception):
    """
    Base class for every failure this script raises.
    """


class GitHubCommandFailed(UpstreamReviewError):
    """
    Raised when ``gh`` exits non-zero or GitHub answers with errors.
    """


class UpstreamPullRequestNotFound(UpstreamReviewError):
    """
    Raised when a branch has no pull request open on the upstream.
    """

    def __init__(self, branch: str, upstream: Repository, fork_owner: str) -> None:
        super().__init__(
            f"no pull request on {upstream} has head '{fork_owner}:{branch}' - "
            "the branch has most likely not been promoted upstream yet"
        )


# %% models


class ReviewState(Enum):
    """
    The verdict a reviewer submitted with a review.
    """

    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    COMMENTED = "COMMENTED"
    DISMISSED = "DISMISSED"
    PENDING = "PENDING"


@dataclass(frozen=True)
class ThreadComment:
    """
    One comment inside a review thread.
    """

    database_id: int
    """
    GitHub's numeric identifier, the one that appears in comment permalinks.
    """

    author: str
    """
    The login of whoever wrote the comment.
    """

    body: str
    """
    The comment text, exactly as written.
    """

    created_at: str
    """
    When the comment was posted, as an ISO 8601 timestamp.
    """

    url: str
    """
    The permalink to this comment.
    """


@dataclass(frozen=True)
class ReviewThread:
    """
    A conversation anchored to one location in the pull request's diff.
    """

    identifier: str
    """
    GitHub's node identifier for the thread.
    """

    is_resolved: bool
    """
    Whether a reviewer has marked the thread resolved.
    """

    is_outdated: bool
    """
    Whether the diff hunk the thread was anchored to has since changed.
    """

    path: str
    """
    The file the thread is attached to.
    """

    line: int | None
    """
    The line the thread is attached to, absent once the hunk is outdated.
    """

    comments: list[ThreadComment]
    """
    Every comment in the thread, oldest first.
    """

    @property
    def location(self) -> str:
        """:return: The thread's ``path:line``, or just its path when it is outdated."""
        if self.line is None:
            return self.path
        return f"{self.path}:{self.line}"


@dataclass(frozen=True)
class Review:
    """
    A submitted review, separate from the threads it may have opened.
    """

    author: str
    """
    The login of the reviewer.
    """

    state: ReviewState
    """
    The verdict the reviewer submitted.
    """

    body: str
    """
    The review's summary text, which is often empty.
    """

    submitted_at: str
    """
    When the review was submitted, as an ISO 8601 timestamp.
    """


@dataclass(frozen=True)
class PullRequestReviewSnapshot:
    """
    Everything read from one upstream pull request in a single run.
    """

    number: int
    """
    The pull request's number on the upstream repository.
    """

    title: str
    """
    The pull request's title.
    """

    url: str
    """
    The pull request's web URL.
    """

    reviews: list[Review]
    """
    Every submitted review, oldest first.
    """

    threads: list[ReviewThread]
    """
    Every review thread, in the order GitHub returned them.
    """

    @property
    def unresolved_threads(self) -> list[ReviewThread]:
        """:return: The threads still awaiting action."""
        return [thread for thread in self.threads if not thread.is_resolved]

    def thread(self, identifier: str) -> ReviewThread:
        """
        Look one thread up by its node identifier.

        :param identifier: The thread's node identifier.
        :return: The matching thread.
        :raises KeyError: If no thread carries that identifier.
        """
        for thread in self.threads:
            if thread.identifier == identifier:
                return thread
        raise KeyError(identifier)


# %% transport


class GraphQLTransport(Protocol):
    """
    Sends a GraphQL document to GitHub and returns its ``data`` payload.
    """

    def execute(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """
        Run one GraphQL query.

        :param query: The GraphQL document.
        :param variables: The document's variables.
        :return: The response's ``data`` payload.
        """


@dataclass
class GitHubCommandTransport:
    """
    A transport that shells out to ``gh api graphql``.

    The runner already ships ``gh`` and authenticates it from ``GITHUB_TOKEN``, so this
    holds no credential handling of its own.
    """

    executable: str = "gh"
    """
    The command to invoke, overridable for testing.
    """

    def execute(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """
        Run one GraphQL query through ``gh``.

        :param query: The GraphQL document.
        :param variables: The document's variables.
        :return: The response's ``data`` payload.
        :raises GitHubCommandFailed: If ``gh`` fails or GitHub answers with errors.
        """
        request = json.dumps({"query": query, "variables": variables})
        completed = subprocess.run(
            [self.executable, "api", "graphql", "--input", "-"],
            input=request,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise GitHubCommandFailed(
                f"{self.executable} exited {completed.returncode}: "
                f"{completed.stderr.strip()}"
            )
        response = json.loads(completed.stdout)
        if "errors" in response:
            raise GitHubCommandFailed(
                "; ".join(error["message"] for error in response["errors"])
            )
        return response["data"]


# %% queries

PULL_REQUEST_FOR_BRANCH = """
query($owner: String!, $name: String!, $headRefName: String!) {
  repository(owner: $owner, name: $name) {
    pullRequests(headRefName: $headRefName, first: 20,
                 orderBy: {field: CREATED_AT, direction: DESC}) {
      nodes { number state headRepositoryOwner { login } }
    }
  }
}
"""

REVIEW_THREADS_PAGE = """
query($owner: String!, $name: String!, $number: Int!, $threadCursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      number
      title
      url
      reviews(first: 100) {
        nodes { author { login } state body submittedAt }
      }
      reviewThreads(first: 100, after: $threadCursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          comments(first: 100) {
            nodes { databaseId author { login } body createdAt url }
          }
        }
      }
    }
  }
}
"""


# %% reading


def _login(holder: dict[str, Any] | None) -> str:
    """
    Read an author login, tolerating the null GitHub returns for deleted users.

    :param holder: The ``author`` object from a payload.
    :return: The login, or a placeholder when the account no longer exists.
    """
    if holder is None:
        return "(unknown)"
    return holder["login"]


@dataclass
class UpstreamReviewReader:
    """
    Reads one upstream pull request's review state through a transport.
    """

    transport: GraphQLTransport
    """
    How GraphQL queries reach GitHub.
    """

    upstream_repository: Repository
    """
    The repository the fork's pull requests are opened against.
    """

    fork_owner: str
    """
    The owner whose branches this reader will claim as its own.
    """

    def resolve_pull_request_number(self, branch: str) -> int:
        """
        Find the upstream pull request opened from *branch*.

        Prefers an open pull request, falling back to the most recent closed one so a
        branch under post-merge discussion still resolves.

        :param branch: The fork branch name.
        :return: The upstream pull request number.
        :raises UpstreamPullRequestNotFound: If the fork has no such pull request.
        """
        payload = self.transport.execute(
            PULL_REQUEST_FOR_BRANCH,
            {
                "owner": self.upstream_repository.owner,
                "name": self.upstream_repository.name,
                "headRefName": branch,
            },
        )
        candidates = [
            node
            for node in payload["repository"]["pullRequests"]["nodes"]
            if _login(node["headRepositoryOwner"]) == self.fork_owner
        ]
        if not candidates:
            raise UpstreamPullRequestNotFound(
                branch, self.upstream_repository, self.fork_owner
            )
        open_candidates = [node for node in candidates if node["state"] == "OPEN"]
        return (open_candidates or candidates)[0]["number"]

    def snapshot(self, pull_request_number: int) -> PullRequestReviewSnapshot:
        """
        Read every review and review thread on one upstream pull request.

        :param pull_request_number: The upstream pull request's number.
        :return: The assembled snapshot.
        """
        threads: list[ReviewThread] = []
        cursor: str | None = None
        pull_request: dict[str, Any] = {}
        while True:
            payload = self.transport.execute(
                REVIEW_THREADS_PAGE,
                {
                    "owner": self.upstream_repository.owner,
                    "name": self.upstream_repository.name,
                    "number": pull_request_number,
                    "threadCursor": cursor,
                },
            )
            pull_request = payload["repository"]["pullRequest"]
            page = pull_request["reviewThreads"]
            threads.extend(_read_thread(node) for node in page["nodes"])
            if not page["pageInfo"]["hasNextPage"]:
                break
            cursor = page["pageInfo"]["endCursor"]
        return PullRequestReviewSnapshot(
            number=pull_request["number"],
            title=pull_request["title"],
            url=pull_request["url"],
            reviews=[_read_review(node) for node in pull_request["reviews"]["nodes"]],
            threads=threads,
        )


def _read_thread(node: dict[str, Any]) -> ReviewThread:
    """
    Build a thread from its payload node.

    :param node: One ``reviewThreads`` node.
    :return: The parsed thread.
    """
    return ReviewThread(
        identifier=node["id"],
        is_resolved=node["isResolved"],
        is_outdated=node["isOutdated"],
        path=node["path"],
        line=node["line"],
        comments=[_read_comment(comment) for comment in node["comments"]["nodes"]],
    )


def _read_comment(node: dict[str, Any]) -> ThreadComment:
    """
    Build a comment from its payload node.

    :param node: One ``comments`` node.
    :return: The parsed comment.
    """
    return ThreadComment(
        database_id=node["databaseId"],
        author=_login(node["author"]),
        body=node["body"],
        created_at=node["createdAt"],
        url=node["url"],
    )


def _read_review(node: dict[str, Any]) -> Review:
    """
    Build a review from its payload node.

    :param node: One ``reviews`` node.
    :return: The parsed review.
    """
    return Review(
        author=_login(node["author"]),
        state=ReviewState(node["state"]),
        body=node["body"],
        submitted_at=node["submittedAt"],
    )


# %% configuration


def resolve_upstream_repository(
    path: Path = CONFIGURATION_PATH, override: str | None = None
) -> Repository:
    """
    Decide which repository the fork's pull requests are reviewed on.

    Reads the committed defaults only. The per-user layer lives on the personal-notes
    branch, which a runner does not check out, so *override* is the escape hatch for a
    checkout whose upstream differs.

    :param path: The committed stack configuration file.
    :param override: An ``owner/name`` reference outranking the file.
    :return: The upstream repository.
    """
    if override:
        return Repository.parse(override)
    values = tomllib.loads(path.read_text())
    return Repository.parse(values["upstream_repository"])


# %% report


@dataclass
class UnresolvedThreadReport:
    """
    Renders a snapshot as the markdown a session or a phone reads.
    """

    snapshot: PullRequestReviewSnapshot
    """
    The review state to describe.
    """

    include_resolved: bool = False
    """
    Whether threads already marked resolved are shown too.
    """

    def render(self) -> str:
        """:return: The report as markdown."""
        lines = [
            f"# Upstream review: #{self.snapshot.number} {self.snapshot.title}",
            "",
            self.snapshot.url,
            "",
        ]
        lines.extend(self._render_reviews())
        lines.extend(self._render_threads())
        return "\n".join(lines)

    def _render_reviews(self) -> list[str]:
        """:return: The submitted-reviews section."""
        if not self.snapshot.reviews:
            return ["## Reviews", "", "No reviews submitted.", ""]
        lines = ["## Reviews", ""]
        for review in self.snapshot.reviews:
            verdict = review.state.value.replace("_", " ").lower()
            lines.append(f"- **{review.author}** — {verdict} ({review.submitted_at})")
            if review.body.strip():
                lines.append(f"  > {review.body.strip()}")
        lines.append("")
        return lines

    def _render_threads(self) -> list[str]:
        """:return: The review-threads section."""
        shown = (
            self.snapshot.threads
            if self.include_resolved
            else self.snapshot.unresolved_threads
        )
        lines = [self._heading(len(shown)), ""]
        if not shown:
            lines.extend(["Nothing to act on.", ""])
            return lines
        for thread in shown:
            lines.extend(self._render_thread(thread))
        return lines

    def _heading(self, shown_count: int) -> str:
        """
        Describe the set actually being listed, not just the unresolved one.

        :param shown_count: How many threads the section goes on to list.
        :return: The section heading.
        """
        unresolved_count = len(self.snapshot.unresolved_threads)
        if not unresolved_count:
            return "## No unresolved review threads"
        if self.include_resolved:
            return f"## {shown_count} review threads, {unresolved_count} unresolved"
        return f"## {unresolved_count} unresolved review threads"

    def _render_thread(self, thread: ReviewThread) -> list[str]:
        """
        Render one thread with every comment in it.

        :param thread: The thread to render.
        :return: The thread's markdown lines.
        """
        markers = []
        if thread.is_resolved:
            markers.append("resolved")
        if thread.is_outdated:
            markers.append("outdated")
        suffix = f" _({', '.join(markers)})_" if markers else ""
        lines = [f"### `{thread.location}`{suffix}", ""]
        for comment in thread.comments:
            lines.append(f"- **{comment.author}**: {comment.body.strip()}")
        if thread.comments:
            lines.extend(["", f"<{thread.comments[0].url}>", ""])
        return lines


# %% command line


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    """
    Parse the command line.

    :param argv: The arguments to parse, defaulting to the process's own.
    :return: The parsed arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--pull-request", type=int, help="the upstream pull request number to read"
    )
    target.add_argument(
        "--branch", help="the fork branch whose upstream pull request to read"
    )
    parser.add_argument(
        "--fork-owner",
        default=os.environ.get("GITHUB_REPOSITORY_OWNER", ""),
        help="the owner whose branches to claim, defaulting to the runner's own",
    )
    parser.add_argument(
        "--upstream", help="an owner/name upstream outranking the configured one"
    )
    parser.add_argument(
        "--include-resolved",
        action="store_true",
        help="show threads already marked resolved as well",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """
    Read one upstream pull request and print its report.

    A branch that was never promoted upstream is an ordinary answer rather than a crash,
    so this boundary turns the script's own errors into a stated reason. Anything else
    still propagates with its traceback intact.

    :param argv: The arguments to parse, defaulting to the process's own.
    :return: The process exit status.
    """
    arguments = _parse_arguments(argv)
    try:
        report = _build_report(arguments)
    except UpstreamReviewError as failure:
        print(failure, file=sys.stderr)
        return 1
    print(report)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        Path(summary_path).write_text(report)
    return 0


def _build_report(arguments: argparse.Namespace) -> str:
    """
    Read the requested pull request and render its report.

    :param arguments: The parsed command line.
    :return: The rendered markdown.
    """
    reader = UpstreamReviewReader(
        GitHubCommandTransport(),
        resolve_upstream_repository(override=arguments.upstream),
        arguments.fork_owner,
    )
    number = arguments.pull_request or reader.resolve_pull_request_number(
        arguments.branch
    )
    return UnresolvedThreadReport(
        reader.snapshot(number), include_resolved=arguments.include_resolved
    ).render()


if __name__ == "__main__":
    sys.exit(main())
