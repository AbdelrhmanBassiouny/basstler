"""
Plans stored on GitHub: a tracking issue per plan, whose sub-issues are its items.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import quote

from basstler.github.client import GitHubClient, HttpMethod
from basstler.github_labels import GitHubLabel
from basstler.plan.model import ItemStatus
from basstler.plan_store.item_body import IssueReference, ItemBody
from basstler.plan_store.rest_models import (
    IssueCreation,
    IssueState,
    LabelAddition,
    RestIssue,
    RestTimelineEvent,
    SubIssueAddition,
    TimelineEventKind,
)
from basstler.repository import Repository

# %% an item's status


class LabelledStatus(StrEnum):
    """
    The statuses an item issue carries as the label of the same name; every other
    status is read from the pull requests that close it.
    """

    BLOCKED = ItemStatus.BLOCKED.value
    """
    :attr:`ItemStatus.BLOCKED`, labelled :attr:`GitHubLabel.BLOCKED`.
    """

    DEFERRED = ItemStatus.DEFERRED.value
    """
    :attr:`ItemStatus.DEFERRED`, labelled :attr:`GitHubLabel.DEFERRED`.
    """


@dataclass(frozen=True)
class ItemIssue:
    """
    A plan item's issue, with the pull requests whose descriptions close it.
    """

    issue: RestIssue
    """
    The item's issue.
    """

    closing_pull_requests: tuple[RestIssue, ...] = ()
    """
    The pull requests, open or closed, whose descriptions close the issue.
    """

    @property
    def body(self) -> ItemBody:
        """
        The item's scope and dependencies, as its issue's body states them.
        """
        return ItemBody.parse(self.issue.body or "", self.issue.repository)

    @property
    def status(self) -> ItemStatus:
        """
        Done once the issue is closed or a closing pull request is merged, else the
        status its label names, else in progress while a closing pull request is open.
        """
        if self.issue.state is IssueState.CLOSED or any(
            pull_request.pull_request.merged_at
            for pull_request in self.closing_pull_requests
        ):
            return ItemStatus.DONE
        labels = {label.name for label in self.issue.labels}
        for labelled in LabelledStatus:
            if labelled in labels:
                return ItemStatus(labelled)
        if any(
            pull_request.state is IssueState.OPEN
            for pull_request in self.closing_pull_requests
        ):
            return ItemStatus.IN_PROGRESS
        return ItemStatus.NOT_STARTED


@dataclass(frozen=True)
class IssuePlan:
    """
    A plan as GitHub stores it.
    """

    tracking_issue: RestIssue
    """
    The issue whose title is the plan's and whose sub-issues are its items.
    """

    items: tuple[ItemIssue, ...]
    """
    The plan's items, in the order the tracking issue lists them.
    """


# %% the store


class IssueResource(StrEnum):
    """
    The REST resources below an issue's path that the store reads and writes.
    """

    SUB_ISSUES = "sub_issues"
    """
    The issues listed under it.
    """

    TIMELINE = "timeline"
    """
    Everything that happened to it, cross-references included.
    """

    LABELS = "labels"
    """
    The labels it carries.
    """


@dataclass(frozen=True)
class IssuePlanStore:
    """
    The plans a repository stores as issues: reading them, and writing their items,
    dependencies and labelled statuses.
    """

    client: GitHubClient
    """
    How the requests reach GitHub.
    """

    repository: Repository
    """
    The repository the plans' issues are opened on.
    """

    def create_plan(self, title: str, description: str) -> RestIssue:
        """
        :param title: The plan's title.
        :param description: What the plan is for, as Markdown.
        :return: The plan's new tracking issue.
        """
        return self._create_issue(IssueCreation(title, description))

    def add_item(self, plan_number: int, title: str, body: ItemBody) -> RestIssue:
        """
        Open an item's issue and list it under its plan's tracking issue.

        :param plan_number: The plan's tracking issue.
        :param title: The item's title.
        :param body: The item's scope and dependencies.
        :return: The item's new issue.
        """
        issue = self._create_issue(IssueCreation(title, body.render(self.repository)))
        self.client.send(
            HttpMethod.POST,
            self._resource_path(self.repository, plan_number, IssueResource.SUB_ISSUES),
            SubIssueAddition(issue.identifier).payload(),
        )
        return issue

    def read_plan(self, plan_number: int) -> IssuePlan:
        """
        :param plan_number: The plan's tracking issue.
        :return: The plan, with each item's closing pull requests.
        """
        tracking_issue = RestIssue.from_response(
            self.client.get(self.repository.issue_path(plan_number))
        )
        sub_issues = RestIssue.from_pages(
            self.client.get_pages(
                self._resource_path(
                    self.repository, plan_number, IssueResource.SUB_ISSUES
                )
            )
        )
        return IssuePlan(
            tracking_issue, tuple(self._read_item(issue) for issue in sub_issues)
        )

    def add_status_label(self, item_number: int, status: LabelledStatus) -> None:
        """
        :param item_number: The item's issue.
        :param status: The status to label it with.
        """
        self.client.send(
            HttpMethod.POST,
            self._resource_path(self.repository, item_number, IssueResource.LABELS),
            LabelAddition((GitHubLabel(status),)).payload(),
        )

    def remove_status_label(self, item_number: int, status: LabelledStatus) -> None:
        """
        :param item_number: The item's issue.
        :param status: The status whose label to take off it.
        :raises GitHubRequestFailed: If the issue does not carry the label.
        """
        label_path = self._resource_path(
            self.repository, item_number, IssueResource.LABELS
        )
        self.client.send(
            HttpMethod.DELETE, f"{label_path}/{quote(GitHubLabel(status))}", {}
        )

    def _read_item(self, issue: RestIssue) -> ItemIssue:
        """
        :param issue: An item's issue, as its plan's sub-issue listing gave it.
        :return: The item, with the pull requests its timeline shows closing it.
        """
        events = RestTimelineEvent.from_pages(
            self.client.get_pages(
                self._resource_path(
                    issue.repository, issue.number, IssueResource.TIMELINE
                )
            )
        )
        reference = IssueReference(issue.repository, issue.number)
        closing_pull_requests = (
            self._closing_pull_request(event, reference) for event in events
        )
        return ItemIssue(
            issue,
            tuple(
                pull_request
                for pull_request in closing_pull_requests
                if pull_request is not None
            ),
        )

    @staticmethod
    def _closing_pull_request(
        event: RestTimelineEvent, reference: IssueReference
    ) -> RestIssue | None:
        """
        :param event: An event on the timeline of the issue *reference* names.
        :param reference: The issue.
        :return: The pull request the event shows referencing the issue, if its
            description closes it.
        """
        if event.event != TimelineEventKind.CROSS_REFERENCED or event.source is None:
            return None
        source = event.source.issue
        if source.pull_request is None:
            return None
        if reference not in IssueReference.closed_by(
            source.body or "", source.repository
        ):
            return None
        return source

    def _create_issue(self, creation: IssueCreation) -> RestIssue:
        """
        :param creation: The new issue's title and body.
        :return: The issue opened.
        """
        return RestIssue.from_response(
            self.client.send(
                HttpMethod.POST,
                f"{self.repository.api_path}/issues",
                creation.payload(),
            )
        )

    @staticmethod
    def _resource_path(
        repository: Repository, number: int, resource: IssueResource
    ) -> str:
        """
        :param repository: The repository an issue is opened on.
        :param number: The issue's number.
        :param resource: The resource below the issue.
        :return: The resource's REST path.
        """
        return f"{repository.issue_path(number)}/{resource}"
