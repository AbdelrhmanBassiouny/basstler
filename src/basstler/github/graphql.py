"""
The shapes GitHub's GraphQL API returns lists in.
"""

from __future__ import annotations

from typing import Annotated, Any, TypeVar

from basstler.json_model import RawValueReader

# %% connections


class GraphQLNodes(RawValueReader):
    """
    Reads a GraphQL connection, which holds a list-valued field's entries under
    ``nodes``, as those entries.
    """

    def read(self, value: dict[str, Any] | list[Any]) -> list[Any]:
        if isinstance(value, list):
            return value
        return value["nodes"]


Node = TypeVar("Node")
"""
Whatever model the entries of a connection are parsed into.
"""

GraphQLConnection = Annotated[list[Node], GraphQLNodes()]
"""
A list-valued GraphQL field, which GitHub returns as a connection.
"""
