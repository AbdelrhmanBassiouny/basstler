"""
The functions, methods and classes a commit defines, read once from each file into
small records holding only what deciding a call's binding needs.
"""

from __future__ import annotations

import ast
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum

from basstler.review_triage.python_source import PythonSource

# %% names the reading recognises


class DataclassName(StrEnum):
    """
    The names of the standard library's dataclass machinery a class definition uses.
    """

    MODULE = "dataclasses"
    """
    The module that provides it.
    """

    DECORATOR = "dataclass"
    """
    The decorator that generates a class's initializer from its fields.
    """

    FIELD = "field"
    """
    The function that configures one field.
    """

    KEYWORD_ONLY = "kw_only"
    """
    The option that makes fields keyword-only.
    """

    INITIALIZED = "init"
    """
    The option that decides whether the initializer takes a field, or is generated.
    """

    KEYWORD_ONLY_MARKER = "KW_ONLY"
    """
    The annotation after which every field is keyword-only.
    """

    CLASS_VARIABLE = "ClassVar"
    """
    The annotation of a class attribute that is not a field.
    """


# %% the records


@dataclass(frozen=True, slots=True)
class FunctionDefinition:
    """
    A function or method, as far as a call's binding depends on it.
    """

    name: str
    """
    The function's name.
    """

    owner: str | None
    """
    The name of the class whose body defines it directly, ``None`` outside a class.
    """

    decorators: tuple[str | None, ...]
    """
    The names its decorators are referred to by, ``None`` for one that is no plain
    reference.
    """

    parameters: tuple[str, ...]
    """
    The names of the parameters an argument can be passed to positionally, in order,
    the instance or class of a method included.
    """

    positional_only: int
    """
    How many of the first parameters can only be passed positionally.
    """

    variadic: bool
    """
    Whether further positional arguments are collected by a ``*`` parameter.
    """

    returns_its_argument: bool
    """
    Whether it is an undecorated function of one parameter that only returns it.
    """


@dataclass(frozen=True, slots=True)
class DataclassField:
    """
    One field a dataclass's generated initializer takes.
    """

    name: str
    """
    The field's name, the initializer's parameter.
    """

    keyword_only: bool
    """
    Whether the parameter can only be passed by keyword.
    """


@dataclass(frozen=True, slots=True)
class ClassDefinition:
    """
    A class, as far as a call of it or of its methods depends on it.
    """

    name: str
    """
    The class's name.
    """

    decorators: tuple[str | None, ...]
    """
    The names its decorators are referred to by, ``None`` for one that is no plain
    reference.
    """

    bases: tuple[str | None, ...]
    """
    The names its base classes are referred to by, ``None`` for one that is no plain
    reference.
    """

    customized: bool
    """
    Whether its definition passes keywords, such as a metaclass, that may change how
    it is called.
    """

    methods: tuple[FunctionDefinition, ...]
    """
    The methods its body defines.
    """

    dataclass_fields: tuple[DataclassField, ...] | None
    """
    The fields its standard dataclass decorator generates the initializer from, in
    order, empty when it is no dataclass and ``None`` when they cannot be read.
    """

    is_dataclass: bool
    """
    Whether the standard dataclass decorator generates its initializer.
    """

    def method(self, name: str) -> FunctionDefinition | None:
        """
        :param name: The name of a method.
        :return: The method of that name the class defines itself, ``None`` when it
            defines none.
        """
        return next((method for method in self.methods if method.name == name), None)


Definition = FunctionDefinition | ClassDefinition
"""
Anything a call may refer to by name.
"""


# %% reading a file


