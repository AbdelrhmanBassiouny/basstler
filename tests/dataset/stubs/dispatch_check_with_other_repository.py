"""
Stands in for :mod:`basstler.plan_site.dispatch_check`, reporting a dispatch that starts
the build and a second repository whose latest run failed.
"""

from __future__ import annotations

from basstler.setup.report import CheckResult, CheckStatus
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is what the stub prints through.
"""

logger.info(CheckResult(CheckStatus.OK, "the own repository starts the build").fields)
logger.info(
    CheckResult(
        CheckStatus.INFORMATIONAL, "another repository's latest run failed"
    ).fields
)
