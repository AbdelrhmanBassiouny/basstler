"""
A label of a repository, as GitHub's labels API lists and creates it, and the labels
a pull request is given.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from basstler.class_property import classproperty
from basstler.github.client import HttpMethod, RepositoryWrite
from basstler.github.issue import IssueWrite
from basstler.json_model import ValidatedJSONModel

# %% a label


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


@dataclass(frozen=True)
class NewLabel(RepositoryWrite):
    """
    A label to define on the repository.
    """

    label: RepositoryLabel
    """
    The label.
    """

    @classproperty
    def method(cls) -> HttpMethod:
        return HttpMethod.POST

    @property
    def path(self) -> str:
        return self.repository.labels_path

    def to_json(self) -> dict[str, Any]:
        return self.label.to_json()


# %% the labels of a pull request


@dataclass(frozen=True)
class LabelReplacement(IssueWrite):
    """
    The complete set of labels an issue or pull request ends up with.
    """

    labels: list[str]
    """
    The names of the labels.
    """

    @classproperty
    def method(cls) -> HttpMethod:
        return HttpMethod.PUT

    @property
    def path(self) -> str:
        return self.repository.issue_labels_path(self.number)

    def to_json(self) -> dict[str, Any]:
        return {"labels": self.labels}
