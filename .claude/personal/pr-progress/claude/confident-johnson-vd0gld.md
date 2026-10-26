PR #78 - plan stack-maintenance, item promotion-summaries-and-table (auto mode).

Plan:
- PromotionSummary/PromotionSummaries (points + optional title, from_json) in maintenance/promotion.py
- --summaries <path> on promote and run-report; prefill = bullets + "Full detail" link
- delete PullRequestDescription.summary (first-paragraph derivation) and its tests
- SKILL.md step 2: session writes summaries for `basstler.stack next` branches first

Done:
- branch, draft PR, manifest open/record

Next:
- failing tests for summary rendering and title override, then implementation
