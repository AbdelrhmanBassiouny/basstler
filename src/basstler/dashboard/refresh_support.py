#!/usr/bin/env python3
"""
The steps of a dashboard refresh that pass JSON between its scripts.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any

from basstler.dashboard.exceptions import SummaryKeyCollisionError
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% the step summaries


def count_corrected(sync_summary_json: str) -> int:
    """
    The number of items ``plan/sync_manifest_status.py`` corrected, from its
    ``{"corrected": [...]}`` summary.

    :param sync_summary_json:``plan/sync_manifest_status.py``'s printed JSON summary.
    :return: How many items were corrected.
    """
    return len(json.loads(sync_summary_json)["corrected"])


@dataclass(frozen=True)
class RefreshSummary:
    """
    The one JSON summary a refresh reports, merged from each of its steps' summaries.
    """

    entries: dict[str, Any]
    """
    Every step's summary entries, by key.
    """

    @classmethod
    def from_step_summaries(cls, *summaries_json: str) -> RefreshSummary:
        """
        :param summaries_json: Each step's printed JSON summary.
        :raises SummaryKeyCollisionError: If two summaries share a key.
        :return: The summaries merged into one.
        """
        entries: dict[str, Any] = {}
        for summary in map(json.loads, summaries_json):
            shared_keys = entries.keys() & summary.keys()
            if shared_keys:
                raise SummaryKeyCollisionError(shared_keys=sorted(shared_keys))
            entries |= summary
        return cls(entries=entries)


# %% the command


def main() -> int:
    """
    Parse arguments, dispatch to the requested subcommand, and print its result.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    count_corrected_parser = subparsers.add_parser("count-corrected")
    count_corrected_parser.add_argument("sync_summary_json")

    merge_summaries_parser = subparsers.add_parser("merge-summaries")
    merge_summaries_parser.add_argument("summaries_json", nargs="+")

    arguments = parser.parse_args()

    if arguments.command == "count-corrected":
        logger.info(count_corrected(arguments.sync_summary_json))
    else:
        summary = RefreshSummary.from_step_summaries(*arguments.summaries_json)
        logger.info(json.dumps(summary.entries))
    return 0


if __name__ == "__main__":
    sys.exit(main())
