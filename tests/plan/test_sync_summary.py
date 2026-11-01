"""
Tests for :mod:`basstler.plan.sync_summary`.
"""

from __future__ import annotations

import json
import sys

from basstler.plan.sync_summary import count_corrected, main

# %% counting corrections


def test_count_corrected_counts_the_corrected_list():
    summary = json.dumps({"corrected": [{"id": "a"}, {"id": "b"}]})
    assert count_corrected(summary) == 2


def test_count_corrected_zero_when_nothing_corrected():
    summary = json.dumps({"corrected": []})
    assert count_corrected(summary) == 0


def test_main_prints_the_count(monkeypatch, capsys):
    summary = json.dumps({"corrected": [{"id": "a"}, {"id": "b"}]})
    monkeypatch.setattr(
        sys, "argv", ["basstler.plan.sync_summary", "count-corrected", summary]
    )
    assert main() == 0
    assert capsys.readouterr().out.strip() == str(count_corrected(summary))
