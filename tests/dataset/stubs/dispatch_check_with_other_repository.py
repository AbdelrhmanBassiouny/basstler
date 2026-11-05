"""
Stands in for :mod:`basstler.plan_site.dispatch_check`, reporting a dispatch that starts
the build and a second repository whose latest run failed.
"""

from __future__ import annotations

from basstler.setup.report import CheckResult, CheckStatus

print(CheckResult(CheckStatus.OK, "the own repository starts the build").fields)
print(
    CheckResult(
        CheckStatus.INFORMATIONAL, "another repository's latest run failed"
    ).fields
)
