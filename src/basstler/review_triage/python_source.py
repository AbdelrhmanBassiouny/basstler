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
from dataclasses import dataclass
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

    def code(self, renames: RenameMap) -> str:
        """
        :param renames: The renames to apply first.
        :return: The file's syntax tree without its imports, other than those of
            ``__future__``, and with every documentation string emptied, dumped as text.
        """
        tree = self.renamed_tree(renames)
        for node in list(ast.walk(tree)):
            for field_name, value in ast.iter_fields(node):
                if isinstance(value, list) and all(
                    isinstance(item, ast.stmt) for item in value
                ):
                    setattr(node, field_name, list(self.code_statements(value)))
        return ast.dump(tree)

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
        bindings: set[ImportBinding] = set()
        for node in ast.walk(self.renamed_tree(renames)):
            if isinstance(node, ast.Import):
                bindings |= {
                    ImportBinding(alias.asname or alias.name.split(".")[0], alias.name)
                    for alias in node.names
                }
            elif isinstance(node, ast.ImportFrom) and node.module != FUTURE_MODULE:
                module = "." * node.level + (node.module or "")
                bindings |= {
                    ImportBinding(alias.asname or alias.name, f"{module}.{alias.name}")
                    for alias in node.names
                }
        return ImportBindings(frozenset(bindings))

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

    @staticmethod
    def is_identifier(token: tokenize.TokenInfo) -> bool:
        """
        :param token: A token of a Python file.
        :return: Whether it is a name that is not a keyword.
        """
        return token.type == tokenize.NAME and not keyword.iskeyword(token.string)
