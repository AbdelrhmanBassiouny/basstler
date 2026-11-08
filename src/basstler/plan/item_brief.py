"""
Print the brief a session reads before working one plan item: the plan's header, the
item's entry, whether each of its dependencies is ready to build on, and the plan's
standing rules.

Run from the project, whose personal-notes branch it fetches. The dependencies' live
state is read from GitHub with the token the environment carries. Prints YAML.
"""

from __future__ import annotations

import sys
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from functools import cached_property
from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter

from basstler.plan_site.plan import Plan
from basstler.plan.check_dependency_readiness import DependencyReadiness
from basstler.plan.dependencies import DependencyResolver
from basstler.plan.item_bootstrap.documents import PlanDocuments, ProjectCheckout
from basstler.plan.model import PlanItem, PlanManifest
from basstler.plan.repository_rules import RepositoryRules
from basstler.plan.repository_rules_store import RepositoryRulesStore
from basstler.plan.size_limits import Roadmap
from basstler.plan.validation import PlanValidator
from basstler.pull_request_source import GitHubPullRequestSource, PullRequestSource
from basstler.command_line import plan_item_selection
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% choosing the item


class ItemSelection(ABC):
    """
    Which of a plan's items to brief.
    """

    @abstractmethod
    def select(self, manifest: PlanManifest) -> PlanItem:
        """
        :param manifest: The plan to choose from.
        :raises ItemNotTrackedError: If the plan has no such item.
        :return: The chosen item.
        """


@dataclass(frozen=True)
class ItemByIdentifier(ItemSelection):
    """
    The item with a given id.
    """

    identifier: str
    """
    The item's id.
    """

    def select(self, manifest: PlanManifest) -> PlanItem:
        return manifest.item_named(self.identifier)


@dataclass(frozen=True)
class ItemByBranch(ItemSelection):
    """
    The item worked on a given branch.
    """

    branch: str
    """
    The item's branch.
    """

    def select(self, manifest: PlanManifest) -> PlanItem:
        return manifest.item_on_branch(self.branch)


# %% the brief


class ItemBriefKey(StrEnum):
    """
    The keys a brief adds to the item's summary.
    """

    DEPENDENCIES = "dependencies"
    """
    Each dependency's live state and whether it is ready to build on.
    """

    STANDING_RULES = "standing_rules"
    """
    The plan's standing rules, one entry each.
    """

    REPOSITORY_RULES = "repository_rules"
    """
    The rules every plan of the repository follows, one entry each.
    """


@dataclass(frozen=True)
class ItemBrief:
    """
    Everything already known and decided about one plan item.
    """

    manifest: PlanManifest
    """
    The plan the item belongs to.
    """

    item: PlanItem
    """
    The briefed item.
    """

    dependencies: list[DependencyReadiness]
    """
    One readiness per entry of the item's ``depends_on``, in that order.
    """

    standing_rules: list[str]
    """
    The plan's roadmap entries.
    """

    repository_rules: RepositoryRules
    """
    The rules every plan of the repository follows.
    """

    @classmethod
    def read(
        cls,
        project_root: Path,
        plan_identifier: str,
        selection: ItemSelection,
        pull_request_source: PullRequestSource,
    ) -> ItemBrief:
        """
        Read the item's plan off the freshly fetched notes branch and classify its
        dependencies.

        :param project_root: The repository whose notes branch holds the plan.
        :param plan_identifier: The plan's id.
        :param selection: Which item to brief.
        :param pull_request_source: Where the dependencies' live state is read from.
        :raises UnknownPlanError: If the notes branch has no such plan.
        :raises ItemNotTrackedError: If the plan has no such item.
        :raises PlanValidationError: If the manifest breaks a rule.
        :return: The brief.
        """
        documents = PlanDocuments.load(plan_identifier, project_root)
        manifest = PlanManifest(documents.manifest)
        item = selection.select(manifest)
        with tempfile.TemporaryDirectory() as scratch:
            plan_directory = ProjectCheckout(project_root).check_out_manifests(
                Path(scratch)
            )
            PlanValidator(manifest.content, plan_directory).validate()
            plan = Plan.from_mapping(manifest.content)
            dependencies = DependencyReadiness.of_item(
                plan,
                item.identifier,
                pull_request_source.pull_requests_of(
                    DependencyResolver(plan, plan_directory)
                ),
                plan_directory,
            )
        return cls(
            manifest=manifest,
            item=item,
            dependencies=dependencies,
            standing_rules=Roadmap.from_text(documents.roadmap_text).entries,
            repository_rules=RepositoryRulesStore.from_project_root(
                project_root
            ).read_fetched(),
        )

    def render(self) -> str:
        """
        :return: The brief as YAML: the item's summary, then its dependencies, the
            repository's rules and the plan's standing rules.
        """
        return PlanManifest.summary_text(
            {
                **self.manifest.item_header(self.item),
                ItemBriefKey.DEPENDENCIES.value: [
                    dependency.to_json() for dependency in self.dependencies
                ],
                ItemBriefKey.REPOSITORY_RULES.value: [
                    rule.to_json() for rule in self.repository_rules.rules
                ],
                ItemBriefKey.STANDING_RULES.value: self.standing_rules,
            }
        )


# %% command line


class ItemBriefOption(StrEnum):
    """
    The options the command takes.
    """

    PLAN = "--plan"
    """
    The plan's id.
    """

    ITEM = "--item"
    """
    The item's id.
    """

    BRANCH = "--branch"
    """
    The item's branch, in place of its id.
    """


@dataclass
class ItemBriefCommandLine:
    """
    The command a skill runs to brief an item.
    """

    pull_request_source: PullRequestSource
    """
    Where the dependencies' live state is read from.
    """

    project_root: Path
    """
    The repository whose notes branch holds the plan.
    """

    @cached_property
    def app(self) -> App:
        """
        :return: The command line, briefing through :meth:`brief`.
        """
        app = App(
            name="basstler.plan.item_brief",
            help="Print the brief a session reads before working one plan item.",
        )
        app.default(self.brief)
        return app

    def brief(
        self,
        *,
        plan_identifier: Annotated[str, Parameter(name=ItemBriefOption.PLAN)],
        item_identifier: Annotated[
            str | None, Parameter(name=ItemBriefOption.ITEM, group=plan_item_selection)
        ] = None,
        branch: Annotated[
            str | None,
            Parameter(name=ItemBriefOption.BRANCH, group=plan_item_selection),
        ] = None,
    ) -> None:
        """
        Print the brief for one item of a plan, as YAML.

        :param plan_identifier: The plan's id.
        :param item_identifier: The item's id.
        :param branch: The item's branch, in place of its id.
        """
        selection = (
            ItemByBranch(branch)
            if branch is not None
            else ItemByIdentifier(item_identifier)
        )
        item_brief = ItemBrief.read(
            self.project_root, plan_identifier, selection, self.pull_request_source
        )
        logger.info(item_brief.render().rstrip("\n"))


def main() -> int:
    """
    Print the brief the command line asks for, reading live state from GitHub.
    """
    ItemBriefCommandLine(GitHubPullRequestSource.from_environment(), Path.cwd()).app(
        sys.argv[1:], result_action="return_value"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
