#!/usr/bin/env python3
"""
Read :mod:`basstler.plan.sync_manifest_status`'s printed summary for ``sync_plan.sh``.

Usage:
    "${BASSTLER_PYTHON}" -m basstler.plan.sync_summary count-corrected '<summary JSON>'
"""

from __future__ import annotations

import argparse
import json
import sys

from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% the summary


def count_corrected(sync_summary_json: str) -> int:
    """
    :param sync_summary_json: :mod:`basstler.plan.sync_manifest_status`'s printed
        ``{"corrected": [...]}`` summary.
    :return: How many items it corrected.
    """
    return len(json.loads(sync_summary_json)["corrected"])


# %% the command


def main() -> int:
    """
    Parse arguments and print how many items the summary names as corrected.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    count_corrected_parser = subparsers.add_parser("count-corrected")
    count_corrected_parser.add_argument("sync_summary_json")
    arguments = parser.parse_args()
    logger.info(count_corrected(arguments.sync_summary_json))
    return 0


if __name__ == "__main__":
    sys.exit(main())
