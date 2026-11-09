"""
Stands in for :mod:`basstler.personal_notes.access`, printing its module name as the
missing access instead of calling GitHub.
"""

from __future__ import annotations

print(__spec__.name)
