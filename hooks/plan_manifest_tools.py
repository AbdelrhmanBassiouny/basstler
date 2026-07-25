#!/usr/bin/env python3
"""
Small plan.yaml manifest utilities used by save-plan.sh.

Kept as a real, testable script rather than inline ``python3 -c`` snippets
in the shell script, so this logic can be read, changed, and (if it grows
non-trivial branches later) tested like any other code.

Usage:
    python3 plan_manifest_tools.py read-id <manifest-file>
    python3 plan_manifest_tools.py regenerate-branch-index \\
        --scratch-dir <dir> --plans-dir <relative-dir> \\
        --manifest-filename <name> --output <relative-path>
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from pathlib import Path

import yaml


def read_manifest_id(manifest_path: Path) -> str:
    """
    Read the ``id`` field out of a plan.yaml manifest.

    :param manifest_path: Path to the manifest file.
    :return: The manifest's ``id`` field, or an empty string if it has none.
    """
    with manifest_path.open() as manifest_file:
        manifest = yaml.safe_load(manifest_file)
    return manifest.get("id", "")


def regenerate_branch_index(
    scratch_directory: Path, plans_directory: str, manifest_filename: str
) -> str:
    """
    Rebuild the branch -> plan-id reverse index from every plan.yaml found.

    Scans every ``<plans_directory>/*/<manifest_filename>`` under ``scratch_directory``
    (a fresh checkout of the personal-notes branch) and emits one ``"<branch>\\t<plan-
    id>"`` line per item branch, first plan wins on a duplicate branch. See ``resolve-
    personal-notes-config.sh``'s ``plan_id_for_branch`` for why the format is TSV, not
    YAML.

    :param scratch_directory: The scratch worktree root to scan within.
    :param plans_directory: The plans directory, relative to ``scratch_directory`` (e.g.
        ``.claude/personal/plans``).
    :param manifest_filename: The manifest's fixed filename (e.g. ``plan.yaml``).
    :return: The regenerated index content, ready to write to disk.
    """
    lines = []
    seen_branches = set()
    manifest_pattern = os.path.join(
        scratch_directory, plans_directory, "*", manifest_filename
    )
    for manifest_path in sorted(glob.glob(manifest_pattern)):
        with open(manifest_path) as manifest_file:
            plan = yaml.safe_load(manifest_file)
        plan_id = plan["id"]
        for item in plan.get("items", []):
            branch = item.get("branch")
            if not branch or branch in seen_branches:
                continue
            seen_branches.add(branch)
            lines.append(f"{branch}\t{plan_id}")
    return "\n".join(lines) + ("\n" if lines else "")


def main() -> int:
    """
    Parse arguments and dispatch to the requested subcommand.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subcommands = parser.add_subparsers(dest="subcommand", required=True)

    read_id_parser = subcommands.add_parser(
        "read-id", help="Print a manifest's id field"
    )
    read_id_parser.add_argument("manifest_path", type=Path)

    regenerate_parser = subcommands.add_parser(
        "regenerate-branch-index", help="Rebuild the branch->plan-id index"
    )
    regenerate_parser.add_argument("--scratch-dir", required=True, type=Path)
    regenerate_parser.add_argument("--plans-dir", required=True)
    regenerate_parser.add_argument("--manifest-filename", required=True)
    regenerate_parser.add_argument(
        "--output", required=True, type=Path, help="Path to write the index to"
    )

    arguments = parser.parse_args()

    if arguments.subcommand == "read-id":
        print(read_manifest_id(arguments.manifest_path))
    elif arguments.subcommand == "regenerate-branch-index":
        index_content = regenerate_branch_index(
            arguments.scratch_dir, arguments.plans_dir, arguments.manifest_filename
        )
        arguments.output.write_text(index_content)

    return 0


if __name__ == "__main__":
    sys.exit(main())
