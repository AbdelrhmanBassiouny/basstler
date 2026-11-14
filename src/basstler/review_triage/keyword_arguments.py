"""
Judging a Python change that passes positional arguments by keyword, makes parameters
keyword-only or adds identity decorators as mechanical, once every call is shown to
bind the same values to the same parameters as before.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from basstler.class_property import classproperty
from basstler.review_triage.calls import CALLEE_RESOLUTIONS, CalleeResolution
from basstler.review_triage.comparison import (
    ChangeKind,
    ChangeKinds,
    JudgmentContext,
    MechanicalChange,
    PythonComparison,
)
from basstler.review_triage.definitions import DataclassName
from basstler.review_triage.python_source import PythonSource
from basstler.review_triage.renames import RenameMap
from basstler.review_triage.signatures import DecoratorPolicy, SignatureReader
from basstler.review_triage.tree_matching import DifferenceRule, Finding, TreeMatcher

# %% what the change consists of


class KeywordChange(ChangeKind):
    """
    The kinds of change of calls, parameters and decorators this judgment finds.
    """

    KEYWORD_ARGUMENTS = "keyword arguments"
    """
    Positional arguments are passed by the names of the parameters they were bound to.
    """

    KEYWORD_ONLY = "keyword-only parameters"
    """
    Parameters or dataclass fields became keyword-only; a call left passing them
    positionally fails instead of binding differently.
    """

    IDENTITY_DECORATORS = "identity decorators"
    """
    Decorators that return what they decorate unchanged were added.
    """


# %% findings


@dataclass(frozen=True)
class KeywordConversion(Finding):
    """
    A call whose trailing positional arguments the head commit passes by keyword.
    """

    callee: str
    """
    The last name of the called expression, the one its definitions are found by.
    """

    first_position: int
    """
    The position of the first argument now passed by keyword.
    """

    keywords: tuple[str, ...]
    """
    The keywords of the arguments from that position on, in order.
    """

    resolution: CalleeResolution
    """
    How the call reaches its callee.
    """

    enclosing_class: str | None
    """
    The name of the class whose body holds the call, ``None`` outside a class.
    """

    @classproperty
    def kind(cls) -> ChangeKind:
        return KeywordChange.KEYWORD_ARGUMENTS

    def holds(self, reader: SignatureReader, renames: RenameMap) -> bool:
        """
        Every definition the call may reach that takes its positional arguments binds
        each to the parameter of its keyword, and at least one takes them.
        """
        signatures = self.resolution.reachable_signatures(
            renames.original_identifier(self.callee),
            self.enclosing_class and renames.original_identifier(self.enclosing_class),
            reader,
        )
        if None in signatures:
            return False
        keywords = tuple(map(renames.original_identifier, self.keywords))
        taking = [
            signature
            for signature in signatures
            if signature.accepts(self.first_position + len(keywords))
        ]
        return bool(taking) and all(
            signature.binds(self.first_position, keywords) for signature in taking
        )

    def looked_up_names(self, renames: RenameMap) -> frozenset[str]:
        return self.resolution.looked_up_names(renames.original_identifier(self.callee))


@dataclass(frozen=True)
class KeywordOnlyDefinition(Finding):
    """
    A definition whose trailing positional parameters, or whose dataclass fields,
    became keyword-only.
    """

    @classproperty
    def kind(cls) -> ChangeKind:
        return KeywordChange.KEYWORD_ONLY

    def holds(self, reader: SignatureReader, renames: RenameMap) -> bool:
        """
        Always: a call still passing such a parameter positionally fails instead of
        binding it to another parameter.
        """
        return True


@dataclass(frozen=True)
class AddedDecorator(Finding):
    """
    A decorator, referred to by a plain name, added to a definition.
    """

    name: str
    """
    The name the decorator is referred to by.
    """

    @classproperty
    def kind(cls) -> ChangeKind:
        return KeywordChange.IDENTITY_DECORATORS

    def holds(self, reader: SignatureReader, renames: RenameMap) -> bool:
        """
        Every definition of the decorator in the base commit returns what it
        decorates.
        """
        return reader.definitions.is_identity(renames.original_identifier(self.name))

    def looked_up_names(self, renames: RenameMap) -> frozenset[str]:
        return frozenset({renames.original_identifier(self.name)})


# %% rules


@dataclass(frozen=True)
class ArgumentsPassedByKeyword(DifferenceRule):
    """
    Allows a call to pass its trailing positional arguments by keyword, the argument
    expressions kept and evaluated in the same order.
    """

    resolutions: tuple[CalleeResolution, ...] = CALLEE_RESOLUTIONS
    """
    The ways a call may reach its callee, the first recognising it deciding it.
    """

    @classproperty
    def node_types(cls) -> tuple[type[ast.AST], ...]:
        return (ast.Call,)

    def matches(self, base: ast.Call, head: ast.Call, matcher: TreeMatcher) -> bool:
        kept = len(head.args)
        moved = base.args[kept:]
        new_keywords = head.keywords[: len(moved)]
        if not (
            len(new_keywords) == len(moved)
            and matcher.matches(base.func, head.func)
            and matcher.matches(base.args[:kept], head.args)
            and matcher.matches(base.keywords, head.keywords[len(moved) :])
        ):
            return False
        if not moved:
            return True
        callee = PythonSource.referenced_name(head.func)
        if (
            callee is None
            or any(isinstance(argument, ast.Starred) for argument in base.args)
            or any(keyword.arg is None for keyword in new_keywords)
            or not matcher.matches(moved, [keyword.value for keyword in new_keywords])
        ):
            return False
        matcher.record(
            KeywordConversion(
                callee,
                kept,
                tuple(keyword.arg for keyword in new_keywords),
                next(
                    resolution
                    for resolution in self.resolutions
                    if resolution.recognises(head.func)
                ),
                matcher.enclosing_class,
            )
        )
        return True


@dataclass(frozen=True)
class ParametersMadeKeywordOnly(DifferenceRule):
    """
    Allows a definition to make its trailing positional parameters keyword-only,
    keeping their names, annotations and defaults.
    """

    @classproperty
    def node_types(cls) -> tuple[type[ast.AST], ...]:
        return (ast.arguments,)

    def matches(
        self, base: ast.arguments, head: ast.arguments, matcher: TreeMatcher
    ) -> bool:
        kept = len(head.args)
        moved = base.args[kept:]
        positional = [*base.posonlyargs, *base.args]
        defaults = [None] * (len(positional) - len(base.defaults)) + base.defaults
        split = len(base.posonlyargs) + kept
        if moved and base.vararg is not None:
            return False
        if not (
            matcher.matches(base.posonlyargs, head.posonlyargs)
            and matcher.matches(base.args[:kept], head.args)
            and matcher.matches([*moved, *base.kwonlyargs], head.kwonlyargs)
            and matcher.matches(base.vararg, head.vararg)
            and matcher.matches(base.kwarg, head.kwarg)
            and matcher.matches(
                [default for default in defaults[:split] if default is not None],
                head.defaults,
            )
            and matcher.matches(
                [*defaults[split:], *base.kw_defaults], head.kw_defaults
            )
        ):
            return False
        if moved:
            matcher.record(KeywordOnlyDefinition())
        return True


@dataclass(frozen=True)
class DefinitionDecorators(DifferenceRule):
    """
    Allows a definition to add decorators referred to by plain names, and a class's
    dataclass decorator to gain ``kw_only=True``.
    """

    @classproperty
    def node_types(cls) -> tuple[type[ast.AST], ...]:
        return (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

    def matches(
        self,
        base: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
        head: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
        matcher: TreeMatcher,
    ) -> bool:
        is_class = isinstance(base, ast.ClassDef)
        if is_class:
            matcher.enclosing_classes.append(base.name)
        fields_match = matcher.matches_fields(base, head, frozenset({"decorator_list"}))
        if is_class:
            matcher.enclosing_classes.pop()
        return fields_match and self.matches_decorators(base, head, matcher)

    def matches_decorators(
        self,
        base: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
        head: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
        matcher: TreeMatcher,
    ) -> bool:
        """
        :param base: A definition in the base tree.
        :param head: The same definition in the head tree.
        :param matcher: The comparison in progress.
        :return: Whether the head keeps each of the base's decorators in order, but
            for allowed additions and the dataclass decorator gaining ``kw_only``.
        """
        remaining = list(base.decorator_list)
        for decorator in head.decorator_list:
            if remaining and matcher.attempt(remaining[0], decorator):
                remaining.pop(0)
            elif remaining and self.adds_keyword_only(remaining[0], decorator, matcher):
                remaining.pop(0)
                matcher.record(KeywordOnlyDefinition())
            elif isinstance(decorator, (ast.Name, ast.Attribute)):
                matcher.record(AddedDecorator(PythonSource.referenced_name(decorator)))
            else:
                return False
        return not remaining

    @staticmethod
    def adds_keyword_only(base: ast.expr, head: ast.expr, matcher: TreeMatcher) -> bool:
        """
        :param base: A decorator in the base tree.
        :param head: The decorator in its place in the head tree.
        :param matcher: The comparison in progress.
        :return: Whether the head is the base's standard dataclass decorator with
            ``kw_only=True`` added to its options.
        """
        if not (
            isinstance(head, ast.Call)
            and not head.args
            and matcher.head_imports.refers_to(
                head.func, DataclassName.MODULE, DataclassName.DECORATOR
            )
        ):
            return False
        added = [
            keyword
            for keyword in head.keywords
            if keyword.arg == DataclassName.KEYWORD_ONLY
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
        ]
        kept = [keyword for keyword in head.keywords if keyword not in added]
        if len(added) != 1:
            return False
        if not isinstance(base, ast.Call):
            return not kept and matcher.attempt(base, head.func)
        return (
            not base.args
            and matcher.attempt(base.func, head.func)
            and matcher.attempt(base.keywords, kept)
        )


KEYWORD_RULES: tuple[DifferenceRule, ...] = (
    ArgumentsPassedByKeyword(),
    ParametersMadeKeywordOnly(),
    DefinitionDecorators(),
)
"""
The built-in rules of the keyword judgment.
"""


# %% the judgment


@dataclass(frozen=True)
class KeywordArgumentComparison(PythonComparison):
    """
    Compares Python files as :class:`PythonComparison` does, also allowing the
    differences its rules find, once each is proved against the base commit.
    """

    rules: tuple[DifferenceRule, ...] = KEYWORD_RULES
    """
    The differences allowed between the code of both versions.
    """

    decorators: DecoratorPolicy = DecoratorPolicy()
    """
    Which decorated definitions of the base commit are read as written.
    """

    def code_changes(
        self, base: PythonSource, head: PythonSource, context: JudgmentContext
    ) -> ChangeKinds | None:
        """
        :meth:`PythonComparison.code_changes`, also allowing the differences
        :attr:`rules` find once every one of them holds.
        """
        kinds = super().code_changes(base, head, context)
        if kinds is not None:
            return kinds
        matcher = TreeMatcher(self.rules, head.import_bindings)
        if not matcher.matches(
            base.code_tree(context.renames), head.code_tree(RenameMap())
        ):
            return None
        reader = SignatureReader(context.base_definitions, self.decorators)
        renames = context.renames
        reader.definitions.load(
            frozenset().union(
                *(finding.looked_up_names(renames) for finding in matcher.findings)
            )
        )
        if not all(finding.holds(reader, renames) for finding in matcher.findings):
            return None
        found: set[ChangeKind] = {finding.kind for finding in matcher.findings}
        if base.code(renames) != base.code(RenameMap()):
            found.add(MechanicalChange.RENAME)
        return frozenset(found)
