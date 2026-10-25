#!/usr/bin/env python3
"""
Auto-correct a plan.yaml's item statuses to ``done`` wherever GitHub confirms the item's
pull request is merged.

This is the one direction plan.yaml's manually-maintained ``status`` field
can be corrected without human judgment. Every other kind of drift
dashboard/plan_page.py's drift banner can report - a pull request number that doesn't
resolve, an item marked done while its pull request is still open, a closed-but-
unmerged pull request against an active status - means something happened that only a
person can interpret (abandoned? reverted? mistyped?), and stays a drift
flag for a human to read, exactly as before. "merged on GitHub" has no such
ambiguity, so leaving it as a standing drift flag would just mean the same
fact gets reported forever until someone manually edits the manifest - this
script is that edit, meant to run automatically as part of every
/plan-dashboard refresh. See plan-schema.md's "Why status is deliberately
thin" section for the full design reasoning.

Usage:
    python3 plan/sync_manifest_status.py \\
        --plan /tmp/plan.yaml \\
        --pr-data /tmp/pr_data.json \\
        [--output /tmp/plan.yaml] \\
        [--plans-dir /tmp/plans]

This validates the manifest before correcting anything, so --plans-dir is
needed by a manifest whose depends_on names another plan - the same directory
dashboard/plan_page.py takes.

Rewrites --plan in place, or writes to --output if given. Patches only the
exact ``status: <value>`` line of each corrected item - every other line is
left byte-for-byte untouched, so comments, key order, string wrapping, and
quoting all survive exactly. A full YAML load-mutate-dump round trip was
tried and rejected: even a library that claims to preserve formatting
(ruamel.yaml) re-flows long wrapped strings and normalizes ``null``
spellings on every write, turning a one-line status fix into an unreadable,
unrelated diff across the whole file.

pr_data.json shape: see :mod:`basstler.pull_request_state`.

Prints a one-line JSON summary to stdout:
    {"corrected": [{"id": "<item id>", "previous_status": "<status>"}, ...]}
An empty ``corrected`` list means nothing needed fixing.
"""

from __future__ import annotations

import argparse
import json
import re
from enum import Enum
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from basstler.exceptions import MissingStatusLineError, PlanValidationError
from basstler.plan.command_arguments import PlanCommandArguments
from basstler.plan.model import ItemStatus, ManifestKey
from basstler.plan.validation import PlanValidator
from basstler.pull_request_state import LiveState
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""


class ManifestLinePattern(Enum):
    """
    What the status patching looks for in a raw ``plan.yaml`` line.
    """

    ITEM_START = re.compile(r"^\s*- id:")
    """
    Matches the first line of an item block, which is always its ``id``.
    """

    STATUS_LINE = re.compile(r"^(\s*status:\s*)(\S.*?)\s*$")
    """
    Matches an item's ``status:`` line; group 2 is the status.
    """

    def match(self, line: str) -> re.Match[str] | None:
        """
        :param line: One manifest line.
        :return: This pattern's match at the line's start, if any.
        """
        return self.value.match(line)


