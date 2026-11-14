"""
The parameters a call may pass positionally to a function, method or class, read from
its definition and the definitions it inherits from.
"""

from __future__ import annotations

import builtins
from dataclasses import dataclass

from basstler.review_triage.definitions import (
    ClassDefinition,
    DataclassField,
    Definition,
    DefinitionIndex,
    FunctionDefinition,
)

# %% names the reading recognises

INITIALIZER = "__init__"
"""
The method a call of a class passes its arguments to.
"""

STATIC_METHOD = "staticmethod"
"""
The decorator of a method that takes no instance or class as first parameter.
"""

ARGUMENTLESS_BASES = frozenset({"object", "ABC", "Generic", "Protocol"})
"""
Base classes that add neither fields nor initializer parameters.
"""

BUILTIN_CLASSES = frozenset(
    name for name, value in vars(builtins).items() if isinstance(value, type)
)
"""
The classes Python provides without an import, none of them a dataclass.
"""

SIGNATURE_PRESERVING_DECORATORS = frozenset(
    {
        "abstractmethod",
        "cache",
        "classmethod",
        "dataclass",
        "final",
        "lru_cache",
        "override",
        STATIC_METHOD,
        "total_ordering",
    }
)
"""
The decorators known to leave the parameters of what they decorate as written.
"""

# %% one signature


@dataclass(frozen=True, slots=True)
class Signature:
    """
    The parameters a call may pass positionally, in order.
    """

    parameters: tuple[str, ...]
    """
    Their names, after the instance or class a method is bound to.
    """

    positional_only: int = 0
    """
    How many of the first ones can only be passed positionally.
    """

    variadic: bool = False
    """
    Whether further positional arguments are collected, by a ``*`` parameter.
    """

    def accepts(self, argument_count: int) -> bool:
        """
        :param argument_count: How many arguments a call passes positionally.
        :return: Whether a parameter takes each of them.
        """
        return self.variadic or argument_count <= len(self.parameters)

    def binds(self, first_position: int, keywords: tuple[str, ...]) -> bool:
        """
        :param first_position: The position of the first argument passed by keyword.
        :param keywords: The keywords of the arguments from that position on.
        :return: Whether those are the names of the parameters at those positions.
        """
        return (
            first_position >= self.positional_only
            and self.parameters[first_position : first_position + len(keywords)]
            == keywords
        )


# %% which definitions can be read


@dataclass(frozen=True)
class DecoratorPolicy:
    """
    Decides which decorated definitions are read as written.
    """

    signature_preserving: frozenset[str] = SIGNATURE_PRESERVING_DECORATORS
    """
    The names of the decorators known to keep what they decorate callable as written.
    """

    def reads(self, definition: Definition) -> bool:
        """
        :param definition: A function, method or class.
        :return: Whether every decorator it carries keeps its parameters as written.
        """
        return all(
            decorator in self.signature_preserving
            for decorator in definition.decorators
        )


# %% reading signatures


