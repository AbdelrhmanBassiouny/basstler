"""
Tests for basstler.plan.item_brief: the one brief a session reads before working a plan
item.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from basstler.github_labels import GitHubLabel
from basstler.locations import PluginLocation
from basstler.plan.check_dependency_readiness import ReadinessField
from basstler.plan.item_brief import (
    ItemBrief,
    ItemBriefCommandLine,
    ItemBriefKey,
    ItemBriefOption,
    ItemByBranch,
    ItemByIdentifier,
)
from basstler.plan.model import (
    ItemNotTrackedError,
    ManifestKey,
    PlanDocument,
    PlanManifest,
)
from basstler.plan.size_limits import Roadmap
from basstler.pull_request_state import PullRequestRecord, PullRequestState
from basstler.repository import PullRequestReference, Repository

from ..constants.paths import DatasetLocation
from ..fixture_plans import FixturePlanId, ForeignItemId
from ..recorded_pull_requests import RecordedPullRequestSource
from ..scratch_repository import ScratchRepository

# %% the briefed plan

BRIEFED_MANIFEST = PlanManifest.from_file(DatasetLocation.BRIEF_PLAN)
"""
The plan the tests publish and brief an item of.
"""

BRIEFED_ITEM = BRIEFED_MANIFEST.item_named("briefed-item")
"""
The item every brief is read for.
"""

FOREIGN_MANIFEST = PlanManifest.from_file(
    DatasetLocation.PLANS / FixturePlanId.OTHER / PlanDocument.MANIFEST
)
"""
The other plan one of the briefed item's dependencies belongs to.
"""


def pull_request_of(
    manifest: PlanManifest, item_identifier: str
) -> PullRequestReference:
    """
    :param manifest: The plan the item belongs to.
    :param item_identifier: The item's id.
    :return: The item's pull request, on the plan's default repository.
    """
    return PullRequestReference(
        Repository.parse(manifest.content[ManifestKey.DEFAULT_REPOSITORY.key]),
        manifest.item_named(item_identifier).content[
            ManifestKey.PULL_REQUEST_NUMBER.key
        ],
    )


@pytest.fixture
def pull_request_source() -> RecordedPullRequestSource:
    """
    :return: The dependencies' pull requests: one merged, one draft, and the foreign
        one out of draft.
    """
    return RecordedPullRequestSource(
        records={
            pull_request_of(BRIEFED_MANIFEST, "merged-dependency"): PullRequestRecord(
                state=PullRequestState.CLOSED, labels=[GitHubLabel.MERGED.value]
            ),
            pull_request_of(BRIEFED_MANIFEST, "draft-dependency"): PullRequestRecord(
                state=PullRequestState.OPEN, draft=True
            ),
            pull_request_of(FOREIGN_MANIFEST, ForeignItemId.READY): PullRequestRecord(
                state=PullRequestState.OPEN
            ),
        }
    )


@pytest.fixture
def briefed_repository(scratch_repository: ScratchRepository) -> ScratchRepository:
    """
    :return: A scratch repository whose notes branch carries the briefed plan and the
        other plan.
    """
    scratch_repository.install_hook_scripts(
        PluginLocation.PERSONAL_NOTES_CONFIGURATION_SCRIPT.name
    )
    scratch_repository.write("README.md", "scratch repo\n")
    scratch_repository.commit_everything("initial commit")
    scratch_repository.publish_notes_branch(
        {
            PlanDocument.MANIFEST.path_within_notes_branch(
                BRIEFED_MANIFEST.identifier
            ): DatasetLocation.BRIEF_PLAN.read_text(),
            PlanDocument.ROADMAP.path_within_notes_branch(
                BRIEFED_MANIFEST.identifier
            ): DatasetLocation.BRIEF_ROADMAP.read_text(),
            PlanDocument.MANIFEST.path_within_notes_branch(
                FOREIGN_MANIFEST.identifier
            ): (
                DatasetLocation.PLANS / FixturePlanId.OTHER / PlanDocument.MANIFEST
            ).read_text(),
        }
    )
    scratch_repository.resolve_notes_remote_to()
    return scratch_repository


def read_brief(
    repository: ScratchRepository,
    pull_request_source: RecordedPullRequestSource,
    selection: ItemByIdentifier | ItemByBranch = ItemByIdentifier(
        BRIEFED_ITEM.identifier
    ),
) -> dict[str, Any]:
    """
    :param repository: The repository whose notes branch carries the plan.
    :param pull_request_source: The live state of the dependencies' pull requests.
    :param selection: Which item to brief.
    :return: The brief, rendered and parsed back.
    """
    brief = ItemBrief.read(
        repository.project_root,
        BRIEFED_MANIFEST.identifier,
        selection,
        pull_request_source,
    )
    return yaml.safe_load(brief.render())


# %% the brief


def test_the_brief_holds_the_plan_header_and_the_item(
    briefed_repository: ScratchRepository,
    pull_request_source: RecordedPullRequestSource,
):
    brief = read_brief(briefed_repository, pull_request_source)
    header = BRIEFED_MANIFEST.item_header(BRIEFED_ITEM)

    assert {key: brief[key] for key in header} == header


def test_the_brief_says_which_dependencies_are_ready_to_build_on(
    briefed_repository: ScratchRepository,
    pull_request_source: RecordedPullRequestSource,
):
    brief = read_brief(briefed_repository, pull_request_source)

    assert [
        (dependency[ReadinessField.IDENTIFIER], dependency[ReadinessField.IS_READY])
        for dependency in brief[ItemBriefKey.DEPENDENCIES]
    ] == list(
        zip(BRIEFED_ITEM.content[ManifestKey.DEPENDS_ON.key], [True, False, True])
    )


def test_the_brief_resolves_a_dependency_in_another_plan(
    briefed_repository: ScratchRepository,
    pull_request_source: RecordedPullRequestSource,
):
    brief = read_brief(briefed_repository, pull_request_source)

    assert (
        brief[ItemBriefKey.DEPENDENCIES][-1][ReadinessField.TITLE]
        == FOREIGN_MANIFEST.item_named(ForeignItemId.READY).content[
            ManifestKey.TITLE.key
        ]
    )


def test_the_brief_holds_the_plans_standing_rules(
    briefed_repository: ScratchRepository,
    pull_request_source: RecordedPullRequestSource,
):
    brief = read_brief(briefed_repository, pull_request_source)

    assert (
        brief[ItemBriefKey.STANDING_RULES]
        == Roadmap.from_text(DatasetLocation.BRIEF_ROADMAP.read_text()).entries
    )


def test_an_item_is_briefed_the_same_by_its_branch(
    briefed_repository: ScratchRepository,
    pull_request_source: RecordedPullRequestSource,
):
    by_branch = read_brief(
        briefed_repository,
        pull_request_source,
        ItemByBranch(BRIEFED_ITEM.content[ManifestKey.BRANCH.key]),
    )

    assert by_branch == read_brief(briefed_repository, pull_request_source)


def test_an_item_the_plan_does_not_track_is_refused(
    briefed_repository: ScratchRepository,
    pull_request_source: RecordedPullRequestSource,
):
    with pytest.raises(ItemNotTrackedError):
        read_brief(briefed_repository, pull_request_source, ItemByIdentifier("missing"))


# %% command line


def test_the_command_prints_the_brief(
    briefed_repository: ScratchRepository,
    pull_request_source: RecordedPullRequestSource,
    capsys: pytest.CaptureFixture[str],
):
    arguments = ItemBriefCommandLine.parser().parse_args(
        [
            ItemBriefOption.PLAN,
            BRIEFED_MANIFEST.identifier,
            ItemBriefOption.ITEM,
            BRIEFED_ITEM.identifier,
        ]
    )

    ItemBriefCommandLine.run(
        arguments, pull_request_source, briefed_repository.project_root
    )

    assert yaml.safe_load(capsys.readouterr().out) == read_brief(
        briefed_repository, pull_request_source
    )
