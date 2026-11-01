## Plan
- Generalize RemoteBranch into a shared branch writer (any branch, any remote).
- Site repository caller workflow template (workflow_dispatch -> plan-site-build.yml).
- Notes-branch dispatch workflow template (push -> gh workflow run with PAT secret).
- basstler.plan_site.publication: push both, register hub, print copyable lines for the rest, re-check on rerun.
- /setup-personal-notes step; stack-board PR replacing board.yml with the caller.
- Page re-checks blocking PRs' draft state from the browser.

## Done
- Branch + draft PR #105 opened; item recorded in progress.

## Next
- Step 1: shared branch writer, tests first.
