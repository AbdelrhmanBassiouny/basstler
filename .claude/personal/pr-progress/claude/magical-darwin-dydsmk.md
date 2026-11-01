## Plan
- Shared branch writer; publication command (site workflow, hub, dispatch workflow, copyable user steps, re-check).
- check-setup plan_site row; /setup-personal-notes step 8.
- stack-board#8 replaces board.yml with the caller (supersedes stack-board#7).
- Browser re-check of blocking PRs' draft state: awaiting owner's call (needs a JS test dependency).

## Done
- All of the above except the browser re-check; 1779 tests pass; PR #105 description current, release:minor.

## Next
- Owner: decide the browser re-check (this PR, follow-up item, or drop).
- After release: run the publication command once on this clone to commit the dispatch workflow; store PLAN_SITE_TOKEN; merge stack-board#8, close #7.
- Follow-up: pass the token into plan-site-build.yml for private repositories.
