"""
The parts of a Python file a change to it is judged by: its code, the names its imports
bind, its documentation strings and its comments.
"""

from __future__ import annotations

import ast
import copy
import io
import keyword
import tokenize
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import cached_property

from basstler.review_triage.renames import RenameMap

# %% names in the syntax tree

IDENTIFIER_FIELDS = frozenset(
    {"id", "attr", "name", "arg", "asname", "module", "names", "rest", "kwd_attrs"}
)
"""
The fields of a syntax tree node that hold an identifier, or a list of them, wherever
the node type has such a field.
"""

FUTURE_MODULE = "__future__"
"""
The module whose imports change how the rest of the file is compiled.
"""


class IdentifierRenamer(ast.NodeVisitor):
    """
    Replaces, in place, every identifier of a syntax tree that a rename map renames.
    """

    def __init__(self, renames: RenameMap) -> None:
        """
        :param renames: The renames to apply.
        """
        self.renames = renames

    def generic_visit(self, node: ast.AST) -> None:
        """
        Rename the identifiers *node* holds, then visit its children.

        :param node: The node visited.
        """
        for field_name, value in ast.iter_fields(node):
            if field_name not in IDENTIFIER_FIELDS:
                continue
            if isinstance(value, str):
                setattr(node, field_name, self.renames.renamed_identifier(value))
            elif isinstance(value, list) and all(isinstance(v, str) for v in value):
                setattr(
                    node,
                    field_name,
                    [self.renames.renamed_identifier(item) for item in value],
                )
        super().generic_visit(node)


# %% one import binding


@dataclass(frozen=True)
class ImportBinding:
    """
    A name an import statement binds, and what it binds it to.
    """

    bound_name: str
    """
    The name the rest of the file refers to.
    """

    source: str
    """
    The dotted path of the module or module member the name is bound to.
    """


@dataclass(frozen=True)
class ImportBindings:
    """
    Every name a file's import statements bind.
    """

    bindings: frozenset[ImportBinding]
    """
    The bindings, wherever in the file their import statement is.
    """

    def sources_of(self, bound_name: str) -> frozenset[str]:
        """
        :param bound_name: A name the imports may bind.
        :return: Everything the imports bind it to.
        """
        return frozenset(
            binding.source
            for binding in self.bindings
            if binding.bound_name == bound_name
        )

    def refers_to(self, expression: ast.expr, module: str, member: str) -> bool:
        """
        :param expression: A name or an attribute in the file.
        :param module: The module defining the member.
        :param member: The member's name in it.
        :return: Whether the expression refers to that member through these bindings.
        """
        if isinstance(expression, ast.Name):
            return self.sources_of(expression.id) == {f"{module}.{member}"}
        return (
            isinstance(expression, ast.Attribute)
            and expression.attr == member
            and isinstance(expression.value, ast.Name)
            and self.sources_of(expression.value.id) == {module}
        )

    def agrees_with(self, other: ImportBindings) -> bool:
        """
        :param other: The bindings of another version of the file.
        :return: Whether every name both bind is bound to the same sources by both.
        """
        bound_names = {binding.bound_name for binding in self.bindings}
        return all(
            self.sources_of(binding.bound_name) == other.sources_of(binding.bound_name)
            for binding in other.bindings
            if binding.bound_name in bound_names
        )


# %% the file's parts


