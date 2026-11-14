"""
The definitions a call may reach, decided by what the call reaches its callee through.
"""

from __future__ import annotations

import ast
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from basstler.review_triage.definitions import ClassDefinition
from basstler.review_triage.signatures import Signature, SignatureReader

# %% the conventional receiver names


class ReceiverName(StrEnum):
    """
    The names a method's code conventionally refers to what it is called on by.
    """

    INSTANCE = "self"
    """
    The instance an instance method is called on.
    """

    CLASS = "cls"
    """
    The class a class method is called on.
    """

    PARENT = "super"
    """
    The function giving access to the methods a class inherits.
    """


# %% resolutions


class CalleeResolution(ABC):
    """
    One way a call reaches its callee, and the definitions it may reach that way.
    """

    @abstractmethod
    def recognises(self, function: ast.expr) -> bool:
        """
        :param function: The called expression of a call.
        :return: Whether the call reaches its callee this way.
        """

    @abstractmethod
    def reachable_signatures(
        self, callee: str, enclosing_class: str | None, reader: SignatureReader
    ) -> list[Signature | None]:
        """
        :param callee: The last name of the called expression.
        :param enclosing_class: The name of the class whose body holds the call.
        :param reader: Reads the base commit's signatures.
        :return: The signature of each definition the call may reach, ``None`` for
            one that cannot be read.
        """

    def looked_up_names(self, callee: str) -> frozenset[str]:
        """
        :param callee: The last name of the called expression.
        :return: The names whose definitions this resolution looks up, to find them
            together with other calls' in one search.
        """
        return frozenset()


@dataclass(frozen=True)
class NamedCallee(CalleeResolution):
    """
    A name, or an attribute of an object of unknown class: every definition of the
    name may be reached.
    """

    def recognises(self, function: ast.expr) -> bool:
        return True

    def reachable_signatures(
        self, callee: str, enclosing_class: str | None, reader: SignatureReader
    ) -> list[Signature | None]:
        if callee.startswith("__"):
            return []
        return list(map(reader.signature_of, reader.definitions.definitions_of(callee)))

    def looked_up_names(self, callee: str) -> frozenset[str]:
        return frozenset({callee})


class HierarchyResolution(CalleeResolution, ABC):
    """
    A call reaching its callee through the class whose body holds it, so only the
    classes related to that one by inheritance may define what it reaches.
    """

    @abstractmethod
    def reachable_classes(
        self, lower: list[ClassDefinition], upper: list[ClassDefinition]
    ) -> list[ClassDefinition]:
        """
        :param lower: The enclosing class and every class inheriting from it.
        :param upper: Every class those inherit from.
        :return: The classes whose definitions the call may reach.
        """

    def reachable_signatures(
        self, callee: str, enclosing_class: str | None, reader: SignatureReader
    ) -> list[Signature | None]:
        if enclosing_class is None:
            return []
        index = reader.definitions
        lower = [
            *index.classes_named(enclosing_class),
            *index.subclasses_of(enclosing_class),
        ]
        return [
            reader.method_signature(definition, callee)
            for definition in self.reachable_classes(lower, index.ancestors_of(lower))
            if reader.defines(definition, callee)
        ]


@dataclass(frozen=True)
class InstanceMethod(HierarchyResolution):
    """
    An attribute of ``self`` or ``cls``: a method of the enclosing class, of a class
    it inherits from or of one inheriting from it.
    """

    def recognises(self, function: ast.expr) -> bool:
        return (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Name)
            and function.value.id in (ReceiverName.INSTANCE, ReceiverName.CLASS)
        )

    def reachable_classes(
        self, lower: list[ClassDefinition], upper: list[ClassDefinition]
    ) -> list[ClassDefinition]:
        return [*lower, *upper]


@dataclass(frozen=True)
class ParentMethod(HierarchyResolution):
    """
    An attribute of ``super()``: a method of a class the enclosing class, or one
    inheriting from it, inherits from.
    """

    def recognises(self, function: ast.expr) -> bool:
        return (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Call)
            and isinstance(function.value.func, ast.Name)
            and function.value.func.id == ReceiverName.PARENT
            and not function.value.args
        )

    def reachable_classes(
        self, lower: list[ClassDefinition], upper: list[ClassDefinition]
    ) -> list[ClassDefinition]:
        return [definition for definition in upper if definition not in lower]


@dataclass(frozen=True)
class OwnClass(CalleeResolution):
    """
    ``cls`` itself: the enclosing class or one inheriting from it.
    """

    def recognises(self, function: ast.expr) -> bool:
        return isinstance(function, ast.Name) and function.id == ReceiverName.CLASS

    def reachable_signatures(
        self, callee: str, enclosing_class: str | None, reader: SignatureReader
    ) -> list[Signature | None]:
        if enclosing_class is None:
            return []
        index = reader.definitions
        classes = [
            *index.classes_named(enclosing_class),
            *index.subclasses_of(enclosing_class),
        ]
        return list(map(reader.signature_of, classes))


CALLEE_RESOLUTIONS: tuple[CalleeResolution, ...] = (
    OwnClass(),
    InstanceMethod(),
    ParentMethod(),
    NamedCallee(),
)
"""
The built-in resolutions, the first recognising a call deciding it.
"""
