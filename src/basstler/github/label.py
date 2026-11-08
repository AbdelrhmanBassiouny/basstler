"""
A label of a repository, as GitHub's labels API lists and creates it, and the labels
a pull request is given.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


from basstler.github.client import RequestBody
from basstler.upstream_reviews.vocabulary import ValidatedJSONModel

# %% a label


class RepositoryLabel(ValidatedJSONModel, RequestBody):
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


# %% the labels of a pull request


@dataclass(frozen=True)
class LabelReplacement(RequestBody):
    """
    The complete set of labels an issue or pull request ends up with.
    """

    labels: list[str]
    """
    The names of the labels.
    """

    def to_json(self) -> dict[str, Any]:
        return asdict(self)
