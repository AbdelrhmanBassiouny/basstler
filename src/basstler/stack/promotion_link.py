"""
The one-click link that opens a fork branch's pull request on the upstream.
"""

from __future__ import annotations

from dataclasses import dataclass

from basstler.class_property import classproperty
from basstler.github.pull_request_form import (
    PrefilledPullRequestLink,
    PullRequestForm,
)
from basstler.locations import ProjectLocation
from basstler.stack.configuration import (
    CommittedStackConfiguration,
    MissingUpstreamRepositoryError,
)
from basstler.stack.exceptions import PromotionLinkTooLongError
from basstler.stack.settings import Configuration
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% promotion links


@dataclass(frozen=True)
class PromotionLink(PrefilledPullRequestLink):
    """
    A one-click compare-and-create link opening a fork branch's pull request upstream.
    """

    @classproperty
    def url_character_limit(cls) -> int:
        """
        Longest URL to build, as :attr:`PullRequestForm.url_character_limit`.
        """
        return PullRequestForm.url_character_limit

    @classproperty
    def truncation_marker(cls) -> str:
        """
        Appended to a shortened body, as :attr:`PullRequestForm.truncation_marker`.
        """
        return PullRequestForm.truncation_marker

    @classmethod
    def build(
        cls, configuration: Configuration, branch: str, title: str, body: str
    ) -> PromotionLink:
        """
        Build the link promoting a fork branch to the upstream base.

        :param configuration: The resolved configuration naming both repositories.
        :param branch: The fork branch to promote.
        :param title: Title to prefill.
        :param body: Description to prefill, shortened if the URL would not otherwise
            fit.
        :return: The link, flagged if the body was shortened.
        :raises MissingUpstreamRepositoryError: If the project names no upstream.
        :raises PromotionLinkTooLongError: If even the title does not fit.
        """
        upstream_repository = configuration.upstream_repository
        if upstream_repository is None:
            raise MissingUpstreamRepositoryError(
                CommittedStackConfiguration().project_file,
                ProjectLocation.PERSONAL_STACK_CONFIGURATION.value,
            )
        form = PullRequestForm(
            upstream_repository,
            configuration.upstream_base,
            f"{configuration.fork_repository.owner}:{branch}",
            title,
            body,
        )
        link = form.link
        if link is None:
            raise PromotionLinkTooLongError(
                branch, len(form.url_for("")), cls.url_character_limit
            )
        return cls(link.url, link.body_was_truncated)

    def print_url(self) -> None:
        """
        Print the compare-and-create URL, reporting on stderr if the body was shortened.
        """
        logger.info(self.url)
        if self.body_was_truncated:
            logger.error("the description was shortened to fit the URL length limit")
