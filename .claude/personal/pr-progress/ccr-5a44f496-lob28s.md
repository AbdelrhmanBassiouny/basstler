PR #57 (draft, release:minor) - plan session-notes-infrastructure, item fresh-base-at-session-start.
Reference: CRAM fork #188 commit 9b8d6d1 (issue #51).

Plan
- basstler.default_branch_sync (dataclass report) run by session-start.sh as "default branch:".
- Fast-forward only; fetch with --no-write-fetch-head; summary SHA from the stamp.
- Checked-out branch with no commits of its own is fast-forwarded too; with commits, only measured.

Done
- Module, 16 tests + forked_scratch_repository.py, hook wiring, README. Suite 1002 passed
  (venv python first on PATH). Session-branch fast-forward in d2cc02b; description updated.
- Verified: unattached upstream readable; REST ref writes 403 via proxy; git push to a fork's
  main from a session still unverified (reported as a row if refused).

Next
- Review on #57; address comments when prompted.
