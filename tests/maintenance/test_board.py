"""
Tests for running git and for the board export the maintenance pass reads, both pure
except for the one git call.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from basstler.repository import Repository
from basstler.stack.model import PullRequest

from basstler.locations import PackageLocation
from basstler.maintenance.board import (
    BoardExport,
    MissingPullRequestFieldError,
    PullRequestField,
    PullRequestHeadKey,
    get_promotion_link_in,
    get_session_link_in,
)
from basstler.maintenance.git_commands import GitCommandFailed
from basstler.maintenance.promotion import description_with_promotion_link

from ..constants.stack import StackBranch, StackLabel

from .fork import (
    StackPullRequestNumber,
    PullRequestHeadRepository,
    A_SESSION_LINK,
    ForkCheckout,
    PromotionSampleText,
    an_api_record,
)


# %% running git


def test_a_failing_git_command_raises_rather_than_returning_nothing(
    fork_checkout: ForkCheckout,
):
    """
    ``basstler.stack``'s helper returns an empty string on failure, which here would
    make a push that did nothing indistinguishable from one that worked.
    """
    with pytest.raises(GitCommandFailed) as raised:
        fork_checkout.git.run("rev-parse", "a-ref-that-does-not-exist")

    assert raised.value.arguments == ("rev-parse", "a-ref-that-does-not-exist")
    assert raised.value.status != 0


# %% the board export


def test_every_field_is_named_by_the_key_the_api_answers_under():
    """
    A member's value is the specification's argument tuple; passing a built
    specification instead lands the whole instance in the key, where every read then
    silently finds nothing.
    """
    for field in PullRequestField:
        assert isinstance(field.key, str), field
    assert len({field.key for field in PullRequestField}) == len(list(PullRequestField))


def test_the_export_reads_each_field_out_of_the_shape_the_api_returns_it_in():
    """
    ``head`` and ``base`` arrive nested and ``labels`` as objects, so a field read the
    wrong way produces a board that is wrong rather than empty.
    """
    export = BoardExport.from_api_records(
        [
            an_api_record(
                number=StackPullRequestNumber.CHILD,
                head=StackBranch.CHILD,
                base=StackBranch.PARENT,
                draft=True,
                labels=[StackLabel.REBASE],
                body=f"see {A_SESSION_LINK}",
            )
        ]
    )

    exported = export.pull_requests[0]
    assert exported.number == StackPullRequestNumber.CHILD
    assert exported.head == StackBranch.CHILD
    assert exported.base == StackBranch.PARENT
    assert exported.draft is True
    assert exported.labels == [StackLabel.REBASE]
    assert exported.session == A_SESSION_LINK


def test_the_written_board_parses_back_into_the_records_it_was_built_from(
    tmp_path: Path,
):
    """
    The export's only contract is that ``PullRequest.read_board`` reads it, so the
    expected value is derived by reading it rather than by hand-writing the shape twice.
    """
    export = BoardExport.from_api_records(
        [
            an_api_record(
                number=StackPullRequestNumber.CHILD,
                head=StackBranch.CHILD,
                base=StackBranch.PARENT,
                draft=True,
            ),
            an_api_record(
                number=StackPullRequestNumber.PARENT,
                head=StackBranch.PARENT,
                labels=[StackLabel.SOMEBODY_ELSES],
            ),
        ]
    )
    destination = tmp_path / "board.json"

    export.write(destination)

    assert PullRequest.read_board(destination) == list(export.pull_requests)


def test_a_pull_request_missing_a_required_field_is_rejected_rather_than_defaulted():
    """
    A dropped field is what made #119's bad data indistinguishable from good data, so
    the parser refuses it at the point it enters rather than substituting a default.
    """
    record = an_api_record(number=StackPullRequestNumber.CHILD)
    del record["draft"]

    with pytest.raises(MissingPullRequestFieldError) as raised:
        BoardExport.from_api_records([record])

    assert raised.value.field_name == PullRequestField.DRAFT
    assert raised.value.pull_request_number == StackPullRequestNumber.CHILD


@pytest.mark.parametrize(
    "head_repository",
    [
        PullRequestHeadRepository.FORK.value,
        PullRequestHeadRepository.ANOTHER_CONTRIBUTORS_FORK.value,
    ],
)
def test_the_export_records_the_repository_the_head_lives_in(
    head_repository: Repository,
):
    export = BoardExport.from_api_records(
        [an_api_record(head_repository=head_repository)]
    )

    assert export.pull_requests[0].head_repository == head_repository.full_name


def test_a_deleted_head_repository_is_exported_as_none():
    """
    GitHub answers a deleted head repository with ``null``, which is a fact about the
    pull request rather than a dropped field.
    """
    export = BoardExport.from_api_records([an_api_record(head_repository=None)])

    assert export.pull_requests[0].head_repository is None


def test_a_head_that_does_not_say_where_it_lives_is_rejected():
    record = an_api_record(number=StackPullRequestNumber.CHILD)
    del record[PullRequestField.HEAD.key][PullRequestHeadKey.HEAD_REPOSITORY]

    with pytest.raises(MissingPullRequestFieldError) as raised:
        BoardExport.from_api_records([record])

    assert raised.value.field_name == PullRequestField.HEAD
    assert raised.value.pull_request_number == StackPullRequestNumber.CHILD


def test_the_board_snapshot_is_never_committable():
    """
    ``board --write`` writes into the working tree, so nothing but ``.gitignore`` stands
    between a pass and a committed snapshot of a stack that has since moved.
    """
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", str(PackageLocation.BOARD)],
        cwd=PackageLocation.DIRECTORY.value,
        capture_output=True,
    )

    assert ignored.returncode == 0


def test_a_session_link_is_read_out_of_the_description():
    body = f"Some prose.\n\nSession: {A_SESSION_LINK}\n"

    assert get_session_link_in(body) == A_SESSION_LINK


def test_a_description_naming_no_session_yields_none():
    assert get_session_link_in("Some prose with no link.") is None


def test_the_export_reads_the_title_and_the_recorded_promotion_link():
    body = description_with_promotion_link(
        PromotionSampleText.PROSE, PromotionSampleText.FIRST_LINK
    )
    export = BoardExport.from_api_records(
        [an_api_record(body=body, title=PromotionSampleText.TITLE)]
    )

    exported = export.pull_requests[0]
    assert exported.title == PromotionSampleText.TITLE
    assert exported.promotion_link == PromotionSampleText.FIRST_LINK


def test_the_promotion_link_read_back_is_the_one_written():
    body = description_with_promotion_link(
        PromotionSampleText.PROSE, PromotionSampleText.FIRST_LINK
    )

    assert get_promotion_link_in(body) == PromotionSampleText.FIRST_LINK


def test_a_description_with_no_promotion_section_yields_no_link():
    assert get_promotion_link_in(PromotionSampleText.PROSE) is None