@dataclass(frozen=True)
class SignatureReader:
    """
    Reads the signature of calling a definition, through the classes it inherits from.
    """

    definitions: DefinitionIndex
    """
    The commit's definitions, inherited ones looked up in.
    """

    decorators: DecoratorPolicy = DecoratorPolicy()
    """
    Which decorated definitions are read as written.
    """

    def signature_of(self, definition: Definition) -> Signature | None:
        """
        :param definition: A function, method or class.
        :return: The signature of calling it, ``None`` when it cannot be read.
        """
        if not self.decorators.reads(definition):
            return None
        if isinstance(definition, ClassDefinition):
            return self.class_signature(definition)
        return self.function_signature(definition)

    @staticmethod
    def function_signature(definition: FunctionDefinition) -> Signature | None:
        """
        :param definition: A function or method.
        :return: Its signature, without the instance or class a method is bound to.
        """
        if definition.owner is None or STATIC_METHOD in definition.decorators:
            return Signature(
                definition.parameters, definition.positional_only, definition.variadic
            )
        if not definition.parameters:
            return None
        return Signature(
            definition.parameters[1:],
            max(definition.positional_only - 1, 0),
            definition.variadic,
        )

    def class_signature(self, definition: ClassDefinition) -> Signature | None:
        """
        :param definition: A class.
        :return: The signature of calling it, ``None`` when it cannot be read.
        """
        initializer = definition.method(INITIALIZER)
        if initializer is not None:
            return self.signature_of(initializer)
        if definition.customized:
            return None
        if definition.is_dataclass:
            fields = self.fields_of(definition, frozenset())
            if fields is None:
                return None
            return Signature(
                tuple(field.name for field in fields if not field.keyword_only)
            )
        bases = self.relevant_bases(definition)
        if bases is None or len(bases) > 1:
            return None
        if not bases:
            return Signature(())
        return self.agreed_signature(bases[0])

    def agreed_signature(self, name: str) -> Signature | None:
        """
        :param name: The name of a function, method or class.
        :return: The signature every definition of it has, ``None`` when there is
            none, when they disagree or when one cannot be read.
        """
        signatures = set(map(self.signature_of, self.definitions.definitions_of(name)))
        if len(signatures) != 1:
            return None
        return signatures.pop()

    def method_signature(
        self, definition: ClassDefinition, name: str
    ) -> Signature | None:
        """
        :param definition: A class defining a method of that name, or a dataclass
            generating its initializer.
        :param name: The method's name.
        :return: The method's signature.
        """
        method = definition.method(name)
        if method is None:
            return self.class_signature(definition)
        return self.signature_of(method)

    def attribute_class(self, class_name: str, attribute: str) -> str | None:
        """
        :param class_name: The name of a class.
        :param attribute: The name of an attribute of its instances.
        :return: The class every declaration of the attribute in the class and its
            ancestors allows, ``None`` when there is none or they disagree.
        """
        classes = list(self.definitions.classes_named(class_name))
        declared = {
            declaration.class_name
            for definition in [*classes, *self.definitions.ancestors_of(classes)]
            for declaration in definition.attribute_types
            if declaration.name == attribute
        }
        if len(declared) != 1:
            return None
        return declared.pop()

    @staticmethod
    def defines(definition: ClassDefinition, name: str) -> bool:
        """
        :param definition: A class.
        :param name: The name of a method.
        :return: Whether the class defines the method, or generates it as a dataclass's
            initializer.
        """
        return definition.method(name) is not None or (
            name == INITIALIZER and definition.is_dataclass
        )

    # %%% dataclass fields

    def fields_of(
        self, definition: ClassDefinition, visited: frozenset[str]
    ) -> tuple[DataclassField, ...] | None:
        """
        :param definition: A class.
        :param visited: The classes whose fields are being read, to stop at a cycle.
        :return: The fields a dataclass initializer generated for it takes, inherited
            ones first, ``None`` when they cannot be read.
        """
        bases = self.relevant_bases(definition)
        if bases is None or definition.dataclass_fields is None:
            return None
        fields: dict[str, DataclassField] = {}
        for base in reversed(bases):
            inherited = self.inherited_fields(base, visited | {definition.name})
            if inherited is None:
                return None
            fields |= {field.name: field for field in inherited}
        fields |= {field.name: field for field in definition.dataclass_fields}
        return tuple(fields.values())

    def inherited_fields(
        self, name: str, visited: frozenset[str]
    ) -> tuple[DataclassField, ...] | None:
        """
        :param name: The name of a base class.
        :param visited: The classes whose fields are being read.
        :return: The fields every class of that name agrees on, ``None`` when they
            disagree or cannot be read.
        """
        if name in visited:
            return None
        definitions = self.definitions.definitions_of(name)
        if not definitions and name in BUILTIN_CLASSES:
            return ()
        if not definitions or not all(
            isinstance(definition, ClassDefinition)
            and self.decorators.reads(definition)
            for definition in definitions
        ):
            return None
        fields = {self.fields_of(definition, visited) for definition in definitions}
        if len(fields) != 1:
            return None
        return fields.pop()

    @staticmethod
    def relevant_bases(definition: ClassDefinition) -> tuple[str, ...] | None:
        """
        :param definition: A class.
        :return: The names of its base classes that may add fields or parameters,
            ``None`` when one is not a plain reference.
        """
        if None in definition.bases:
            return None
        return tuple(
            base for base in definition.bases if base not in ARGUMENTLESS_BASES
        )
