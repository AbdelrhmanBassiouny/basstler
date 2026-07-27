"""
Tests for refresh_dashboard_support.py: the JSON-plumbing helpers refresh_dashboard.sh
calls between sync_manifest_status.py and build_dashboard.py.
"""

import json

from refresh_dashboard_support import count_corrected, merge_summaries

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
