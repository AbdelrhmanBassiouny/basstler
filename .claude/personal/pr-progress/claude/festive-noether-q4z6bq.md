Plan (PR #79, item stack-maintenance/landed-predicate-once):
- merged_predicate: one `git for-each-ref --merged` → set membership; Stack.build contract unchanged.

Done:
- Tests (tests/stack/test_landed_predicate.py) and implementation pushed (9a0f0f3); full suite green.
- GIT_TRACE2: 30 branches, 70 merge-base → 1 for-each-ref; numbers in PR description.

Next:
- Author review of draft PR #79; mark ready when satisfied.
