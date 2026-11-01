## Plan
- Failing test: default ActionRead raises ActionRunNotStarted after 20 s when no run appears.
- Lower ActionRead.start_allowance default from 60 to 20.

## Done
- Branch and draft PR #103 opened.

## Next
- Write the failing test, then the fix; run the upstream_reviews tests.
