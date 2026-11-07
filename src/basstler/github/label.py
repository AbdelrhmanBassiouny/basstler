"""
A label of a repository, as GitHub's labels API lists and creates it.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from pydantic.dataclasses import dataclass

from basstler.upstream_reviews.vocabulary import ValidatedJSONModel

# %% a label


@dataclass(frozen=True)
class RepositoryLabel(ValidatedJSONModel):
    """
    One label, whose fields are named as the labels API names them.
    """

    name: str
    """
    The label's name.
    """

    description: str | None = None
    """
    What the label means, ``None`` when it has no description.
    """

    def to_json(self) -> dict[str, Any]:
        """
        :return: The body the labels API creates the label from.
        """
        return asdict(self)