@dataclass(frozen=True)
class DefinitionReader:
    """
    Reads the definitions of one Python file into records.
    """

    source: PythonSource
    """
    The file read.
    """

    def definitions(self) -> Iterator[Definition]:
        """
        :return: Every function, method and class the file defines, at any depth.
        """
        owners = {
            statement: node.name
            for node in ast.walk(self.source.tree)
            if isinstance(node, ast.ClassDef)
            for statement in node.body
        }
        for node in ast.walk(self.source.tree):
            if isinstance(node, ast.ClassDef):
                yield self.class_definition(node)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield self.function_definition(node, owners.get(node))

    @staticmethod
    def function_definition(
        node: ast.FunctionDef | ast.AsyncFunctionDef, owner: str | None
    ) -> FunctionDefinition:
        """
        :param node: A function definition.
        :param owner: The name of the class whose body holds it.
        :return: Its record.
        """
        arguments = node.args
        body = [
            statement
            for statement in node.body
            if not PythonSource.is_documentation(statement)
        ]
        single_parameter = (
            not arguments.posonlyargs
            and len(arguments.args) == 1
            and not arguments.kwonlyargs
            and arguments.vararg is None
            and arguments.kwarg is None
        )
        return FunctionDefinition(
            name=node.name,
            owner=owner,
            decorators=tuple(map(PythonSource.referenced_name, node.decorator_list)),
            parameters=tuple(
                parameter.arg for parameter in (*arguments.posonlyargs, *arguments.args)
            ),
            positional_only=len(arguments.posonlyargs),
            variadic=arguments.vararg is not None,
            returns_its_argument=(
                owner is None
                and not node.decorator_list
                and single_parameter
                and len(body) == 1
                and isinstance(body[0], ast.Return)
                and isinstance(body[0].value, ast.Name)
                and body[0].value.id == arguments.args[0].arg
            ),
        )

    def class_definition(self, node: ast.ClassDef) -> ClassDefinition:
        """
        :param node: A class definition.
        :return: Its record.
        """
        decorator = self.dataclass_decorator(node)
        return ClassDefinition(
            name=node.name,
            decorators=tuple(map(PythonSource.referenced_name, node.decorator_list)),
            bases=tuple(map(PythonSource.referenced_name, node.bases)),
            customized=bool(node.keywords),
            methods=tuple(
                self.function_definition(statement, node.name)
                for statement in node.body
                if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef))
            ),
            dataclass_fields=(
                () if decorator is None else self.dataclass_fields(node, decorator)
            ),
            is_dataclass=decorator is not None,
        )

    def dataclass_decorator(self, node: ast.ClassDef) -> ast.expr | None:
        """
        :param node: A class definition.
        :return: Its standard dataclass decorator, ``None`` when it has none.
        """
        return next(
            (
                decorator
                for decorator in node.decorator_list
                if self.source.import_bindings.refers_to(
                    decorator.func if isinstance(decorator, ast.Call) else decorator,
                    DataclassName.MODULE,
                    DataclassName.DECORATOR,
                )
            ),
            None,
        )

    @staticmethod
    def dataclass_fields(
        node: ast.ClassDef, decorator: ast.expr
    ) -> tuple[DataclassField, ...] | None:
        """
        :param node: A dataclass definition.
        :param decorator: Its dataclass decorator.
        :return: The fields it declares itself, in order, ``None`` when they cannot
            be read.
        """
        options = (
            DefinitionReader.literal_options(decorator)
            if isinstance(decorator, ast.Call)
            else {}
        )
        if options is None:
            return None
        return DefinitionReader.own_fields(node, options)

    @staticmethod
    def literal_options(call: ast.Call) -> dict[str, bool] | None:
        """
        :param call: A call of the dataclass decorator or of its field function.
        :return: The options deciding which fields the initializer takes and how,
            ``None`` when one of them is not a literal boolean.
        """
        options: dict[str, bool] = {}
        for keyword in call.keywords:
            if keyword.arg is None:
                return None
            if keyword.arg not in (
                DataclassName.INITIALIZED,
                DataclassName.KEYWORD_ONLY,
            ):
                continue
            if not isinstance(keyword.value, ast.Constant) or not isinstance(
                keyword.value.value, bool
            ):
                return None
            options[keyword.arg] = keyword.value.value
        return options

    @staticmethod
    def own_fields(
        node: ast.ClassDef, options: dict[str, bool]
    ) -> tuple[DataclassField, ...] | None:
        """
        :param node: A dataclass definition.
        :param options: The options of its decorator.
        :return: The fields it declares itself, in order, ``None`` when it generates
            no initializer or a field cannot be read.
        """
        if not options.get(DataclassName.INITIALIZED, True):
            return None
        keyword_only = options.get(DataclassName.KEYWORD_ONLY, False)
        fields: list[DataclassField] = []
        for statement in node.body:
            if not isinstance(statement, ast.AnnAssign) or not isinstance(
                statement.target, ast.Name
            ):
                continue
            annotation = PythonSource.referenced_name(statement.annotation)
            if annotation == DataclassName.CLASS_VARIABLE:
                continue
            if annotation == DataclassName.KEYWORD_ONLY_MARKER:
                keyword_only = True
                continue
            field_options: dict[str, bool] | None = {}
            if (
                isinstance(statement.value, ast.Call)
                and PythonSource.referenced_name(statement.value.func)
                == DataclassName.FIELD
            ):
                field_options = DefinitionReader.literal_options(statement.value)
            if field_options is None:
                return None
            if field_options.get(DataclassName.INITIALIZED, True):
                fields.append(
                    DataclassField(
                        statement.target.id,
                        field_options.get(DataclassName.KEYWORD_ONLY, keyword_only),
                    )
                )
        return tuple(fields)


# %% where definitions are found


