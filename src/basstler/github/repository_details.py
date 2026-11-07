"""
What GitHub's repository resource says about a repository.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic.dataclasses import dataclass

from basstler.upstream_reviews.vocabulary import ValidatedJSONModel

# %% the repository resource


@dataclass(frozen=True)
class RepositoryDetails(ValidatedJSONModel):
    """
    One repository, as its REST resource describes it.
    """

    default_branch: str
    """
    The branch pull requests target unless told otherwise.
    """

    is_fork: Annotated[bool, Field(alias="fork")]
    """
    Whether it is a fork, whose default branch follows its upstream's.
    """
