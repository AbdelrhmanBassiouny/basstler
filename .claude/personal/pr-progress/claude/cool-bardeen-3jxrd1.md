PR #77 - plan stack-maintenance / item stack-state-from-github (auto mode). Draft, release:minor.

Plan:
- in-review from the open upstream PR (board export, no label fallback); pass syncs the label.
- check_state: RollupState on the board from fork head checks; promotion withholds failure/error.

Done:
- Implemented and pushed (430ffde): board/UpstreamReviews/CommitChecks, GitHubRepository.check_state, review_label.py, status/next/summary output, skill + docs. 24 new tests; full suite = main's 14 env failures only.

Next:
- Owner review. Open question: a cloud pass now needs the upstream attached (add_repo) or the export stops (403) - by design per #15 thread.
- After merge: resolve the three #15 threads (r4368830083, r4368930418, r4368930516).
