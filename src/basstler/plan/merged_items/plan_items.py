"""
The items of one plan whose pull requests GitHub reports merged, recorded done in its
manifest so a save drops them as landed.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from basstler.exit_codes import CommandFailure, ExitCode, ManifestToolsExitCode
from basstler.github.pull_request_source import PullRequestSource
from basstler.github.repository import PullRequestReference
from basstler.plan.model import ItemStatus, PlanItem, PlanManifest
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% merged items


@dataclass(frozen=True)
class MergedItems:
    """
    The items of one plan whose pull requests GitHub reports merged, though the plan
    does not record them done.
    """

    manifest: PlanManifest
    """
    The plan whose items are looked up.
    """

    pull_request_source: PullRequestSource
    """
    Where the items' pull requests are read from.
    """

    @cached_property
    def items(self) -> list[PlanItem]:
        """
        :return: The merged items, in manifest order.
        :raises CommandFailure: If a pull request could not be read.
        """
        merged = []
        for item in self.manifest.items:
            if item.status is ItemStatus.DONE or item.pull_request_number is None:
                continue
            record = self.pull_request_source.pull_request(
                PullRequestReference(
                    self.manifest.repository_of(item), item.pull_request_number
                )
            )
            if record is not None and record.was_merged:
                merged.append(item)
        return merged

    @property
    def recorded_manifest(self) -> PlanManifest:
        """
        :return: The manifest with every merged item's status set to done.
        """
        return self.manifest.with_items_done({item.identifier for item in self.items})

    @classmethod
    def record(
        cls, manifest_path: Path, pull_request_source: PullRequestSource
    ) -> ExitCode:
        """
        Set the status of every merged item of the manifest at *manifest_path* to done,
        printing one line per item; a read that fails is printed and changes nothing.

        :param manifest_path: The ``plan.yaml`` to record the merged items in.
        :param pull_request_source: Where the items' pull requests are read from.
        :return: :attr:`ManifestToolsExitCode.SUCCESS`, or the status of the failed
            read.
        """
        merged_items = cls(PlanManifest.from_file(manifest_path), pull_request_source)
        try:
            items = merged_items.items
        except CommandFailure as failure:
            logger.error(f"Could not read which items' pull requests merged: {failure}")
            return failure.exit_code
        if not items:
            return ManifestToolsExitCode.SUCCESS
        merged_items.recorded_manifest.write(manifest_path)
        for item in items:
            logger.info(
                f"{item.identifier}: pull request #{item.pull_request_number} merged, "
                f"recorded done"
            )
        return ManifestToolsExitCode.SUCCESS
