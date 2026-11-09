<!-- BEGIN-PR-PROGRESS -->
Plan
- #141 (base main; #140 merged): live pull request states in the browser, plan created/modified/refreshed times, merge workflow on every PR state change.
Done
- 2026-11-09 resolve: main conflicted in tests/plan_site/test_hub.py (imports only); kept PlanHistory and main's PlanSiteSecret (6ad86d6). The stack pass then merged #172 cleanly (5018d58).
- At 5018d58: full suite 2435 passed, 1 skipped (browser tests included), ruff and code-rules clean, merge probe CLEAN against main 48ca1ab. CI on 5018d58 still running at the time of the resolve.
Next
- User review of #141; it stays a draft.
<!-- END-PR-PROGRESS -->
