#!/usr/bin/env python3
"""
Small JSON-plumbing helpers refresh_dashboard.sh needs between its two script
calls (sync_manifest_status.py, then build_dashboard.py) - extracted so that
plumbing is real, tested code instead of inline ``python3 -c`` snippets
embedded in the shell script.

Usage:
    python3 refresh_dashboard_support.py count-corrected '<sync summary JSON>'
    python3 refresh_dashboard_support.py merge-summaries '<sync summary JSON>' '<build summary JSON>'
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def count_corrected(sync_summary_json: str) -> int:
    """
    The number of items ``sync_manifest_status.py`` corrected, from its ``{"corrected":
    [...]}`` summary.

    :param sync_summary_json:``sync_manifest_status.py``'s printed JSON summary.
    :return: How many items were corrected.
    """
    return len(json.loads(sync_summary_json)["corrected"])


def merge_summaries(sync_summary_json: str, build_summary_json: str) -> dict[str, Any]:
    """
    Merge ``sync_manifest_status.py``'s and ``build_dashboard.py``'s printed JSON
    summaries into the one object the calling skill reports from.

    :param sync_summary_json: ``sync_manifest_status.py``'s printed JSON summary.
    :param build_summary_json: ``build_dashboard.py``'s printed JSON summary.
    :return: The two summaries merged into one dict - the two never share a
        key, so merge order doesn't matter.
    """
    return {**json.loads(sync_summary_json), **json.loads(build_summary_json)}


def main() -> int:
    """
    Parse arguments, dispatch to the requested subcommand, and print its result.

    See the module docstring for the CLI contract.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    count_corrected_parser = subparsers.add_parser("count-corrected")
    count_corrected_parser.add_argument("sync_summary_json")

    merge_summaries_parser = subparsers.add_parser("merge-summaries")
    merge_summaries_parser.add_argument("sync_summary_json")
    merge_summaries_parser.add_argument("build_summary_json")

    arguments = parser.parse_args()

    if arguments.command == "count-corrected":
        print(count_corrected(arguments.sync_summary_json))
    else:
        print(
            json.dumps(
                merge_summaries(
                    arguments.sync_summary_json, arguments.build_summary_json
                )
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
