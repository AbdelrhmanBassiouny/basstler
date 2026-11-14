"""
Where a triage goes once it is made: the interface every output implements, and the
built-in outputs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Annotated, Any

from pydantic import Field

from basstler.class_property import classproperty
from basstler.github.client import GitHubWrite, GitHubWriter, HttpMethod
from basstler.json_model import ValidatedJSONModel
from basstler.locations import ReviewTriageLocation
from basstler.render_common import TemplatePage
from basstler.review_triage.declaration import DECLARATION_MARKER
from basstler.review_triage.exceptions import GraphQLMutationRefused
from basstler.review_triage.triage import PullRequestTriage
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which the Markdown report prints through.
"""

# %% the interface


class TriageOutput(ABC):
    """
    Delivers a triage somewhere.
    """

    @abstractmethod
    def publish(self, triage: PullRequestTriage) -> None:
        """
        :param triage: The triaged pull request.
        """


# %% the Markdown report


class MarkdownReport(TriageOutput, TemplatePage):
    """
    Prints the triage as a Markdown report to standard output.
    """

    @classproperty
    def template(cls) -> str:
        return ReviewTriageLocation.REPORT_TEMPLATE.name

    def render(self, triage: PullRequestTriage) -> str:
        """
        :param triage: The triaged pull request.
        :return: The report.
        """
        return self.render_template(triage=triage, marker=DECLARATION_MARKER)

    def publish(self, triage: PullRequestTriage) -> None:
        logger.info(self.render(triage))


# %% marking files viewed

GRAPHQL_PATH = "graphql"
"""
The path, below the API root, of GitHub's GraphQL endpoint.
"""


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


class GraphQLMutation(GitHubWrite):
    """
    One GraphQL mutation, sent to GitHub's GraphQL endpoint.
    """

    query: str
    """
    The mutation's document.
    """

    variables: dict[str, Any]
    """
    The document's variables.
    """

    @classproperty
    def method(cls) -> HttpMethod:
        return HttpMethod.POST

    @property
    def path(self) -> str:
        return GRAPHQL_PATH


class GraphQLError(ValidatedJSONModel):
    """
    One error GitHub reports for a GraphQL request.
    """

    message: str
    """
    What went wrong.
    """


class GraphQLAnswer(ValidatedJSONModel):
    """
    GitHub's answer to a GraphQL request, read only for its errors.
    """

    errors: tuple[GraphQLError, ...] = ()
    """
    The errors reported, none when the request succeeded.
    """


@dataclass(frozen=True)
class ViewedMarking(TriageOutput):
    """
    Marks every mechanical file viewed for the account whose credential the writer
    sends, raising :class:`GraphQLMutationRefused` when GitHub refuses one or the
    call.
    """

    github: GitHubWriter
    """
    The writer the mutations are sent through.
    """

    def publish(self, triage: PullRequestTriage) -> None:
        refusals = self.refusals(triage)
        if refusals:
            raise GraphQLMutationRefused(refusals)

    def refusals(self, triage: PullRequestTriage) -> tuple[str, ...]:
        """
        Mark the mechanical files viewed, stopping at the first refusal.

        :param triage: The triaged pull request.
        :return: What GitHub refused with, empty once every file is marked.
        """
        document = ReviewTriageLocation.MARK_FILE_AS_VIEWED.read_text()
        for file in triage.mechanical_files:
            variables = ViewedFile(
                triage.pull_request.node_identifier, str(file.change.path)
            )
            response = self.github.attempt_send(
                GraphQLMutation(document, variables.to_json())
            )
            if response.failure is not None:
                return (response.failure.error_message(),)
            answer = GraphQLAnswer.from_json(response.body)
            if answer.errors:
                return tuple(error.message for error in answer.errors)
        return ()
