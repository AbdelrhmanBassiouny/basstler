"""
The definitions a call may reach: a resolution reads from the call's syntax what it
reaches its callee through, as a target that knows which definitions that may be.
"""

from __future__ import annotations

import ast
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from enum import Enum, auto

from basstler.review_triage.definitions import ClassDefinition, ReceiverName
from basstler.review_triage.renames import RenameMap
from basstler.review_triage.signatures import Signature, SignatureReader

# %% where a call is made


@dataclass(frozen=True)
class CallScope:
    """
    What the code around a call tells about the names it uses.
    """

    enclosing_class: str | None = None
    """
    The name of the innermost class whose body holds the call.
    """

    parameter_types: dict[str, str] = field(default_factory=dict)
    """
    The class each parameter of the innermost enclosing function is annotated with,
    for the parameters the function never assigns to.
    """


# %% targets


class CallTarget(ABC):
    """
    What one call reaches its callee through, and so the definitions it may reach.
    """

    @abstractmethod
    def reachable_signatures(self, reader: SignatureReader) -> list[Signature | None]:
        """
        :param reader: Reads the base commit's signatures.
        :return: The signature of each definition the call may reach, ``None`` for
            one that cannot be read.
        """

    @abstractmethod
    def in_base(self, renames: RenameMap) -> CallTarget:
        """
        :param renames: The renames the pull request makes throughout.
        :return: This target with every name the base commit spells differently.
        """

    def looked_up_names(self) -> frozenset[str]:
        """
        :return: The names whose definitions this target looks up by name, to find
            them together with other calls' in one search.
        """
        return frozenset()


@dataclass(frozen=True)
class NamedTarget(CallTarget):
    """
    A callee known by its name alone: every definition of the name may be reached.
    """

    callee: str
    """
    The last name of the called expression.
    """

    def reachable_signatures(self, reader: SignatureReader) -> list[Signature | None]:
        if self.callee.startswith("__"):
            return []
        definitions = reader.definitions.definitions_of(self.callee)
        return list(map(reader.signature_of, definitions))

    def in_base(self, renames: RenameMap) -> CallTarget:
        return replace(self, callee=renames.original_identifier(self.callee))

    def looked_up_names(self) -> frozenset[str]:
        return frozenset({self.callee})


class ClassReach(Enum):
    """
    Which classes related to the receiver's class may define the method a call reaches.
    """

    HIERARCHY = auto()
    """
    The class, the classes it inherits from and those inheriting from it: the
    receiver is an instance of the class or of a subclass.
    """

    ANCESTORS = auto()
    """
    Only the classes it, or a subclass, inherits from: the receiver is ``super()``.
    """


@dataclass(frozen=True)
class MethodTarget(CallTarget):
    """
    A method of an object of a known class, or of a subclass of it.
    """

    callee: str
    """
    The method's name.
    """

    class_name: str
    """
    The name of the receiver's class.
    """

    reach: ClassReach = ClassReach.HIERARCHY
    """
    Which related classes may define the method reached.
    """

    def reachable_signatures(self, reader: SignatureReader) -> list[Signature | None]:
        index = reader.definitions
        lower = [
            *index.classes_named(self.class_name),
            *index.subclasses_of(self.class_name),
        ]
        upper = index.ancestors_of(lower)
        classes = [*lower, *upper]
        if self.reach is ClassReach.ANCESTORS:
            classes = [definition for definition in upper if definition not in lower]
        return [
            reader.method_signature(definition, self.callee)
            for definition in classes
            if reader.defines(definition, self.callee)
        ]

    def in_base(self, renames: RenameMap) -> CallTarget:
        return replace(
            self,
            callee=renames.original_identifier(self.callee),
            class_name=renames.original_identifier(self.class_name),
        )


@dataclass(frozen=True)
class ClassTarget(CallTarget):
    """
    A class of a known name, or a subclass of it, called to make an instance.
    """

    class_name: str
    """
    The class's name.
    """

    def reachable_signatures(self, reader: SignatureReader) -> list[Signature | None]:
        index = reader.definitions
        classes: list[ClassDefinition] = [
            *index.classes_named(self.class_name),
            *index.subclasses_of(self.class_name),
        ]
        return list(map(reader.signature_of, classes))

    def in_base(self, renames: RenameMap) -> CallTarget:
        return replace(self, class_name=renames.original_identifier(self.class_name))


