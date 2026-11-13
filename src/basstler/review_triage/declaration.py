"""
The renames a pull request's description declares or rejects.
"""

from __future__ import annotations

import re

import yaml
from pydantic import Field

from basstler.class_property import classproperty
from basstler.json_model import ValidatedJSONModel
from basstler.review_triage.pull_request import PullRequestChanges
from basstler.review_triage.rename_sources import RenameSource
from basstler.review_triage.renames import Rename, RenameDecisions

# %% the declaration

DECLARATION_MARKER = "review-triage"
"""
The word opening the HTML comment of a description that holds its declarations.
"""


class TriageDeclaration(ValidatedJSONModel):
    """
    What a pull request's description states about its renames, as YAML inside an ``<!--
    review-triage ...

    -->`` comment.
    """

    renames: dict[str, str] = Field(default_factory=dict)
    """
    The new identifier of each old identifier the pull request renames throughout.
    """

    rejected_renames: tuple[str, ...] = ()
    """
    Old identifiers whose detected rename is not a rename.
    """

    @classmethod
    def of_description(cls, description: str) -> TriageDeclaration:
        """
        :param description: A pull request's description.
        :return: Its declarations, none when it holds no declaration comment.
        :raises yaml.YAMLError: If the comment does not hold YAML.
        :raises pydantic.ValidationError: If the YAML does not have the model's shape.
        """
        match = re.search(
            rf"<!--\s*{re.escape(DECLARATION_MARKER)}\s*\n(.*?)-->",
            description,
            re.DOTALL,
        )
        if match is None:
            return cls()
        return cls.from_json(yaml.safe_load(match.group(1)) or {})


# %% the rename source


class DescriptionDeclaration(RenameSource):
    """
    Takes the renames the pull request's description declares and rejects.
    """

    @classproperty
    def label(cls) -> str:
        return "description"

    def decisions(self, changes: PullRequestChanges) -> RenameDecisions:
        declaration = TriageDeclaration.of_description(changes.pull_request.description)
        return RenameDecisions(
            tuple(
                Rename(old, new, self.label) for old, new in declaration.renames.items()
            ),
            frozenset(declaration.rejected_renames),
        )
