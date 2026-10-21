PR #57 - plan session-notes-infrastructure, item fresh-base-at-session-start.
Reference: CRAM fork #188 commit 9b8d6d1 (issue #51).

Plan
- Python module basstler.default_branch_sync: resolve upstream via stack.load_configuration,
  fetch upstream base without touching FETCH_HEAD, fast-forward local base (merge --ff-only if
  checked out, else fetch into ref), push to fork when fork tip differs, report rows.
- session-start.sh: run it as a subprocess, never fatal, print a "default branch:" line;
  plan state SHA read from the stamp, not FETCH_HEAD.
- Tests: forked scratch repo (owner/name.git stand-ins + url.insteadOf), every outcome.
- README section + safety bullets.

Done
- Branch, draft PR #57, manifest open/record.

Next
- Write failing tests, then the module, then the hook wiring.
