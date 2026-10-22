PR #57 (draft, release:minor) - plan session-notes-infrastructure, item fresh-base-at-session-start.
Reference: CRAM fork #188 commit 9b8d6d1 (issue #51).

Plan
- basstler.default_branch_sync (dataclass report) run by session-start.sh as "default branch:".
- Fast-forward only; fetch with --no-write-fetch-head; summary SHA from the stamp.
- No upstream named: follow the clone's own remote (BaseSource), push nothing.
- Checked-out branch with no commits of its own is fast-forwarded too; with commits, only measured.

Done
- Module, 17 tests + forked_scratch_repository.py, hook wiring, README. Suite 1003 passed
  (venv python first on PATH). Own-remote fallback in 1a8d082; description, plan notes updated.
- Fork-main push from sessions: same plain git push stack maintenance uses (works per user).

Next
- Review on #57; address comments when prompted.
