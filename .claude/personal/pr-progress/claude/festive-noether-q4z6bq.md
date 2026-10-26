Plan (PR #79, item stack-maintenance/landed-predicate-once):
- Tests: merged_predicate answers landed/unlanded/missing-ref/slash names, and is a snapshot.
- merged_predicate: one `git for-each-ref --merged` → set membership; Stack.build contract unchanged.
- Measure stack derivations with GIT_TRACE2 before/after; numbers in the PR.

Done:
- Bootstrap: branch, draft PR #79, manifest in progress.

Next:
- Write the failing tests in tests/stack/.
