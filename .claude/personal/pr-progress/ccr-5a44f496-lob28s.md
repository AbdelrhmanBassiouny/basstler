PR #57 (draft, release:minor) - plan session-notes-infrastructure, item fresh-base-at-session-start.
Reference: CRAM fork #188 commit 9b8d6d1 (issue #51).

Plan
- basstler.default_branch_sync (dataclass report) run by session-start.sh as "default branch:".
- Fast-forward only; fetch with --no-write-fetch-head; summary SHA from the stamp.

Done
- Module, tests/test_default_branch_sync.py (14) + forked_scratch_repository.py, hook wiring,
  README section + safety bullets. Full suite 1000 passed (needs venv python first on PATH).
- PR description, label, manifest notes, dashboard.

Next
- Review on #57; address comments when prompted.
