#!/usr/bin/env python3
"""
Shared support for plan-updates-since.sh: the CLI option name, every user-facing message
string, and how tracking-issue comments are printed.

Kept as a real, testable module rather than inline ``python3 -c`` snippets in the
shell script (mirrors plan/manifest_tools.py's own reasoning for save-plan.sh), and
defined here exactly once so the shell script prints these strings by calling into
this module instead of embedding its own copy, and the test suite imports the same
constants instead of hardcoding a second copy of them.

Usage:
    python3 plan/updates_since_support.py print-comments < comments.json
    python3 plan/updates_since_support.py print-no-changes-message
    python3 plan/updates_since_support.py print-no-tracking-issue-message
    python3 plan/updates_since_support.py print-no-default-repository-message \\
        <plan-id> <tracking-issue-number>
"""

from __future__ import annotations

import argparse
import json
import sys
from enum import StrEnum

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


def main() -> int:
    """
    Parse arguments and dispatch to the requested subcommand.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subcommands = parser.add_subparsers(dest="subcommand", required=True)

    subcommands.add_parser(
        "print-comments",
        help="Read a GitHub issue-comments JSON response from stdin and print it",
    )
    subcommands.add_parser("print-no-changes-message")
    subcommands.add_parser("print-no-tracking-issue-message")
    no_default_repository_parser = subcommands.add_parser(
        "print-no-default-repository-message"
    )
    no_default_repository_parser.add_argument("plan_id")
    no_default_repository_parser.add_argument("tracking_issue")

    arguments = parser.parse_args()

    if arguments.subcommand == "print-comments":
        logger.info(format_issue_comments(sys.stdin.read()))
    elif arguments.subcommand == "print-no-changes-message":
        logger.info(PlanUpdatesSinceMessage.NO_CHANGES.value)
    elif arguments.subcommand == "print-no-tracking-issue-message":
        logger.info(PlanUpdatesSinceMessage.NO_TRACKING_ISSUE.value)
    elif arguments.subcommand == "print-no-default-repository-message":
        logger.error(
            no_default_repository_message(arguments.plan_id, arguments.tracking_issue)
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
