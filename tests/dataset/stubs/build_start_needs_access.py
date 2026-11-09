"""
Stands in for :mod:`basstler.plan_site.build_start`, printing that the session cannot
start the build yet, over two lines as the real command does.
"""

from __future__ import annotations

print("A plan save cannot start the build in an-owner/the-site yet.\nAttach it.")
