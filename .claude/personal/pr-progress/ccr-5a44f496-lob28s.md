PR #57 (draft, release:minor) - plan session-notes-infrastructure, item fresh-base-at-session-start.
Reference: CRAM fork #188 commit 9b8d6d1 (issue #51).

Plan
- basstler.maintenance.default_branch_sync (dataclass report) run by session-start.sh as "default branch:".
- Fast-forward only; fetch with --no-write-fetch-head; summary SHA from the stamp.
- No upstream named: follow the clone's own remote (BaseSource), push nothing.
- Checked-out branch with no commits of its own is fast-forwarded too; with commits, only measured.

Done
- Module, 17 tests + forked_scratch_repository.py, hook wiring, README.
- Merged main (4837c89): moved into basstler.maintenance and tests/maintenance after the
  subpackage reorganization; suite 1339 passed. Description and plan notes updated.

Next
- Review on #57; address comments when prompted.
