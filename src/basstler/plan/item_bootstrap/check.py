"""
Checking what an item's manifest entry claims against local git.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from basstler.plan.item_bootstrap.documents import PlanDocuments, ProjectCheckout
from basstler.plan.item_bootstrap.report import OperationReport
from basstler.plan.item_bootstrap.vocabulary import PlanItemBootstrapExitCode, ReportKey
from basstler.plan.model import (
    ItemStatus,
    ManifestKey,
)

# %% checking an item


@dataclass(frozen=True)
class StalenessFinding:
    """
    One recorded field that local git contradicts.
    """

    manifest_key: ManifestKey
    """
    The field whose recorded value is stale.
    """

    recorded: str | None
    """
    What the manifest says, or ``None`` where it says nothing.
    """

    observed: str
    """
    What git shows instead, in the terms a reader acts on.
    """

    def to_json(self) -> dict[str, Any]:
        """
        Render the finding as the JSON a caller reads.
        """
        return {
            ReportKey.FIELD: self.manifest_key.key,
            ReportKey.RECORDED: self.recorded,
            ReportKey.OBSERVED: self.observed,
        }


@dataclass(frozen=True)
class StalenessReport(OperationReport):
    """
    Which of an item's recorded fields local git contradicts, if any.
    """

    plan_identifier: str
    """
    The plan the item belongs to.
    """

    item_identifier: str
    """
    The item that was checked.
    """

    findings: tuple[StalenessFinding, ...]
    """
    Every stale field, in the order the fields are checked.
    """

    @property
    def exit_code(self) -> PlanItemBootstrapExitCode:
        if self.findings:
            return PlanItemBootstrapExitCode.MANIFEST_IS_STALE
        return PlanItemBootstrapExitCode.SUCCESS

    def to_json(self) -> dict[str, Any]:
        return {
            ReportKey.STATUS: self.exit_code.name_for_a_caller,
            ReportKey.EXIT_CODE: int(self.exit_code),
            ReportKey.PLAN: self.plan_identifier,
            ReportKey.ITEM: self.item_identifier,
            ReportKey.FINDINGS: [finding.to_json() for finding in self.findings],
            ReportKey.DASHBOARD_COMMAND: self.dashboard_command_for(
                self.plan_identifier
            ),
        }


@dataclass(frozen=True)
class ItemCheckRequest:
    """
    Which item to compare against local git, and the remote its branch is published to.

    Local git only: the dashboard compares the manifest against GitHub on every refresh,
    so what is left is the window before a push.
    """

    plan_identifier: str
    """
    The plan the item belongs to.
    """

    item_identifier: str
    """
    The item to check.
    """

    remote: str = "origin"
    """
    The remote the item's branch would be published to.
    """

    def check(self, project_root: Path) -> StalenessReport:
        """
        Compare the item's recorded fields against what local git shows.

        :param project_root: The repository to run within.
        :raises UnknownPlanError: If the plan has no manifest on the notes branch.
        :raises UnknownItemError: If the plan tracks no item of that id.
        :return: What is stale, if anything.
        """
        item = PlanDocuments.load(self.plan_identifier, project_root).item(
            self.item_identifier
        )
        recorded_branch = item.get(ManifestKey.BRANCH.key)
        if not recorded_branch:
            findings: tuple[StalenessFinding, ...] = ()
        elif not ProjectCheckout(project_root).branch_is_published(
            recorded_branch, self.remote
        ):
            findings = (
                StalenessFinding(
                    manifest_key=ManifestKey.BRANCH,
                    recorded=recorded_branch,
                    observed=f"no branch of that name on {self.remote}",
                ),
            )
        else:
            findings = self.fields_a_published_branch_requires(item, recorded_branch)
        return StalenessReport(
            plan_identifier=self.plan_identifier,
            item_identifier=self.item_identifier,
            findings=findings,
        )

    @staticmethod
    def fields_a_published_branch_requires(
        item: dict[str, Any], branch: str
    ) -> tuple[StalenessFinding, ...]:
        """
        :param item: The item's parsed manifest mapping.
        :param branch: The published branch it records.
        :return: One finding per field an item whose branch is published still leaves
            unset or contradicts.
        """
        observed = f"{branch} is published"
        recorded_status = item.get(ManifestKey.STATUS.key)
        status_findings = (
            (
                StalenessFinding(
                    manifest_key=ManifestKey.STATUS,
                    recorded=recorded_status,
                    observed=observed,
                ),
            )
            if recorded_status is not None
            and ItemStatus(recorded_status) is ItemStatus.NOT_STARTED
            else ()
        )
        return status_findings + tuple(
            StalenessFinding(
                manifest_key=manifest_key, recorded=None, observed=observed
            )
            for manifest_key in (ManifestKey.SESSION, ManifestKey.PULL_REQUEST_NUMBER)
            if item.get(manifest_key.key) is None
        )
