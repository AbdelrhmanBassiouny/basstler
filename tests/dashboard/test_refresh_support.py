"""
Tests for dashboard/refresh_support.py: the JSON-plumbing helpers refresh_dashboard.sh
calls between plan/sync_manifest_status.py and dashboard/plan_page.py.
"""

import json
import sys

import pytest

from basstler.dashboard.publication import (
    DashboardUrlCache,
    PublicationCheck,
    PublicationField,
)
from basstler.dashboard.refresh_support import (
    SummaryKeyCollisionError,
    check_publication,
    count_corrected,
    main,
    merge_summaries,
)

from ..constants.paths import DatasetLocation

# %% count_corrected


def test_count_corrected_counts_the_corrected_list():
    summary = json.dumps({"corrected": [{"id": "a"}, {"id": "b"}]})
    assert count_corrected(summary) == 2


def test_count_corrected_zero_when_nothing_corrected():
    summary = json.dumps({"corrected": []})
    assert count_corrected(summary) == 0


# %% merge_summaries


def test_merge_summaries_combines_both_objects():
    sync_summary = json.dumps({"corrected": [{"id": "a"}]})
    build_summary = json.dumps({"status_counts": {"done": 1}, "drift_count": 0})
    merged = merge_summaries(sync_summary, build_summary)
    assert merged == {
        "corrected": [{"id": "a"}],
        "status_counts": {"done": 1},
        "drift_count": 0,
    }


def test_merge_summaries_raises_on_a_shared_key_instead_of_silently_dropping_one():
    sync_summary = json.dumps({"corrected": [{"id": "a"}], "drift_count": 1})
    build_summary = json.dumps({"drift_count": 0})
    with pytest.raises(SummaryKeyCollisionError, match="drift_count"):
        merge_summaries(sync_summary, build_summary)


# %% main - subcommand dispatch


def test_main_dispatches_count_corrected(monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dashboard/refresh_support.py",
            "count-corrected",
            json.dumps({"corrected": [{"id": "a"}, {"id": "b"}]}),
        ],
    )
    exit_code = main()
    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "2"


def test_main_dispatches_merge_summaries(monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dashboard/refresh_support.py",
            "merge-summaries",
            json.dumps({"corrected": [{"id": "a"}]}),
            json.dumps({"drift_count": 0}),
        ],
    )
    exit_code = main()
    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {
        "corrected": [{"id": "a"}],
        "drift_count": 0,
    }


def test_merge_summaries_combines_any_number_of_objects():
    merged = merge_summaries(
        json.dumps({"corrected": []}),
        json.dumps({"drift_count": 0}),
        json.dumps({PublicationField.UNCHANGED: True}),
    )
    assert merged == {
        "corrected": [],
        "drift_count": 0,
        PublicationField.UNCHANGED: True,
    }


# %% check_publication


DIGESTED_CACHE_TEXT = (
    DatasetLocation.DIRECTORY / "dashboard-urls-with-content-digests.yaml"
).read_text()


def build_summary_with_digest(content_digest: str) -> str:
    """
    :param content_digest: The digest the build reports for the files it wrote.
    :return: A build summary carrying it.
    """
    return json.dumps(
        {"drift_count": 0, PublicationField.CONTENT_DIGEST: content_digest}
    )


def test_check_publication_reads_the_digest_from_the_build_summary():
    cache = DashboardUrlCache.from_yaml(DIGESTED_CACHE_TEXT)
    recorded_digest = cache.content_digests["alpha-plan"]
    assert check_publication(
        build_summary_with_digest(recorded_digest), "alpha-plan", DIGESTED_CACHE_TEXT
    ) == cache.check("alpha-plan", recorded_digest)


def test_check_publication_without_a_cache_has_nowhere_to_publish_to():
    assert check_publication(
        build_summary_with_digest("a" * 64), "alpha-plan", ""
    ) == PublicationCheck(url=None, unchanged=False)


def test_main_dispatches_check_publication(monkeypatch, capsys, tmp_path):
    cache_path = tmp_path / "dashboard-urls.yaml"
    cache_path.write_text(DIGESTED_CACHE_TEXT)
    cache = DashboardUrlCache.from_yaml(DIGESTED_CACHE_TEXT)
    recorded_digest = cache.content_digests["alpha-plan"]
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dashboard/refresh_support.py",
            "check-publication",
            "--key",
            "alpha-plan",
            "--build-summary",
            build_summary_with_digest(recorded_digest),
            "--cache",
            str(cache_path),
        ],
    )
    assert main() == 0
    assert (
        json.loads(capsys.readouterr().out)
        == cache.check("alpha-plan", recorded_digest).to_json()
    )


def test_main_checks_publication_without_a_cache(monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dashboard/refresh_support.py",
            "check-publication",
            "--key",
            "alpha-plan",
            "--build-summary",
            build_summary_with_digest("a" * 64),
        ],
    )
    assert main() == 0
    assert (
        json.loads(capsys.readouterr().out)
        == PublicationCheck(url=None, unchanged=False).to_json()
    )
