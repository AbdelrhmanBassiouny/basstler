"""
The vocabulary of GitHub's pull request endpoints.
"""

from __future__ import annotations

from enum import StrEnum

# %% opening a pull request


class NewPullRequestField(StrEnum):
    """
    The fields GitHub's create-pull-request endpoint reads from its JSON body.
    """

    TITLE = "title"
    """
    The pull request's title.
    """

    BODY = "body"
    """
    The pull request's description.
    """

    HEAD = "head"
    """
    The branch carrying the changes.
    """

    BASE = "base"
    """
    The branch to merge into.
    """

    DRAFT = "draft"
    """
    Whether it opens as a draft.
    """
