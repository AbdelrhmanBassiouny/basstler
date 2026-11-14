"""
Comparing two syntax trees node by node, where pluggable rules allow particular
differences and record each as a finding that is proved harmless afterwards.
"""

from __future__ import annotations

import ast
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import cached_property

from basstler.class_property import classproperty
from basstler.review_triage.calls import CallScope
from basstler.review_triage.comparison import ChangeKind
from basstler.review_triage.python_source import ImportBindings
from basstler.review_triage.renames import RenameMap
from basstler.review_triage.signatures import SignatureReader

# %% findings


class Finding(ABC):
    """
    One allowed difference between the trees, harmless only once :meth:`holds`.
    """

    @classproperty
    @abstractmethod
    def kind(cls) -> ChangeKind:
        """
        The kind of change a report lists this difference under.
        """

    @abstractmethod
    def holds(self, reader: SignatureReader, renames: RenameMap) -> bool:
        """
        :param reader: Reads the base commit's signatures.
        :param renames: The renames the pull request makes throughout.
        :return: Whether the difference cannot change what the code does.
        """

    def looked_up_names(self, renames: RenameMap) -> frozenset[str]:
        """
        :param renames: The renames the pull request makes throughout.
        :return: The names whose definitions :meth:`holds` looks up, to find every
            finding's together in one search.
        """
        return frozenset()


# %% rules


class DifferenceRule(ABC):
    """
    Compares the nodes of some types, allowing a particular difference between them.
    """

    @classproperty
    @abstractmethod
    def node_types(cls) -> tuple[type[ast.AST], ...]:
        """
        The types of the nodes this rule compares.
        """

    @abstractmethod
    def matches(self, base: ast.AST, head: ast.AST, matcher: TreeMatcher) -> bool:
        """
        :param base: A node of the base tree of one of :attr:`node_types`.
        :param head: The node of the same type at the same place in the head tree.
        :param matcher: The comparison in progress, for the nodes' children and to
            record findings.
        :return: Whether the two are equal but for differences this rule allows.
        """


# %% the comparison


@dataclass
class TreeMatcher:
    """
    One comparison of a base tree with a head tree, and the findings it records.
    """

    rules: tuple[DifferenceRule, ...]
    """
    The rules allowing differences, the first comparing a node's type deciding it.
    """

    head_imports: ImportBindings
    """
    The names the head version's imports bind.
    """

    findings: list[Finding] = field(default_factory=list)
    """
    Every allowed difference found so far.
    """

    enclosing_classes: list[str] = field(default_factory=list)
    """
    The names of the classes whose bodies are being compared, innermost last.
    """

    parameter_types: list[dict[str, str]] = field(default_factory=list)
    """
    For each function whose body is being compared, innermost last, the class each
    parameter it never assigns to is annotated with.
    """

    @cached_property
    def rule_by_type(self) -> dict[type[ast.AST], DifferenceRule]:
        """
        The rule comparing each node type some rule compares.
        """
        rules: dict[type[ast.AST], DifferenceRule] = {}
        for rule in reversed(self.rules):
            rules |= dict.fromkeys(rule.node_types, rule)
        return rules

    @property
    def scope(self) -> CallScope:
        """
        What the code around the nodes being compared tells about the names they use.
        """
        return CallScope(
            self.enclosing_classes[-1] if self.enclosing_classes else None,
            self.parameter_types[-1] if self.parameter_types else {},
        )

    def matches(self, base: object, head: object) -> bool:
        """
        :param base: A node of the base tree, a list of them or one of their values.
        :param head: What is at the same place in the head tree.
        :return: Whether the two are equal but for differences the rules allow.
        """
        if isinstance(base, list):
            return (
                isinstance(head, list)
                and len(base) == len(head)
                and all(map(self.matches, base, head))
            )
        if not isinstance(base, ast.AST):
            return base == head
        if type(base) is not type(head):
            return False
        rule = self.rule_by_type.get(type(base))
        if rule is None:
            return self.matches_fields(base, head)
        return rule.matches(base, head, self)

    def matches_fields(
        self, base: ast.AST, head: ast.AST, skipped: frozenset[str] = frozenset()
    ) -> bool:
        """
        :param base: A node of the base tree.
        :param head: A node of the same type at the same place in the head tree.
        :param skipped: The fields the caller compares itself.
        :return: Whether every other field matches.
        """
        return all(
            self.matches(base_value, head_value)
            for (field_name, base_value), (_, head_value) in zip(
                ast.iter_fields(base), ast.iter_fields(head), strict=True
            )
            if field_name not in skipped
        )

    def attempt(self, base: object, head: object) -> bool:
        """
        :meth:`matches`, keeping the findings it records only when the two match, so
        that a caller may try another way of matching them.
        """
        recorded = len(self.findings)
        if self.matches(base, head):
            return True
        del self.findings[recorded:]
        return False

    def record(self, finding: Finding) -> None:
        """
        :param finding: An allowed difference just found.
        """
        self.findings.append(finding)
