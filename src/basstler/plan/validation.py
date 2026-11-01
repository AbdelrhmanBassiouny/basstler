"""
Checks a freshly loaded plan.yaml against the schema rules in plan-schema.md, reporting
every :class:`~basstler.exceptions.ValidationProblem` it carries at once.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

import rustworkx

from basstler.exceptions import (
    DependencyCycle,
    DuplicateItemId,
    InvalidBlockers,
    InvalidDependsOn,
    InvalidManifestRoot,
    InvalidSchemaVersion,
    MalformedDependencyReference,
    MissingPlanDirectory,
    PlanValidationError,
    SelfPlanReference,
    UnknownDependency,
    UnknownDependencyPlan,
    UnknownStatus,
    UnknownTrack,
    UnknownWave,
    ValidationProblem,
)
from basstler.plan.dependencies import (
    DependencyReference,
    PlanDirectory,
    ResolvedDependency,
)
from basstler.plan.model import ItemStatus, ManifestKey


# %% dependency cycles


@dataclass
class DependencyGraph:
    """
    The ``depends_on`` graph reachable from one plan's own items.

    Each node holds its key, written the way a manifest names it: a bare id for an item
    of that plan, ``<plan-id>/<item-id>`` for an item of another plan. Only what the
    plan can reach is walked, so a cycle wholly inside some other plan is that plan's
    own to report.
    """

    plan_id: Any
    """The validated plan's own id."""

    plan_directory: PlanDirectory | None = None
    """
    The plans a cross-plan reference resolves against.
    """

    graph: rustworkx.PyDiGraph = field(default_factory=rustworkx.PyDiGraph)
    """
    Every node reached so far, with an edge from each node to every entry it depends on.
    """

    node_indices_by_key: dict[str, int] = field(default_factory=dict)
    """
    Each node's index in :attr:`graph`, by its key.
    """

    walked_keys: set[str] = field(default_factory=set)
    """
    The keys of the nodes whose own edges are already recorded.
    """

    @classmethod
    def reachable_from(
        cls,
        plan_id: Any,
        references_by_identifier: dict[str, list[DependencyReference]],
        plan_directory: PlanDirectory | None,
    ) -> DependencyGraph:
        """
        Build the graph one plan's own items reach.

        :param plan_id: The validated plan's own id.
        :param references_by_identifier: Each of its items' parsed ``depends_on``.
        :param plan_directory: The plans a cross-plan reference resolves against.
        :return: The built graph.
        """
        graph = cls(plan_id=plan_id, plan_directory=plan_directory)
        for identifier, references in references_by_identifier.items():
            graph.add_node(identifier, None, references)
        return graph

    def find_cycle(self) -> list[str] | None:
        """
        Find one cycle in this graph, if any exists.

        :return: The cycle's node keys in order, starting from its earliest reached node
            and repeating it at the end, or ``None`` if the graph is acyclic.
        """
        found = next(iter(rustworkx.simple_cycles(self.graph)), None)
        if found is None:
            return None
        cycle = list(found)
        start = cycle.index(min(cycle))
        node_indices = [*cycle[start:], *cycle[:start], cycle[start]]
        return [self.graph[node_index] for node_index in node_indices]

    def add_node(
        self,
        node_key: str,
        holding_plan_id: str | None,
        references: list[DependencyReference],
    ) -> None:
        """
        Record one node's edges, then walk the foreign items it names.

        :param node_key: This node's key in the graph.
        :param holding_plan_id: The plan whose manifest wrote *references*, or ``None``
            for the validated plan itself.
        :param references: That node's own parsed ``depends_on``.
        """
        if node_key in self.walked_keys:
            return
        self.walked_keys.add(node_key)
        node_index = self.index_of(node_key)
        for reference in references:
            target_index = self.index_of(self.key_of(reference, holding_plan_id))
            self.graph.add_edge(node_index, target_index, None)
        for reference in references:
            self._add_node_in_another_plan(reference, holding_plan_id)

    def index_of(self, node_key: str) -> int:
        """
        The index of one node in :attr:`graph`, adding the node when it is reached for
        the first time.

        :param node_key: The node's key.
        """
        if node_key not in self.node_indices_by_key:
            self.node_indices_by_key[node_key] = self.graph.add_node(node_key)
        return self.node_indices_by_key[node_key]

    def key_of(
        self, reference: DependencyReference, holding_plan_id: str | None
    ) -> str:
        """
        The graph key for one reference.

        :param reference: The reference to key.
        :param holding_plan_id: The plan whose manifest wrote it, or ``None`` for the
            validated plan itself.
        :return: A bare id for an item of the validated plan, the full ``<plan-
            id>/<item-id>`` reference otherwise.
        """
        target_plan_id = self._plan_holding(reference, holding_plan_id)
        if target_plan_id is None:
            return reference.item_identifier
        return DependencyReference(
            item_identifier=reference.item_identifier, plan_id=target_plan_id
        ).text

    def _add_node_in_another_plan(
        self, reference: DependencyReference, holding_plan_id: str | None
    ) -> None:
        """
        Walk one reference onwards, if it names an item of another plan.

        :param reference: One parsed ``depends_on`` entry.
        :param holding_plan_id: The plan whose manifest wrote it, or ``None`` for the
            validated plan itself.
        """
        if self.plan_directory is None:
            return
        target_plan_id = self._plan_holding(reference, holding_plan_id)
        if target_plan_id is None:
            return
        dependency = self.plan_directory.resolve(
            DependencyReference(
                item_identifier=reference.item_identifier, plan_id=target_plan_id
            )
        )
        if not isinstance(dependency, ResolvedDependency):
            return
        self.add_node(
            self.key_of(reference, holding_plan_id),
            target_plan_id,
            [
                DependencyReference.from_text(entry)
                for entry in dependency.item.depends_on
            ],
        )

    def _plan_holding(
        self, reference: DependencyReference, holding_plan_id: str | None
    ) -> str | None:
        """
        Which other plan holds the item one reference names.

        :param reference: The reference to place.
        :param holding_plan_id: The plan whose manifest wrote it, or ``None`` for the
            validated plan itself.
        :return: That plan's id, or ``None`` when the item belongs to the plan being
            validated.
        """
        target_plan_id = reference.plan_id or holding_plan_id
        if target_plan_id == self.plan_id:
            return None
        return target_plan_id


