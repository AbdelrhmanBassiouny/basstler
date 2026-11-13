"""
Marking a pull request's mechanical files viewed for the account whose credential the
GraphQL client uses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from pydantic import Field

from basstler.json_model import ValidatedJSONModel
from basstler.locations import ReviewTriageLocation
from basstler.review_triage.triage import PullRequestTriage
from basstler.upstream_reviews.clients import GraphQLClient

# %% the mutation


class ViewedFile(ValidatedJSONModel):
    """
    The variables of the mutation marking one file of a pull request viewed.
    """

    pull_request_node_identifier: Annotated[str, Field(alias="pullRequestId")]
    """
    What GitHub's GraphQL API identifies the pull request by.
    """

    path: str
    """
    The file's path in the pull request's head commit.
    """


@dataclass(frozen=True)
class ViewedMarking:
    """
    Marks files viewed through GitHub's GraphQL API.
    """

    client: GraphQLClient
    """
    The client whose account the files are marked viewed for.
    """

    def mark_mechanical_files(self, triage: PullRequestTriage) -> None:
        """
        Mark every mechanical file of *triage* viewed.

        :param triage: The triaged pull request.
        """
        mutation = ReviewTriageLocation.MARK_FILE_AS_VIEWED.read_text()
        for file in triage.mechanical_files:
            self.client.execute(
                mutation,
                ViewedFile(
                    triage.pull_request.node_identifier, str(file.change.path)
                ).to_json(),
            )
