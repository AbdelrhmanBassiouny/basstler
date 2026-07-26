"""
Tests for sync_manifest_status.py: auto-correcting a plan.yaml's item statuses to "done"
wherever GitHub confirms the item's pull request is merged.
"""

from datetime import datetime
from pathlib import Path

import pytest
import yaml

from build_dashboard import ItemStatus, PullRequestRecord, PullRequestState
from sync_manifest_status import (
    MissingStatusLineError,
    apply_status_corrections,
    find_items_to_correct,
)


def plan(**overrides):
    data = {
        "schema_version": 1,
        "id": "test-plan",
        "title": "Test Plan",
        "description": "A plan.",
        "default_repository": "owner/repo",
        "waves": [{"id": "wave-1", "name": "Wave 1"}],
        "tracks": [{"id": "track-1", "name": "Track 1", "wave": "wave-1"}],
        "items": [],
    }
    data.update(overrides)
    return data


def item(identifier, status, pull_request_number=None, repository=None):
    entry = {
        "id": identifier,
        "title": identifier,
        "branch": identifier,
        "track": "track-1",
        "status": status,
        "pull_request_number": pull_request_number,
    }
    if repository is not None:
        entry["repository"] = repository
    return entry


# %% find_items_to_correct


def test_finds_an_in_progress_item_whose_pull_request_is_merged():
    pull_requests_by_repository = {
        "owner/repo": {
            "1": PullRequestRecord(
                state=PullRequestState.CLOSED, merged_at=datetime(2026, 1, 1)
            )
        }
    }
    items = [item("a", "in_progress", pull_request_number=1)]
    corrections = find_items_to_correct(plan(items=items), pull_requests_by_repository)
    assert [entry["id"] for entry in corrections] == ["a"]


def test_ignores_an_item_already_marked_done():
    pull_requests_by_repository = {
        "owner/repo": {
            "1": PullRequestRecord(
                state=PullRequestState.CLOSED, merged_at=datetime(2026, 1, 1)
            )
        }
    }
    items = [item("a", "done", pull_request_number=1)]
    assert find_items_to_correct(plan(items=items), pull_requests_by_repository) == []


def test_ignores_an_item_whose_pull_request_is_still_open():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state=PullRequestState.OPEN, draft=False)}
    }
    items = [item("a", "in_progress", pull_request_number=1)]
    assert find_items_to_correct(plan(items=items), pull_requests_by_repository) == []


def test_ignores_an_item_with_no_pull_request_yet():
    items = [item("a", "not_started")]
    assert find_items_to_correct(plan(items=items), {}) == []


def test_merged_via_out_of_band_label_is_also_corrected():
    pull_requests_by_repository = {
        "owner/repo": {
            "1": PullRequestRecord(state=PullRequestState.CLOSED, labels=["merged"])
        }
    }
    items = [item("a", "blocked", pull_request_number=1)]
    corrections = find_items_to_correct(plan(items=items), pull_requests_by_repository)
    assert [entry["id"] for entry in corrections] == ["a"]


def test_uses_the_item_repository_override_over_the_plan_default():
    pull_requests_by_repository = {
        "owner/other-repo": {
            "1": PullRequestRecord(
                state=PullRequestState.CLOSED, merged_at=datetime(2026, 1, 1)
            )
        }
    }
    items = [
        item("a", "in_progress", pull_request_number=1, repository="owner/other-repo")
    ]
    corrections = find_items_to_correct(plan(items=items), pull_requests_by_repository)
    assert [entry["id"] for entry in corrections] == ["a"]


# %% apply_status_corrections - real manifest text


MANIFEST_TEXT = (Path(__file__).parent / "fixtures" / "manifest.yaml").read_text()


def test_patches_only_the_targeted_items_status_line():
    data = yaml.safe_load(MANIFEST_TEXT)
    patched_text, corrections = apply_status_corrections(
        MANIFEST_TEXT, [data["items"][0]]
    )
    assert "  status: done" in patched_text
    assert "  status: not_started" in patched_text  # item b untouched
    assert [c.item_identifier for c in corrections] == ["a"]
    assert [c.previous_status for c in corrections] == [ItemStatus.IN_PROGRESS]


def test_patching_leaves_every_other_line_byte_for_byte_identical():
    data = yaml.safe_load(MANIFEST_TEXT)
    patched_text, _ = apply_status_corrections(MANIFEST_TEXT, [data["items"][0]])
    original_lines = MANIFEST_TEXT.split("\n")
    patched_lines = patched_text.split("\n")
    changed_line_pairs = [
        (before, after)
        for before, after in zip(original_lines, patched_lines)
        if before != after
    ]
    assert changed_line_pairs == [("  status: in_progress", "  status: done")]


def test_patched_text_still_parses_and_validates():
    data = yaml.safe_load(MANIFEST_TEXT)
    patched_text, _ = apply_status_corrections(MANIFEST_TEXT, [data["items"][0]])
    reparsed = yaml.safe_load(patched_text)
    assert reparsed["items"][0]["status"] == "done"
    assert reparsed["items"][0]["notes"] == data["items"][0]["notes"]


def test_no_items_to_correct_returns_original_text_unchanged():
    patched_text, corrections = apply_status_corrections(MANIFEST_TEXT, [])
    assert patched_text == MANIFEST_TEXT
    assert corrections == []


def test_raises_if_an_item_has_no_status_line():
    text = "- id: a\n  title: A\n  branch: a\n"
    with pytest.raises(MissingStatusLineError, match="no status: line"):
        apply_status_corrections(text, [{"id": "a", "branch": "a"}])
