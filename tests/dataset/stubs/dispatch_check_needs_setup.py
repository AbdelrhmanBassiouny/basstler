"""
Stands in for :mod:`basstler.plan_site.dispatch_check`, reporting a dispatch whose
latest run failed.
"""

from __future__ import annotations

from basstler.setup.report import CheckResult, CheckStatus

print(CheckResult(CheckStatus.NEEDS_SETUP, "the latest dispatch run failed").fields)