@dataclass(frozen=True)
class PythonSource:
    """
    One version of a Python file, split into the parts a change to it is judged by.
    """

    text: str
    """
    The file's content.
    """

    code_trees: dict[RenameMap, ast.Module] = field(
        default_factory=dict, compare=False, repr=False
    )
    """
    :meth:`code_tree` under each renames asked for so far.
    """

    @cached_property
    def tree(self) -> ast.Module:
        """
        The file's syntax tree.

        :raises SyntaxError: If the file is not valid Python.
        """
        return ast.parse(self.text)

    def renamed_tree(self, renames: RenameMap) -> ast.Module:
        """
        :param renames: The renames to apply.
        :return: A copy of :attr:`tree` with every identifier the renames rename
            replaced.
        """
        tree = copy.deepcopy(self.tree)
        IdentifierRenamer(renames).visit(tree)
        return tree

    def code_tree(self, renames: RenameMap) -> ast.Module:
        """
        :param renames: The renames to apply first.
        :return: The file's syntax tree without its imports, other than those of
            ``__future__``, and with every documentation string emptied; not to be
            modified, as it is kept for the next call.
        """
        if renames in self.code_trees:
            return self.code_trees[renames]
        tree = self.renamed_tree(renames)
        for node in list(ast.walk(tree)):
            for field_name, value in ast.iter_fields(node):
                if isinstance(value, list) and all(
                    isinstance(item, ast.stmt) for item in value
                ):
                    setattr(node, field_name, list(self.code_statements(value)))
        self.code_trees[renames] = tree
        return tree

    def code(self, renames: RenameMap) -> str:
        """
        :param renames: The renames to apply first.
        :return: :meth:`code_tree`, dumped as text.
        """
        return ast.dump(self.code_tree(renames))

    @staticmethod
    def code_statements(statements: list[ast.stmt]) -> Iterator[ast.stmt]:
        """
        :param statements: A block of statements.
        :return: Its statements other than imports, each documentation string emptied.
        """
        for statement in statements:
            if isinstance(statement, ast.Import) or (
                isinstance(statement, ast.ImportFrom)
                and statement.module != FUTURE_MODULE
            ):
                continue
            if PythonSource.is_documentation(statement):
                yield ast.Expr(ast.Constant(""))
                continue
            yield statement

    @staticmethod
    def is_documentation(statement: ast.stmt) -> bool:
        """
        :param statement: A statement.
        :return: Whether it is a bare string, which documents what precedes or holds it.
        """
        return (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        )

    def imports(self, renames: RenameMap) -> ImportBindings:
        """
        :param renames: The renames to apply first.
        :return: The names the file's imports bind, other than those of ``__future__``.
        """
        renamed = renames.renamed_identifier
        bindings: set[ImportBinding] = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                bindings |= {
                    ImportBinding(
                        renamed(alias.asname or alias.name.split(".")[0]),
                        renamed(alias.name),
                    )
                    for alias in node.names
                }
            elif isinstance(node, ast.ImportFrom) and node.module != FUTURE_MODULE:
                module = "." * node.level + renamed(node.module or "")
                bindings |= {
                    ImportBinding(
                        renamed(alias.asname or alias.name),
                        f"{module}.{renamed(alias.name)}",
                    )
                    for alias in node.names
                }
        return ImportBindings(frozenset(bindings))

    @cached_property
    def import_bindings(self) -> ImportBindings:
        """
        The names the file's imports bind, as the file spells them.
        """
        return self.imports(RenameMap())

    @cached_property
    def import_statements(self) -> str:
        """
        The file's import statements, other than those of ``__future__``, dumped as text
        in the order they occur.
        """
        return "\n".join(
            ast.dump(node)
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Import)
            or (isinstance(node, ast.ImportFrom) and node.module != FUTURE_MODULE)
        )

    @cached_property
    def documentation(self) -> tuple[str, ...]:
        """
        The file's documentation strings, in the order they occur.
        """
        return tuple(
            node.value.value
            for node in ast.walk(self.tree)
            if isinstance(node, ast.stmt) and self.is_documentation(node)
        )

    @cached_property
    def comments(self) -> str:
        """
        The text of the file's comments, one per line, in the order they occur.
        """
        return "\n".join(
            token.string.removeprefix("#")
            for token in tokenize.generate_tokens(io.StringIO(self.text).readline)
            if token.type == tokenize.COMMENT
        )

    @cached_property
    def significant_tokens(self) -> tuple[tokenize.TokenInfo, ...]:
        """
        The file's tokens that carry meaning - names, operators, numbers and strings -
        in order.
        """
        return tuple(
            token
            for token in tokenize.generate_tokens(io.StringIO(self.text).readline)
            if token.type
            in (tokenize.NAME, tokenize.OP, tokenize.NUMBER, tokenize.STRING)
        )

    def tokens_on_lines(self, first: int, end: int) -> tuple[tokenize.TokenInfo, ...]:
        """
        :param first: The number of the first line, counted from one.
        :param end: The number of the line after the last.
        :return: The :attr:`significant_tokens` starting on those lines.
        """
        return tuple(
            token for token in self.significant_tokens if first <= token.start[0] < end
        )

    @staticmethod
    def referenced_name(expression: ast.expr) -> str | None:
        """
        :param expression: An expression naming something, such as a decorator, a base
            class or an annotation.
        :return: The last name it refers to, ignoring subscripts and calls, ``None``
            when it is no reference.
        """
        if isinstance(expression, ast.Name):
            return expression.id
        if isinstance(expression, ast.Attribute):
            return expression.attr
        if isinstance(expression, ast.Subscript):
            return PythonSource.referenced_name(expression.value)
        if isinstance(expression, ast.Call):
            return PythonSource.referenced_name(expression.func)
        if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
            return expression.value.split("[")[0].split(".")[-1].strip()
        return None

    @staticmethod
    def is_identifier(token: tokenize.TokenInfo) -> bool:
        """
        :param token: A token of a Python file.
        :return: Whether it is a name that is not a keyword.
        """
        return token.type == tokenize.NAME and not keyword.iskeyword(token.string)
