## Plan
- Fix #152: the plan site build reads private repositories through an optional PLAN_SITE_READ_TOKEN; publication checks every repository the build reads and says so before writing.

## Done
- Build secret, publication check, step text, corrections and skill docs (3f859ad); review comment's four gaps answered (gap 3 is item unreadable-repository-items).
- Resolve read at 3f859ad: CI green (ruff, pytest 3.12/3.13, Actions usage), merge probe CLEAN against main 8681585, no review threads, no new comments. No separate upstream is configured, so upstream reviews do not apply.

## Next
- Owner review; PR stays draft.
