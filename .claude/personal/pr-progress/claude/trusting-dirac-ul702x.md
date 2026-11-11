## Plan
- Private-repository check runs before the missing-site-repository return; create step carries the public-site warning

## Done
- Failing tests added, then fixed in `PlanSitePublication.publish` (a8da357)
- Full suite green apart from 10 Playwright tests (local Chromium/Playwright version mismatch); ruff, format, code-rules pass
- PR #193 description updated; still draft, labelled `bug`

## Next
- Wait for CI and review on PR #193
