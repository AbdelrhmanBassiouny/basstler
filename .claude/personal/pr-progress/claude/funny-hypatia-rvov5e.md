## Plan
- Failing test: save with notes remote in a separate repository, origin naming the plan's repository
- Validate default_repository against the clone's origin, fail closed on an origin naming no repository
- Rename --notes-remote-url / notes_repository to --origin-url / checkout_repository
- Update plan-create checklist and plan-schema.md

## Done
- Branch, draft PR #169, item recorded in progress

## Next
- Ask the owner before rewriting the tests that encode the notes-remote comparison