class DefinitionSearch(ABC):
    """
    Finds the Python files of one commit by what they hold, and reads them.
    """

    @abstractmethod
    def files_defining(self, names: frozenset[str]) -> tuple[str, ...]:
        """
        :param names: Names of functions, methods or classes.
        :return: A key for every file defining one of them; files defining none may be
            among them.
        """

    @abstractmethod
    def files_mentioning(self, name: str) -> tuple[str, ...]:
        """
        :param name: A name, such as that of a class.
        :return: A key for every file holding it as a whole word; files not holding it
            may be among them.
        """

    @abstractmethod
    def text_of(self, file: str) -> str:
        """
        :param file: The key of a file this search found.
        :return: Its content.
        """


@dataclass(frozen=True)
class SourceDefinitions(DefinitionSearch):
    """
    Searches a fixed set of Python file contents, each keyed by its position.
    """

    texts: tuple[str, ...] = ()
    """
    The contents searched.
    """

    def files_defining(self, names: frozenset[str]) -> tuple[str, ...]:
        return tuple(map(str, range(len(self.texts))))

    def files_mentioning(self, name: str) -> tuple[str, ...]:
        return tuple(map(str, range(len(self.texts))))

    def text_of(self, file: str) -> str:
        return self.texts[int(file)]


# %% the index


@dataclass
class DefinitionIndex:
    """
    The definitions of one commit by name and by the classes they inherit from, each
    file read once and each search made once.
    """

    search: DefinitionSearch = field(default_factory=SourceDefinitions)
    """
    Where the definitions are found.
    """

    by_file: dict[str, tuple[Definition, ...]] = field(default_factory=dict)
    """
    The definitions of each file read so far, by its key.
    """

    by_name: dict[str, tuple[Definition, ...]] = field(default_factory=dict)
    """
    Every definition of each name looked up so far.
    """

    direct_subclasses: dict[str, tuple[ClassDefinition, ...]] = field(
        default_factory=dict
    )
    """
    The classes naming each class looked up so far among their bases.
    """

    def file_definitions(self, files: tuple[str, ...]) -> Iterator[Definition]:
        """
        :param files: Keys of files the search found.
        :return: Every definition they hold, each file read the first time only.
        """
        for file in files:
            if file not in self.by_file:
                source = PythonSource(self.search.text_of(file))
                self.by_file[file] = tuple(DefinitionReader(source).definitions())
            yield from self.by_file[file]

    def load(self, names: frozenset[str]) -> None:
        """
        Find the definitions of every name not looked up yet, in one search.

        :param names: Names of functions, methods or classes.
        """
        missing = names - self.by_name.keys()
        if not missing:
            return
        found: dict[str, list[Definition]] = {name: [] for name in missing}
        files = self.search.files_defining(frozenset(missing))
        for definition in self.file_definitions(files):
            if definition.name in found:
                found[definition.name].append(definition)
        self.by_name |= {name: tuple(named) for name, named in found.items()}

    def definitions_of(self, name: str) -> tuple[Definition, ...]:
        """
        :param name: The name of a function, method or class.
        :return: Every definition of it.
        """
        self.load(frozenset({name}))
        return self.by_name[name]

    def classes_named(self, name: str) -> tuple[ClassDefinition, ...]:
        """
        :param name: The name of a class.
        :return: Every class definition of it.
        """
        return tuple(
            definition
            for definition in self.definitions_of(name)
            if isinstance(definition, ClassDefinition)
        )

    def is_identity(self, name: str) -> bool:
        """
        :param name: The name a decorator is referred to by.
        :return: Whether every definition of it is a plain function returning its only
            argument, at least one being found.
        """
        definitions = self.definitions_of(name)
        return bool(definitions) and all(
            isinstance(definition, FunctionDefinition)
            and definition.returns_its_argument
            for definition in definitions
        )

    # %%% the class hierarchy

    def subclasses_of(self, name: str) -> list[ClassDefinition]:
        """
        :param name: The name of a class.
        :return: Every class inheriting from a class of that name, at any depth.
        """
        found: list[ClassDefinition] = []
        visited = {name}
        pending = [name]
        while pending:
            current = pending.pop()
            if current not in self.direct_subclasses:
                files = self.search.files_mentioning(current)
                self.direct_subclasses[current] = tuple(
                    definition
                    for definition in self.file_definitions(files)
                    if isinstance(definition, ClassDefinition)
                    and current in definition.bases
                )
            for subclass in self.direct_subclasses[current]:
                found.append(subclass)
                if subclass.name not in visited:
                    visited.add(subclass.name)
                    pending.append(subclass.name)
        return found

    def ancestors_of(self, classes: list[ClassDefinition]) -> list[ClassDefinition]:
        """
        :param classes: Class definitions.
        :return: Every class of the commit they inherit from, at any depth.
        """
        found: list[ClassDefinition] = []
        visited: set[str] = set()
        pending = [base for definition in classes for base in definition.bases if base]
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            for definition in self.classes_named(current):
                found.append(definition)
                pending.extend(base for base in definition.bases if base)
        return found
