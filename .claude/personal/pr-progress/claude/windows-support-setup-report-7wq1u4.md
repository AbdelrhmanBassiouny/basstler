Plan:
- Strict check-setup.sh report parsing: CheckSetupFailedError (status, stderr, missing checks, unreadable rows); setup exits 5
Done:
- Tests first, then the fix, pushed in 7024e83; draft PR #202 labelled bug, description current
- check-setup.sh now prints plan_site_access when the notes branch is missing
Next:
- Wait for CI and review; the plan-site Playwright tests only ran in CI
