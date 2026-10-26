PR AbdelrhmanBassiouny/basstler#80, plan item stack-maintenance/pass-commit-graph (rescoped:
a commit-graph is ignored in shallow clones, so batch the ancestry calls instead).

Plan
- One `for-each-ref --merged=<upstream>` call answers every landed-branch question in
  `basstler.stack.checkout`; re-run only when the upstream or a fork ref moves.
- Tests against a real scratch repository first.
- GIT_TRACE2 profile before/after on a synthetic stack; numbers into the PR.

Done
- Branch, draft PR, manifest status recorded.

Next
- Failing tests, then the implementation, then the profile.