@dataclass(frozen=True)
class AttributeMethodTarget(CallTarget):
    """
    A method of an attribute of ``self``: of the class the enclosing class declares it
    to hold, or found by name when no class is declared.
    """

    callee: str
    """
    The method's name.
    """

    owner_class: str
    """
    The name of the class whose instance holds the attribute.
    """

    attribute: str
    """
    The attribute's name.
    """

    def reachable_signatures(self, reader: SignatureReader) -> list[Signature | None]:
        declared = reader.attribute_class(self.owner_class, self.attribute)
        if declared is None:
            return NamedTarget(self.callee).reachable_signatures(reader)
        return MethodTarget(self.callee, declared).reachable_signatures(reader)

    def in_base(self, renames: RenameMap) -> CallTarget:
        return replace(
            self,
            callee=renames.original_identifier(self.callee),
            owner_class=renames.original_identifier(self.owner_class),
            attribute=renames.original_identifier(self.attribute),
        )


# %% resolutions


class CalleeResolution(ABC):
    """
    Recognises one way a call reaches its callee.
    """

    @abstractmethod
    def target(self, function: ast.expr, scope: CallScope) -> CallTarget | None:
        """
        :param function: The called expression of a call.
        :param scope: What the code around the call tells.
        :return: What the call reaches its callee through, ``None`` when it does not
            reach it this way.
        """


@dataclass(frozen=True)
class OwnClass(CalleeResolution):
    """
    ``cls(...)``: the enclosing class or one inheriting from it.
    """

    def target(self, function: ast.expr, scope: CallScope) -> CallTarget | None:
        if not (isinstance(function, ast.Name) and function.id == ReceiverName.CLASS):
            return None
        if scope.enclosing_class is None:
            return None
        return ClassTarget(scope.enclosing_class)


@dataclass(frozen=True)
class InstanceMethod(CalleeResolution):
    """
    ``self.method(...)`` or ``cls.method(...)``: a method of the enclosing class's
    hierarchy.
    """

    def target(self, function: ast.expr, scope: CallScope) -> CallTarget | None:
        if not (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Name)
            and function.value.id in (ReceiverName.INSTANCE, ReceiverName.CLASS)
            and scope.enclosing_class is not None
        ):
            return None
        return MethodTarget(function.attr, scope.enclosing_class)


@dataclass(frozen=True)
class ParentMethod(CalleeResolution):
    """
    ``super().method(...)``: a method of a class the enclosing class inherits from.
    """

    def target(self, function: ast.expr, scope: CallScope) -> CallTarget | None:
        if not (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Call)
            and isinstance(function.value.func, ast.Name)
            and function.value.func.id == ReceiverName.PARENT
            and not function.value.args
            and scope.enclosing_class is not None
        ):
            return None
        return MethodTarget(function.attr, scope.enclosing_class, ClassReach.ANCESTORS)


@dataclass(frozen=True)
class AttributeMethod(CalleeResolution):
    """
    ``self.attribute.method(...)``: a method of the class the enclosing class declares
    the attribute to hold.
    """

    def target(self, function: ast.expr, scope: CallScope) -> CallTarget | None:
        if not (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Attribute)
            and isinstance(function.value.value, ast.Name)
            and function.value.value.id == ReceiverName.INSTANCE
            and scope.enclosing_class is not None
        ):
            return None
        return AttributeMethodTarget(
            function.attr, scope.enclosing_class, function.value.attr
        )


@dataclass(frozen=True)
class ParameterMethod(CalleeResolution):
    """
    ``parameter.method(...)``: a method of the class the enclosing function annotates
    the parameter with.
    """

    def target(self, function: ast.expr, scope: CallScope) -> CallTarget | None:
        if not (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Name)
            and function.value.id in scope.parameter_types
        ):
            return None
        return MethodTarget(function.attr, scope.parameter_types[function.value.id])


@dataclass(frozen=True)
class NamedCallee(CalleeResolution):
    """
    Any other call: every definition of the called name may be reached.
    """

    def target(self, function: ast.expr, scope: CallScope) -> CallTarget | None:
        if isinstance(function, ast.Name):
            return NamedTarget(function.id)
        if isinstance(function, ast.Attribute):
            return NamedTarget(function.attr)
        return None


CALLEE_RESOLUTIONS: tuple[CalleeResolution, ...] = (
    OwnClass(),
    InstanceMethod(),
    ParentMethod(),
    AttributeMethod(),
    ParameterMethod(),
    NamedCallee(),
)
"""
The built-in resolutions, the first giving a call a target deciding it.
"""
