"""
The errors triaging a pull request can end in.
"""

from __future__ import annotations

from dataclasses import dataclass

from basstler.exceptions import DataclassException

# %% errors


@dataclass
class GraphQLMutationRefused(DataclassException):
    """
    Raised when GitHub answers a GraphQL mutation with errors.
    """

    messages: tuple[str, ...]
    """
    Every message GitHub reported.
    """

    def error_message(self) -> str:
        return "GitHub refused the mutation: " + "; ".join(self.messages)

    def suggest_correction(self) -> str:
        return (
            "Run it where GitHub's GraphQL API is reachable, with a credential of the "
            "account the files are marked viewed for: gh auth status"
        )