@dataclass
class StatusCorrection:
    """
    One item whose manifest ``status`` was corrected to ``done``.
    """

    item_identifier: str
    """
    The corrected item's effective id (``id``, or ``branch`` if unset).
    """

    previous_status: ItemStatus
    """
    The status the manifest held before correction.
    """

    def to_json_dict(self) -> dict[str, str]:
        """
        Render to the plain-dict shape the calling skill expects.
        """
        return {"id": self.item_identifier, "previous_status": self.previous_status}

    @classmethod
    def items_to_correct(
        cls,
        plan: dict[str, Any],
        pull_requests_by_repository: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Find every item whose pull request is merged on GitHub but whose manifest
        ``status`` isn't already ``done``.

        :param plan: The raw, freshly-``yaml.safe_load``-ed plan.yaml content.
        :param pull_requests_by_repository: Live pull request state for every repository
            referenced by the plan's items.
        :return: The raw item mappings that need correcting, in manifest order.
        """
        default_repository = plan[ManifestKey.DEFAULT_REPOSITORY.key]
        return [
            item
            for item in plan.get(ManifestKey.ITEMS.key, [])
            if item.get(ManifestKey.STATUS.key) != ItemStatus.DONE.value
            and LiveState.classify(
                item.get(ManifestKey.PULL_REQUEST_NUMBER.key),
                item.get(ManifestKey.REPOSITORY.key) or default_repository,
                pull_requests_by_repository,
            )
            is LiveState.MERGED
        ]


@dataclass
class ItemBlock:
    """
    One item's lines in a raw plan.yaml, from its ``- id:`` line up to the next item's.
    """

    lines: list[str]
    """
    The block's lines, which :meth:`correct_status` edits in place.
    """

    @property
    def item_identifier(self) -> str:
        """
        The id written on the block's first line.
        """
        return self.lines[0].strip().removeprefix("- id:").strip()

    def correct_status(self) -> StatusCorrection:
        """
        Set this block's ``status:`` line to ``done``.

        :raises MissingStatusLineError: If the block has no ``status:`` line.
        :return: The correction made.
        """
        status_line_index = next(
            (
                index
                for index, line in enumerate(self.lines)
                if ManifestLinePattern.STATUS_LINE.match(line)
            ),
            None,
        )
        if status_line_index is None:
            raise MissingStatusLineError(self.item_identifier)
        match = ManifestLinePattern.STATUS_LINE.match(self.lines[status_line_index])
        self.lines[status_line_index] = f"{match.group(1)}{ItemStatus.DONE.value}"
        return StatusCorrection(self.item_identifier, ItemStatus(match.group(2)))


@dataclass
class ManifestText:
    """
    A raw plan.yaml's text, split into the lines before its first item and one block per
    item.
    """

    preamble: list[str]
    """
    The lines before the first item block.
    """

    item_blocks: list[ItemBlock]
    """
    Every item block, in manifest order.
    """

    @classmethod
    def parse(cls, text: str) -> ManifestText:
        """
        :param text: The plan.yaml file's raw text.
        :return: The text split into its preamble and item blocks.
        """
        lines = text.split("\n")
        boundaries = [
            index
            for index, line in enumerate(lines)
            if ManifestLinePattern.ITEM_START.match(line)
        ] + [len(lines)]
        return cls(
            preamble=lines[: boundaries[0]],
            item_blocks=[
                ItemBlock(lines[start:end])
                for start, end in zip(boundaries, boundaries[1:])
            ],
        )

    @property
    def text(self) -> str:
        """
        The plan.yaml text as it now stands, every unedited line byte-for-byte as
        parsed.
        """
        return "\n".join(
            self.preamble + [line for block in self.item_blocks for line in block.lines]
        )

    def correct_statuses(
        self, items_to_correct: list[dict[str, Any]]
    ) -> list[StatusCorrection]:
        """
        Set the ``status:`` line of each item in ``items_to_correct`` to ``done``,
        leaving every other line untouched.

        :param items_to_correct: Raw item mappings, as found by
            :meth:`StatusCorrection.items_to_correct`.
        :raises MissingStatusLineError: If one of those items' block has no ``status:``
            line.
        :return: The correction made to each item, in manifest order.
        """
        identifiers_to_correct = {
            item.get(ManifestKey.IDENTIFIER.key) or item.get(ManifestKey.BRANCH.key)
            for item in items_to_correct
        }
        return [
            block.correct_status()
            for block in self.item_blocks
            if block.item_identifier in identifiers_to_correct
        ]


def main() -> int:
    """
    Parse arguments, apply corrections, and print the summary.

    See the module docstring for the CLI contract.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    PlanCommandArguments.add_to(parser)
    parser.add_argument(
        "--output",
        default=None,
        help="Path to write the corrected plan.yaml to - defaults to --plan (in place)",
    )
    arguments = parser.parse_args()
    plan_arguments = PlanCommandArguments.from_namespace(arguments)

    manifest_text = ManifestText.parse(plan_arguments.plan_path.read_text())
    plan = yaml.safe_load(manifest_text.text)
    try:
        PlanValidator(plan, plan_arguments.plan_directory).validate()
    except PlanValidationError as error:
        logger.error(f"plan.yaml failed validation: {error}")
        return 1
    pull_requests_by_repository = plan_arguments.read_pull_requests_by_repository()

    items_to_correct = StatusCorrection.items_to_correct(
        plan, pull_requests_by_repository
    )
    corrections = manifest_text.correct_statuses(items_to_correct)

    output_path = (
        Path(arguments.output) if arguments.output else plan_arguments.plan_path
    )
    output_path.write_text(manifest_text.text)

    logger.info(json.dumps({"corrected": [c.to_json_dict() for c in corrections]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
