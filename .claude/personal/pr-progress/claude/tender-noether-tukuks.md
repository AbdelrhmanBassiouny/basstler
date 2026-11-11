## Plan
- Cards carry the items they count (status, built live state, pull request)
- Stage table derived from `Item` rules, passed through `LiveStateDisplay`
- Shared live-state script; hub script lists each repository's pulls (state=all, 100/page)
- Script rewrites marked count spans and bar widths only; refusal keeps the build
- Browser tests for hub and repository index first, plus a stage-table unit test

## Done
- Branch, draft PR #199, item recorded in progress

## Next
- Write the failing browser tests
