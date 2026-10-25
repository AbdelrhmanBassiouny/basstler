#!/usr/bin/env python3
"""
Stands in for ``gh`` on PATH where a test needs each REST path answered separately, as a
helper session's fetch asks for several::

    api <path>                          prints STUB_GH_RESPONSES[<path>]
    api --paginate --slurp <path>       prints STUB_GH_RESPONSES[<path>]
    api --allow-escape-sequences <path> prints STUB_GH_JOB_LOGS[<path>]

``STUB_GH_RESPONSES`` and ``STUB_GH_JOB_LOGS`` name JSON files mapping a path to its
answer. A path missing from them exits 64, so an unexpected request fails loudly.
"""

import json
import os
import sys
from pathlib import Path


def answers(variable: str) -> dict[str, object]:
    """
    :param variable: The environment variable naming a JSON file.
    :return: Its mapping, empty when the variable is unset.
    """
    location = os.environ.get(variable)
    return json.loads(Path(location).read_text()) if location else {}


def main(arguments: list[str]) -> int:
    """
    :param arguments: What ``gh`` was called with.
    :return: The exit status.
    """
    if arguments[:2] == ["api", "--allow-escape-sequences"]:
        logs = answers("STUB_GH_JOB_LOGS")
        if arguments[2] in logs:
            sys.stdout.write(str(logs[arguments[2]]))
            return 0
    elif arguments[:1] == ["api"]:
        responses = answers("STUB_GH_RESPONSES")
        if arguments[-1] in responses:
            sys.stdout.write(json.dumps(responses[arguments[-1]]))
            return 0
    print(f"stub gh: unexpected invocation: {' '.join(arguments)}", file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
