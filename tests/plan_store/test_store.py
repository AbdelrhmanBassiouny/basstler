"""
Tests for the issue-based plan store: the requests it sends, the plan it reads back, and
the status an item's issue and closing pull requests give it.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime

import pytest

from basstler.github.client import HttpMethod
from basstler.github_labels import GitHubLabel
from basstler.plan.model import ItemStatus
from basstler.plan_store.item_body import IssueReference, ItemBody
from basstler.plan_store.rest_models import (
    IssueCreation,
    IssueState,
    LabelAddition,
    RestIssue,
    RestLabel,
    RestPullRequestLink,
    SubIssueAddition,
)
from basstler.plan_store.store import IssuePlanStore, ItemIssue, LabelledStatus
from basstler.repository import Repository

from ..constants.paths import PlanStoreResponse
from ..github.api_stand_in import RequestLine
from ..github.recorded_client import RecordedGitHubClient, SentWrite

REPOSITORY = Repository("example-owner", "example-repo")
PLAN_NUMBER = 100
ISSUES_PATH = f"{REPOSITORY.api_path}/issues"
SUB_ISSUES_PATH = f"{REPOSITORY.issue_path(PLAN_NUMBER)}/sub_issues"


def recorded(response: PlanStoreResponse):
    """:return: The recorded response, parsed."""
    return json.loads(response.read_text())


@pytest.fixture
def item_issue() -> RestIssue:
    """:return: Issue 101, open, unlabelled and with no closing pull request."""
    return RestIssue.from_response(recorded(PlanStoreResponse.CREATED_ITEM_ISSUE))


def pull_request(state: IssueState, merged_at: datetime | None = None) -> RestIssue:
    """:return: A pull request read as an issue, in the given state."""
    issue = RestIssue.from_response(recorded(PlanStoreResponse.TRACKING_ISSUE))
    return dataclasses.replace(
        issue, state=state, pull_request=RestPullRequestLink(merged_at)
    )


MERGED = datetime(2026, 11, 1, tzinfo=UTC)

# %% writes


def test_create_plan_opens_its_tracking_issue():
    client = RecordedGitHubClient(
        write_responses={
            RequestLine(HttpMethod.POST, ISSUES_PATH): recorded(
                PlanStoreResponse.TRACKING_ISSUE
            )
        }
    )
    issue = IssuePlanStore(client, REPOSITORY).create_plan("Plans", "Store plans.")
    assert client.writes == [
        SentWrite(
            HttpMethod.POST,
            ISSUES_PATH,
            IssueCreation("Plans", "Store plans.").payload(),
        )
    ]
    assert issue == RestIssue.from_response(recorded(PlanStoreResponse.TRACKING_ISSUE))


def test_add_item_opens_its_issue_and_lists_it_under_the_plan(item_issue):
    client = RecordedGitHubClient(
        write_responses={
            RequestLine(HttpMethod.POST, ISSUES_PATH): recorded(
                PlanStoreResponse.CREATED_ITEM_ISSUE
            )
        }
    )
    body = ItemBody("Store plans as issues.", (IssueReference(REPOSITORY, 103),))
    IssuePlanStore(client, REPOSITORY).add_item(PLAN_NUMBER, item_issue.title, body)
    assert client.writes == [
        SentWrite(
            HttpMethod.POST,
            ISSUES_PATH,
            IssueCreation(item_issue.title, body.render(REPOSITORY)).payload(),
        ),
        SentWrite(
            HttpMethod.POST,
            SUB_ISSUES_PATH,
            SubIssueAddition(item_issue.identifier).payload(),
        ),
    ]


def test_sub_issue_is_added_by_the_identifier_field_github_reads():
    assert SubIssueAddition(7).payload() == {"sub_issue_id": 7}


@pytest.mark.parametrize("status", list(LabelledStatus))
def test_add_status_label_labels_the_item(status):
    client = RecordedGitHubClient()
    IssuePlanStore(client, REPOSITORY).add_status_label(101, status)
    assert client.writes == [
        SentWrite(
            HttpMethod.POST,
            f"{REPOSITORY.issue_path(101)}/labels",
            LabelAddition((GitHubLabel(status),)).payload(),
        )
    ]


@pytest.mark.parametrize("status", list(LabelledStatus))
def test_remove_status_label_deletes_the_label(status):
    client = RecordedGitHubClient()
    IssuePlanStore(client, REPOSITORY).remove_status_label(101, status)
    assert client.writes == [
        SentWrite(
            HttpMethod.DELETE,
            f"{REPOSITORY.issue_path(101)}/labels/{GitHubLabel(status)}",
            {},
        )
    ]


# %% reading a plan


@pytest.fixture
def stored_plan_client() -> RecordedGitHubClient:
    """:return: A client answering with plan 100 and its three items."""
    return RecordedGitHubClient(
        responses={
            REPOSITORY.issue_path(PLAN_NUMBER): recorded(
                PlanStoreResponse.TRACKING_ISSUE
            )
        },
        pages={
            SUB_ISSUES_PATH: [recorded(PlanStoreResponse.SUB_ISSUES)],
            f"{REPOSITORY.issue_path(101)}/timeline": [
                recorded(PlanStoreResponse.ITEM_TIMELINE)
            ],
            f"{REPOSITORY.issue_path(102)}/timeline": [
                recorded(PlanStoreResponse.EMPTY_TIMELINE)
            ],
            f"{REPOSITORY.issue_path(103)}/timeline": [
                recorded(PlanStoreResponse.EMPTY_TIMELINE)
            ],
        },
    )


def test_read_plan_lists_its_items_in_order(stored_plan_client):
    plan = IssuePlanStore(stored_plan_client, REPOSITORY).read_plan(PLAN_NUMBER)
    assert [item.issue for item in plan.items] == RestIssue.from_pages(
        [recorded(PlanStoreResponse.SUB_ISSUES)]
    )


def test_read_plan_keeps_only_pull_requests_closing_the_item(stored_plan_client):
    plan = IssuePlanStore(stored_plan_client, REPOSITORY).read_plan(PLAN_NUMBER)
    assert [
        pull_request.number for pull_request in plan.items[0].closing_pull_requests
    ] == [110, 113]


def test_read_plan_reads_each_items_dependencies(stored_plan_client):
    plan = IssuePlanStore(stored_plan_client, REPOSITORY).read_plan(PLAN_NUMBER)
    assert plan.items[0].body.dependencies == (
        IssueReference(REPOSITORY, 103),
        IssueReference(Repository("other-owner", "other-repo"), 7),
    )


def test_read_plan_reads_each_items_status(stored_plan_client):
    plan = IssuePlanStore(stored_plan_client, REPOSITORY).read_plan(PLAN_NUMBER)
    assert [item.status for item in plan.items] == [
        ItemStatus.DONE,
        ItemStatus.BLOCKED,
        ItemStatus.DONE,
    ]


# %% an item's status


def test_item_without_pull_requests_is_not_started(item_issue):
    assert ItemIssue(item_issue).status is ItemStatus.NOT_STARTED


def test_item_with_an_open_closing_pull_request_is_in_progress(item_issue):
    item = ItemIssue(item_issue, (pull_request(IssueState.OPEN),))
    assert item.status is ItemStatus.IN_PROGRESS


def test_item_with_only_an_unmerged_closed_pull_request_is_not_started(item_issue):
    item = ItemIssue(item_issue, (pull_request(IssueState.CLOSED),))
    assert item.status is ItemStatus.NOT_STARTED


def test_item_with_a_merged_closing_pull_request_is_done(item_issue):
    item = ItemIssue(item_issue, (pull_request(IssueState.CLOSED, MERGED),))
    assert item.status is ItemStatus.DONE


def test_closed_item_is_done(item_issue):
    closed = dataclasses.replace(item_issue, state=IssueState.CLOSED)
    assert ItemIssue(closed).status is ItemStatus.DONE


@pytest.mark.parametrize("status", list(LabelledStatus))
def test_labelled_item_has_its_labels_status(item_issue, status):
    labelled = dataclasses.replace(item_issue, labels=(RestLabel(status),))
    item = ItemIssue(labelled, (pull_request(IssueState.OPEN),))
    assert item.status is ItemStatus(status)
