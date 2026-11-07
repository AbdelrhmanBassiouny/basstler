"""
The distributions this package is split into, the layers they sit in, and which modules
each one ships.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum
from functools import cached_property
from itertools import combinations

import rustworkx

from basstler.exceptions import InconsistentPackageMap, PackageMapInconsistency

# %% layers and distributions


class Layer(IntEnum):
    """
    A layer of distributions; a distribution depends only on distributions in its own
    layer or a lower one.
    """

    CORE = 1
    """
    What every other distribution builds on: locations, environment, exceptions.
    """

    LOCAL_TOOLS = 2
    """
    Tools that work on a local checkout alone: git and the code rules.
    """

    GITHUB = 3
    """
    GitHub's data and the client that reads and writes it.
    """

    COLLABORATION = 4
    """
    Work on pull requests: upstream reviews, stacked pull requests and plans.
    """

    NOTES = 5
    """
    The personal notes and their setup.
    """

    USER_FACING = 6
    """
    What a user reads or invokes directly: the plan site hub and the skills.
    """

    MCP = 7
    """
    The Model Context Protocol server.
    """

    META_PACKAGE = 8
    """
    The ``basstler`` distribution, which installs every default distribution.
    """


class Distribution(StrEnum):
    """
    A distribution this package is released as, by its package name.
    """

    CORE = "basstler-core"
    """
    The foundation every other distribution imports.
    """

    GIT = "basstler-git"
    """
    Git commands and branches.
    """

    RULES = "basstler-rules"
    """
    The code rules, their checkers and the generated ``AGENTS.md``.
    """

    GITHUB = "basstler-github"
    """
    The GitHub client and the models of GitHub's data.
    """

    REVIEWS = "basstler-reviews"
    """
    Reading an upstream pull request's checks and review threads.
    """

    STACK = "basstler-stack"
    """
    Stacked pull request maintenance.
    """

    PLAN = "basstler-plan"
    """
    Plans and their items.
    """

    NOTES = "basstler-notes"
    """
    Personal notes, pull request progress notes and their setup.
    """

    HUB = "basstler-hub"
    """
    The plan site.
    """

    META_PACKAGE = "basstler"
    """
    The command tree every command is mounted on, installing every default
    distribution.
    """


# %% declarations


@dataclass(frozen=True)
class DistributionDeclaration:
    """
    What one distribution ships and which distributions its ``pyproject.toml`` lists.
    """

    distribution: Distribution
    """
    The distribution declared.
    """

    layer: Layer
    """
    The layer it sits in.
    """

    modules: tuple[str, ...]
    """
    The dotted names, within ``basstler``, of the modules and subpackages it ships; a
    subpackage ships every module under it that a longer name does not claim.
    """

    dependencies: tuple[Distribution, ...] = ()
    """
    The distributions it may import.
    """

    def claim_length(self, module: str) -> int:
        """
        :param module: A module's dotted name within ``basstler``.
        :return: The length of the longest of :attr:`modules` that is *module* or a
            package holding it; zero when none is.
        """
        return max(
            (
                len(claimed)
                for claimed in self.modules
                if module == claimed or module.startswith(f"{claimed}.")
            ),
            default=0,
        )


@dataclass(frozen=True)
class PackageMap:
    """
    The declarations of every distribution, checked to be layered and acyclic.
    """

    declarations: tuple[DistributionDeclaration, ...]
    """
    One declaration per distribution.
    """

    def __post_init__(self) -> None:
        """
        :raise InconsistentPackageMap: When the declarations are not layered and
            acyclic, or two of them claim one module.
        """
        for first, second in combinations(self.declarations, 2):
            if set(first.modules) & set(second.modules):
                raise InconsistentPackageMap(
                    PackageMapInconsistency.MODULE_CLAIMED_TWICE,
                    (first.distribution, second.distribution),
                )
        for declaration in self.declarations:
            for dependency in declaration.dependencies:
                if self[dependency].layer > declaration.layer:
                    raise InconsistentPackageMap(
                        PackageMapInconsistency.DEPENDENCY_ON_A_HIGHER_LAYER,
                        (declaration.distribution, dependency),
                    )
        cycle = next(iter(rustworkx.simple_cycles(self.dependency_graph)), None)
        if cycle is not None:
            raise InconsistentPackageMap(
                PackageMapInconsistency.DEPENDENCY_CYCLE,
                tuple(self.dependency_graph[node] for node in cycle),
            )

    def __getitem__(self, distribution: Distribution) -> DistributionDeclaration:
        """
        :param distribution: A declared distribution.
        :return: Its declaration.
        """
        for declaration in self.declarations:
            if declaration.distribution is distribution:
                return declaration
        raise InconsistentPackageMap(
            PackageMapInconsistency.UNDECLARED_DISTRIBUTION, (distribution,)
        )

    @cached_property
    def dependency_graph(self) -> rustworkx.PyDiGraph:
        """
        The distributions as nodes, with an edge from each to every one it depends on.
        """
        graph = rustworkx.PyDiGraph()
        nodes = {
            declaration.distribution: graph.add_node(declaration.distribution)
            for declaration in self.declarations
        }
        for declaration in self.declarations:
            for dependency in declaration.dependencies:
                graph.add_edge(nodes[declaration.distribution], nodes[dependency], None)
        return graph

    def claiming(self, module: str) -> DistributionDeclaration | None:
        """
        :param module: A module's dotted name within ``basstler``.
        :return: The declaration whose :attr:`DistributionDeclaration.modules` names
            *module* most specifically; none when no declaration names it.
        """
        claim_length, declaration = max(
            (
                (declaration.claim_length(module), declaration)
                for declaration in self.declarations
            ),
            key=lambda claim: claim[0],
        )
        return declaration if claim_length else None


# %% this package's map

PACKAGE_MAP = PackageMap(
    (
        DistributionDeclaration(
            Distribution.CORE,
            Layer.CORE,
            (
                "bash",
                "class_property",
                "command_line",
                "email_address",
                "environment",
                "exceptions",
                "exit_codes",
                "locations",
                "package_layout",
                "package_map",
                "plugin_root",
                "render_common",
                "shell_configuration",
                "standard_streams",
            ),
        ),
        DistributionDeclaration(
            Distribution.GIT,
            Layer.LOCAL_TOOLS,
            (
                "branch",
                "maintenance.git_commands",
                "maintenance.remote_branch",
                "stack.commit_move",
            ),
            (Distribution.CORE,),
        ),
        DistributionDeclaration(
            Distribution.RULES,
            Layer.LOCAL_TOOLS,
            ("code_rules",),
            (Distribution.CORE, Distribution.GIT),
        ),
        DistributionDeclaration(
            Distribution.GITHUB,
            Layer.GITHUB,
            (
                "actions_budget",
                "actions_usage",
                "github",
                "github_labels",
                "maintenance.constants",
                "maintenance.description",
                "maintenance.github",
                "pull_request_source",
                "pull_request_state",
                "release_version",
                "repository",
                "upstream_reviews.pull_request_models",
                "upstream_reviews.rest_models",
                "upstream_reviews.review_models",
                "upstream_reviews.vocabulary",
                "workflows",
            ),
            (Distribution.CORE, Distribution.GIT),
        ),
        DistributionDeclaration(
            Distribution.REVIEWS,
            Layer.COLLABORATION,
            ("upstream_reviews",),
            (Distribution.CORE, Distribution.GIT, Distribution.GITHUB),
        ),
        DistributionDeclaration(
            Distribution.STACK,
            Layer.COLLABORATION,
            ("maintenance", "stack"),
            (
                Distribution.CORE,
                Distribution.GIT,
                Distribution.GITHUB,
                Distribution.REVIEWS,
            ),
        ),
        DistributionDeclaration(
            Distribution.PLAN,
            Layer.COLLABORATION,
            ("plan",),
            (Distribution.CORE, Distribution.GIT, Distribution.GITHUB),
        ),
        DistributionDeclaration(
            Distribution.NOTES,
            Layer.NOTES,
            ("personal_notes", "setup"),
            (
                Distribution.CORE,
                Distribution.GIT,
                Distribution.GITHUB,
                Distribution.REVIEWS,
                Distribution.STACK,
            ),
        ),
        DistributionDeclaration(
            Distribution.HUB,
            Layer.USER_FACING,
            ("plan_site",),
            (
                Distribution.CORE,
                Distribution.GIT,
                Distribution.GITHUB,
                Distribution.REVIEWS,
                Distribution.STACK,
                Distribution.PLAN,
                Distribution.NOTES,
            ),
        ),
        DistributionDeclaration(
            Distribution.META_PACKAGE,
            Layer.META_PACKAGE,
            ("__main__",),
            (
                Distribution.CORE,
                Distribution.GIT,
                Distribution.RULES,
                Distribution.GITHUB,
                Distribution.REVIEWS,
                Distribution.STACK,
                Distribution.PLAN,
                Distribution.NOTES,
                Distribution.HUB,
            ),
        ),
    )
)
"""
Every distribution this package is released as.
"""
