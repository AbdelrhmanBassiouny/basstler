PR #191 (draft) - one branch per upstream-reviews Action request.

Plan:
- Stop concurrent Action reads cancelling each other (exit 12 from maintenance).

Done:
- Per-request branches, no concurrency group, run commits in Python, trailer-marked pruning.
- Review round 1 (1d21d74): timedelta, required remote, RemoteBranch writes JSON values, test fixes; 5 threads resolved.

Next:
- Reviewer to decide: Path keys for branch files (this PR or separate); structured run-listing test double (separate PR / issue?).
