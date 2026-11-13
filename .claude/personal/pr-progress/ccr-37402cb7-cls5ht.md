Plan (review-triage/mechanical-file-triage):
- Classifier, rename detection, PR reader, Markdown report, mark-viewed command
- Tests on tests/dataset/review-triage snippets; report step in tests.yml lint job
- Draft PR labelled release:minor

Done:
- review-triage plan saved; src/basstler/review_triage written; ruff clean
- Smoke-tested report on #154 and on rename commit 16050031 (all 3 files mechanical)
- Dataset snippets written

Next:
- Snippets lack `from __future__ import annotations` (ruff I002); user declined the bulk rewrite - waiting on how to handle
- Write tests, CI step, format via pre-commit hook, commit, push, draft PR
