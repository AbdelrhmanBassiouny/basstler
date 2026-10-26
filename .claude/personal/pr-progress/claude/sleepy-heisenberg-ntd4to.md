PR AbdelrhmanBassiouny/basstler#80, plan item stack-maintenance/pass-commit-graph (rescoped:
a commit-graph is ignored in shallow clones, so batch the ancestry calls instead).

Plan
- `LandedBranches` snapshot: one `for-each-ref --merged` call answers every landed question.

Done
- Tests, implementation (`stack/checkout.py`, `Stack.load`), full suite green (1554).
- GIT_TRACE2 profile in the PR: 266 merge-base calls -> 1 for-each-ref.

Next
- Review. A real CRAM run-report would confirm the 60 ms/call extrapolation.
- PR #79 (landed-predicate-once) should build on `LandedBranches`.
