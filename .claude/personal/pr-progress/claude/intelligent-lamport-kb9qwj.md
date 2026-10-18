PR: https://github.com/AbdelrhmanBassiouny/basstler/pull/3 (draft, label `bug`)

Plan: make current_branch_upstream_remote return 0 when the branch has no
upstream, so create-personal-notes-branch.sh stops exiting 128 silently.

Done:
- Fix in plugin/hooks/resolve-personal-notes-config.sh; regression test
  tests/test_create_personal_notes_branch_sh.py; full suite 806 passed.
- Checked safety: the fix doesn't change which remote the branch is created
  on (always NOTES_REMOTE); the skipped upstream guard matches the read side,
  which also falls back only to the upstream remote.

Next:
- Wait for CI and review (handle only when asked).
- Possible follow-up (separate PR, if wanted): have the script itself refuse
  a NOTES_REMOTE the user doesn't own, since it's zero-config `origin`.
