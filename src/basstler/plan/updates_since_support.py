#!/usr/bin/env python3
"""
Shared support for plan-updates-since.sh: the CLI option name, every user-facing message
string, and how tracking-issue comments are printed.

Kept as a real, testable module rather than inline ``python3 -c`` snippets in the
shell script (mirrors plan/manifest_tools.py's own reasoning for save-plan.sh), and
defined here exactly once so the shell script prints these strings by calling into
this module instead of embedding its own copy, and the test suite imports the same
constants instead of hardcoding a second copy of them.
"""

from __future__ import annotations

import json
import sys
from enum import StrEnum

from cyclopts import App

from basstler.github.issue import PostedIssueComment
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""


class PlanUpdatesSinceOption(StrEnum):
    """
    Command-line options plan-updates-since.sh accepts.
    """

    SINCE = "--since"
    """
    Overrides the recorded stamp with an explicit baseline commit SHA.
    """


class PlanUpdatesSinceMessage(StrEnum):
    """
    Fixed messages plan-updates-since.sh prints.
    """

    NO_CHANGES = "No changes."
    """
    Printed when the plan directory has no diff since the baseline commit.
    """

    NO_NEW_COMMENTS = "No new comments."
    """
    Printed when the tracking issue has no comments newer than the baseline.
    """

    NO_TRACKING_ISSUE = (
        "This plan has no tracking_issue set - nothing to check for new comments."
    )
    """
    Printed when the plan's manifest has no tracking_issue field.
    """


def no_default_repository_message(plan_id: str, tracking_issue: str) -> str:
    """
    Build the error printed when a plan has a tracking_issue but no default_repository
    to resolve it against.

    :param plan_id: The plan's id.
    :param tracking_issue: The plan's tracking_issue number, as a string.
    :return: The error message.
    """
    return (
        f"Plan '{plan_id}' has tracking_issue set (#{tracking_issue}) but no\n"
        "default_repository - cannot tell which GitHub repository to query."
    )


def format_issue_comments(comments_json: str) -> str:
    """
    Render a GitHub issue-comments API response as human-readable text.

    :param comments_json: The raw JSON array GitHub's comments endpoint returned.
    :return: One formatted block per comment separated by "---" lines, or
        :attr:`PlanUpdatesSinceMessage.NO_NEW_COMMENTS` if the array is empty.
    """
    comments = [
        PostedIssueComment.from_json(comment) for comment in json.loads(comments_json)
    ]
    if not comments:
        return PlanUpdatesSinceMessage.NO_NEW_COMMENTS.value
    return "\n---\n".join(comment.formatted() for comment in comments) + "\n---"


class PlanUpdatesSinceCommand(StrEnum):
    """
    The subcommands plan-updates-since.sh calls this module with.
    """

    PRINT_COMMENTS = "print-comments"
    """
    Print the tracking issue's new comments, read from stdin.
    """

    PRINT_NO_CHANGES_MESSAGE = "print-no-changes-message"
    """
    Print :attr:`PlanUpdatesSinceMessage.NO_CHANGES`.
    """

    PRINT_NO_TRACKING_ISSUE_MESSAGE = "print-no-tracking-issue-message"
    """
    Print :attr:`PlanUpdatesSinceMessage.NO_TRACKING_ISSUE`.
    """

    PRINT_NO_DEFAULT_REPOSITORY_MESSAGE = "print-no-default-repository-message"
    """
    Print why the tracking issue cannot be read without a default repository.
    """


updates_since_app = App(
    name="basstler.plan.updates_since_support",
    help="The messages and comment rendering plan-updates-since.sh prints.",
)
"""
This module's command line: one command per :class:`PlanUpdatesSinceCommand`.
"""


@updates_since_app.command(name=PlanUpdatesSinceCommand.PRINT_COMMENTS)
def print_comments() -> None:
    """
    Read a GitHub issue-comments JSON response from stdin and print it.
    """
    logger.info(format_issue_comments(sys.stdin.read()))


@updates_since_app.command(name=PlanUpdatesSinceCommand.PRINT_NO_CHANGES_MESSAGE)
def print_no_changes_message() -> None:
    """
    Print that the plan has not changed since the baseline.
    """
    logger.info(PlanUpdatesSinceMessage.NO_CHANGES.value)


@updates_since_app.command(name=PlanUpdatesSinceCommand.PRINT_NO_TRACKING_ISSUE_MESSAGE)
def print_no_tracking_issue_message() -> None:
    """
    Print that the plan has no tracking issue to read.
    """
    logger.info(PlanUpdatesSinceMessage.NO_TRACKING_ISSUE.value)


@updates_since_app.command(
    name=PlanUpdatesSinceCommand.PRINT_NO_DEFAULT_REPOSITORY_MESSAGE
)
def print_no_default_repository_message(plan_id: str, tracking_issue: str, /) -> None:
    """
    Print why the tracking issue cannot be read without a default repository.

    :param plan_id: The plan's id.
    :param tracking_issue: The tracking issue's number.
    """
    logger.error(no_default_repository_message(plan_id, tracking_issue))


if __name__ == "__main__":
    updates_since_app(sys.argv[1:])
