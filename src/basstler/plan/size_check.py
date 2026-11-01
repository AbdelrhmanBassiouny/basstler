#!/usr/bin/env python3
"""
Report whether a plan is already full, before ``/add-plan-item`` or ``/plan-create``
writes into or as it.

Counts a manifest's items the way ``save-plan.sh`` does - landed items pruned first -
and judges the count against :attr:`basstler.plan.size_limits.Measure.ITEM_COUNT`. A plan already
at that limit is full: one more item and the save is refused. Unlike the save, this never
refuses anything - it only answers the question a skill has to ask *before* a save is
even attempted, so the routing decision (grow this plan, or open a new one) can be made
before writing anything doomed to be refused later.

Usage:
    python3 -m basstler.plan.size_check --manifest <path>
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from basstler.plan.model import PlanManifest
from basstler.plan.size_limits import Measure


# %% output keys


class PlanSizeCheckField(StrEnum):
    """
    The keys this script's JSON output carries, named once so a producer or reader never
    spells one as a bare string.
    """

    ITEM_COUNT = "item_count"
    """
    How many items the measured manifest keeps once its landed items are pruned.
    """

    ITEM_LIMIT = "item_limit"
    """
    The most items a plan may hold.
    """

    IS_FULL = "is_full"
    """
    Whether the measured plan has no room for another item.
    """


# %% the result


@dataclass(frozen=True)
class PlanSizeCheckResult:
    """
    Whether one plan is already full, as this script reports it.
    """

    item_count: int
    """
    How many items the measured manifest keeps once its landed items are pruned.
    """

    item_limit: int
    """
    The most items a plan may hold.
    """

    @property
    def is_full(self) -> bool:
        """
        :return: Whether adding one more item would break the limit.
        """
        return self.item_count >= self.item_limit

    @classmethod
    def measure(cls, manifest_path: Path) -> PlanSizeCheckResult:
        """
        Count a plan's items and judge them against the item limit.

        :param manifest_path: The manifest to measure.
        :return: Whether that plan is already full.
        """
        manifest = PlanManifest.from_file(manifest_path).without_landed_items()
        return cls(
            item_count=len(manifest.items), item_limit=Measure.ITEM_COUNT.maximum
        )

    def to_json(self) -> dict[str, Any]:
        """
        :return: This result as the mapping this script prints as JSON.
        """
        return {
            PlanSizeCheckField.ITEM_COUNT: self.item_count,
            PlanSizeCheckField.ITEM_LIMIT: self.item_limit,
            PlanSizeCheckField.IS_FULL: self.is_full,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> PlanSizeCheckResult:
        """
        Build a result from this script's own parsed JSON output.

        :param data: The parsed JSON mapping.
        :return: The result it describes.
        """
        return cls(
            item_count=data[PlanSizeCheckField.ITEM_COUNT],
            item_limit=data[PlanSizeCheckField.ITEM_LIMIT],
        )


# %% command line


class PlanSizeCheckOption(StrEnum):
    """
    The options this script's command line takes.
    """

    MANIFEST = "--manifest"
    """
    The manifest to measure.
    """


class PlanSizeCheckArgument(StrEnum):
    """
    The names this script's command line parses its options under.
    """

    MANIFEST = "manifest"
    """
    The value of :attr:`PlanSizeCheckOption.MANIFEST`.
    """


def main() -> int:
    """
    Parse arguments and print whether the given manifest is already full.

    :return: 0, always - this reports, it never refuses.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        PlanSizeCheckOption.MANIFEST,
        dest=PlanSizeCheckArgument.MANIFEST,
        required=True,
        type=Path,
    )
    arguments = vars(parser.parse_args())

    result = PlanSizeCheckResult.measure(arguments[PlanSizeCheckArgument.MANIFEST])
    print(json.dumps(result.to_json()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
