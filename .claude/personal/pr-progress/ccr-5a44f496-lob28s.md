PR #57 (draft, release:minor) - plan session-notes-infrastructure, item fresh-base-at-session-start.
Reference: CRAM fork #188 commit 9b8d6d1 (issue #51).

Plan
- basstler.maintenance.default_branch_sync (dataclass report) run by session-start.sh as "default branch:".
- Fast-forward only; fetch with --no-write-fetch-head; summary SHA from the stamp.
- No upstream named: follow the clone's own remote (BaseSource), push nothing.
- Checked-out branch with no commits of its own is fast-forwarded too; with commits, only measured.

Done
- Module, 17 tests + forked_scratch_repository.py, hook wiring, README; main merged (4837c89).
- Review round 1 (5ca4154): module docstring cut to one statement; sync_this_checkout became
  DefaultBranchSync.catch_up_checkout. Both threads replied to and resolved; suite 1339 passed.

Next
- Review on #57; address comments when prompted. Unifying with maintenance.fast_forward is
  stack-maintenance item shared-fork-base-fast-forward, after #57 lands.
