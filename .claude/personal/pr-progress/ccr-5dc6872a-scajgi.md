PR #191 (draft) - one branch per upstream-reviews Action request.

Plan:
- Stop concurrent Action reads cancelling each other (exit 12 from maintenance).

Done:
- Each request on basstler/upstream-reviews-requests/<id>; result committed there; session deletes it.
- Concurrency group removed; run commits in Python instead of a rebase loop.
- Runs prune request branches over an hour old, only those whose Basstler-request trailer names the branch.
- Tests, ruff, code-rules green (plan_site Playwright errors pre-exist on main).

Next:
- Await review / CI.