# %% the validator


@dataclass
class PlanValidator:
    """
    Checks one freshly loaded plan.yaml against the schema rules plan-create is required
    to produce manifests that pass.

    It reads the loaded content rather than a :class:`Plan`, so partially malformed
    input still yields every problem it carries.
    """

    manifest: Any
    """
    The plan.yaml content, as ``yaml.safe_load`` returned it.
    """

    plan_directory: PlanDirectory | None = None
    """The other plans a ``depends_on`` entry may name, or ``None`` when only
    this plan's own items are available - in which case a cross-plan entry is
    a problem rather than a free pass."""

    def validate(self) -> None:
        """
        Check every rule.

        :raises PlanValidationError: If any rule is violated, carrying every problem
            found.
        """
        if not isinstance(self.manifest, dict):
            raise PlanValidationError([InvalidManifestRoot(self.manifest)])
        problems = [
            *self.schema_version_problems(),
            *self.duplicate_identifier_problems(),
            *(problem for item in self.items for problem in self.item_problems(item)),
            *self.cycle_problems(),
            *self.wave_problems(),
        ]
        if problems:
            raise PlanValidationError(problems)

    @property
    def plan_id(self) -> Any:
        """
        The validated plan's own id.
        """
        return self.manifest.get(ManifestKey.IDENTIFIER.key)

    @property
    def items(self) -> list[dict[str, Any]]:
        """
        The manifest's items, as loaded.
        """
        return self.manifest.get(ManifestKey.ITEMS.key, [])

    @cached_property
    def item_identifiers(self) -> list[str]:
        """
        Every item's effective id, in manifest order, duplicates included.
        """
        return [self.identifier_of(item) for item in self.items]

    @cached_property
    def track_identifiers(self) -> set[str]:
        """
        Every declared track's id.
        """
        return {
            track[ManifestKey.IDENTIFIER.key]
            for track in self.manifest.get(ManifestKey.TRACKS.key, [])
        }

    @cached_property
    def wave_identifiers(self) -> set[str]:
        """
        Every declared wave's id.
        """
        return {
            wave[ManifestKey.IDENTIFIER.key]
            for wave in self.manifest.get(ManifestKey.WAVES.key, [])
        }

    def identifier_of(self, item: dict[str, Any]) -> str:
        """
        One item's effective id: its ``id``, else its ``branch``.

        :param item: The item, as loaded.
        """
        return item.get(ManifestKey.IDENTIFIER.key) or item.get(ManifestKey.BRANCH.key)

    def schema_version_problems(self) -> list[ValidationProblem]:
        """
        The problem with the manifest's ``schema_version``, if any.
        """
        schema_version = self.manifest.get(ManifestKey.SCHEMA_VERSION.key)
        if schema_version == InvalidSchemaVersion.supported_version:
            return []
        return [InvalidSchemaVersion(schema_version)]

    def duplicate_identifier_problems(self) -> list[ValidationProblem]:
        """
        The problem of two items sharing an effective id, if any.
        """
        duplicate_identifiers = sorted(
            identifier
            for identifier, count in Counter(self.item_identifiers).items()
            if count > 1
        )
        if not duplicate_identifiers:
            return []
        return [DuplicateItemId(duplicate_identifiers)]

    def item_problems(self, item: dict[str, Any]) -> list[ValidationProblem]:
        """
        Every problem one item carries.

        :param item: The item, as loaded.
        """
        item_identifier = self.identifier_of(item)
        problems: list[ValidationProblem] = []
        if item.get(ManifestKey.TRACK.key) not in self.track_identifiers:
            problems.append(
                UnknownTrack(item_identifier, item.get(ManifestKey.TRACK.key))
            )
        if item.get(ManifestKey.STATUS.key) not in ItemStatus.accepted_spellings():
            problems.append(
                UnknownStatus(item_identifier, item.get(ManifestKey.STATUS.key))
            )
        depends_on = item.get(ManifestKey.DEPENDS_ON.key)
        if depends_on is not None and not isinstance(depends_on, list):
            problems.append(InvalidDependsOn(item_identifier, type(depends_on)))
        else:
            problems.extend(
                problem
                for entry in depends_on or []
                if (problem := self.dependency_problem(item_identifier, entry))
                is not None
            )
        blockers = item.get(ManifestKey.BLOCKERS.key)
        if blockers is not None and not isinstance(blockers, list):
            problems.append(InvalidBlockers(item_identifier, type(blockers)))
        return problems

    def dependency_problem(
        self, item_identifier: str, entry: Any
    ) -> ValidationProblem | None:
        """
        Check one ``depends_on`` entry.

        :param item_identifier: The depending item's effective id.
        :param entry: The entry, exactly as the manifest wrote it.
        :return: The problem the entry carries, or ``None`` if it resolves.
        """
        if not isinstance(entry, str):
            return UnknownDependency(item_identifier, entry)
        reference = DependencyReference.from_text(entry)
        if not reference.is_well_formed:
            return MalformedDependencyReference(item_identifier, entry)
        if not reference.names_another_plan:
            if reference.item_identifier in self.item_identifiers:
                return None
            return UnknownDependency(item_identifier, entry)
        if reference.plan_id == self.plan_id:
            return SelfPlanReference(item_identifier, entry)
        if self.plan_directory is None:
            return MissingPlanDirectory(item_identifier, entry)
        if self.plan_directory.plan(reference.plan_id) is None:
            return UnknownDependencyPlan(item_identifier, entry)
        if not isinstance(self.plan_directory.resolve(reference), ResolvedDependency):
            return UnknownDependency(item_identifier, entry)
        return None

    def cycle_problems(self) -> list[ValidationProblem]:
        """
        The problem of a ``depends_on`` chain looping back on itself, if one reachable
        from this plan's items does.
        """
        references_by_identifier = {
            self.identifier_of(item): [
                DependencyReference.from_text(entry)
                for entry in item.get(ManifestKey.DEPENDS_ON.key) or []
                if isinstance(entry, str)
            ]
            for item in self.items
            if isinstance(item.get(ManifestKey.DEPENDS_ON.key) or [], list)
        }
        cycle = DependencyGraph.reachable_from(
            self.plan_id, references_by_identifier, self.plan_directory
        ).find_cycle()
        if cycle is None:
            return []
        return [DependencyCycle(cycle)]

    def wave_problems(self) -> list[ValidationProblem]:
        """
        Every track whose ``wave`` names no declared wave.
        """
        return [
            UnknownWave(
                track[ManifestKey.IDENTIFIER.key], track.get(ManifestKey.WAVE.key)
            )
            for track in self.manifest.get(ManifestKey.TRACKS.key, [])
            if track.get(ManifestKey.WAVE.key) not in self.wave_identifiers
        ]
