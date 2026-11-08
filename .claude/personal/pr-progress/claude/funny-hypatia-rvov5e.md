## Plan
- Validate default_repository against the checkout's origin, failing closed (done)

## Done
- Failing test reproducing #153, then the fix: origin replaces the notes remote in the check
- Renamed --notes-remote-url/notes_repository to --origin-url/checkout_repository; docs updated
- #138's tests moved to the origin contract (owner-approved); suite green apart from 4 Playwright errors from the environment
- Reproduction and fix posted on #153; PR #169 labelled bug, still a draft

## Next
- Owner review of #169
- Owner to place the plan-site private-repository token problem from #153's comments
