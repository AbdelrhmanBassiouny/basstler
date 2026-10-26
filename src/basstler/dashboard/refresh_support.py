#!/usr/bin/env python3
"""
Small JSON-plumbing helpers refresh_dashboard.sh needs between its script calls
(plan/sync_manifest_status.py, then dashboard/plan_page.py) - extracted so that
plumbing is real, tested code instead of inline ``python3 -c`` snippets
embedded in the shell script.

Usage:
    python3 dashboard/refresh_support.py count-corrected '<sync summary JSON>'
    python3 dashboard/refresh_support.py check-publication --key <plan-id> \\
        --build-summary '<build summary JSON>' [--cache <dashboard-urls.yaml>]
    python3 dashboard/refresh_support.py merge-summaries '<summary JSON>' ...
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from basstler.dashboard.publication import (
    DashboardUrlCache,
    PublicationCheck,
    PublicationField,
)
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""


class SummaryKeyCollisionError(ValueError):
    """Raised when plan/sync_manifest_status.py's and dashboard/plan_page.py's printed
    summaries share a key - merge_summaries can no longer assume a plain
    dict merge is safe once that holds."""


def count_corrected(sync_summary_json: str) -> int:
    """
    The number of items ``plan/sync_manifest_status.py`` corrected, from its
    ``{"corrected": [...]}`` summary.

    :param sync_summary_json:``plan/sync_manifest_status.py``'s printed JSON summary.
    :return: How many items were corrected.
    """
    return len(json.loads(sync_summary_json)["corrected"])


def check_publication(
    build_summary_json: str, key: str, cache_text: str
) -> PublicationCheck:
    """
    Check whether the dashboard ``dashboard/plan_page.py`` just wrote is already
    published.

    :param build_summary_json:``dashboard/plan_page.py``'s printed JSON summary, which
        carries the written files' content digest.
    :param key: The dashboard's cache key.
    :param cache_text: The dashboard-URL cache's text, empty when there is none.
    :return: Where the dashboard goes, and whether it is already published there.
    """
    content_digest = json.loads(build_summary_json)[PublicationField.CONTENT_DIGEST]
    return DashboardUrlCache.from_yaml(cache_text).check(key, content_digest)


def merge_summaries(*summaries_json: str) -> dict[str, Any]:
    """
    Merge the JSON summaries the refresh's steps print into the one object the calling
    skill reports from.

    :param summaries_json: Each step's printed JSON summary.
    :raises SummaryKeyCollisionError: If two summaries share a key.
    :return: The summaries merged into one dict.
    """
    merged: dict[str, Any] = {}
    for summary in map(json.loads, summaries_json):
        shared_keys = merged.keys() & summary.keys()
        if shared_keys:
            raise SummaryKeyCollisionError(
                f"summaries share key(s): {', '.join(sorted(shared_keys))}"
            )
        merged |= summary
    return merged


def main() -> int:
    """
    Parse arguments, dispatch to the requested subcommand, and print its result.

    See the module docstring for the CLI contract.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    count_corrected_parser = subparsers.add_parser("count-corrected")
    count_corrected_parser.add_argument("sync_summary_json")

    check_publication_parser = subparsers.add_parser("check-publication")
    check_publication_parser.add_argument("--key", required=True)
    check_publication_parser.add_argument("--build-summary", required=True)
    check_publication_parser.add_argument("--cache", default=None)

    merge_summaries_parser = subparsers.add_parser("merge-summaries")
    merge_summaries_parser.add_argument("summaries_json", nargs="+")

    arguments = parser.parse_args()

    if arguments.command == "count-corrected":
        logger.info(count_corrected(arguments.sync_summary_json))
    elif arguments.command == "check-publication":
        cache_text = (
            "" if arguments.cache is None else Path(arguments.cache).read_text()
        )
        publication = check_publication(
            arguments.build_summary, arguments.key, cache_text
        )
        logger.info(json.dumps(publication.to_json()))
    else:
        logger.info(json.dumps(merge_summaries(*arguments.summaries_json)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
