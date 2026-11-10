PR #191 (draft) - one branch per upstream-reviews Action request.

Plan:
- Stop concurrent Action reads cancelling each other (exit 12 from maintenance).

Done:
- Per-request branches, no concurrency group, run commits in Python, trailer-marked pruning.
- Review rounds 1-2 (1d21d74, bfe7516): timedelta, required remote, RemoteBranch writes dicts and ValidatedJSONModel, test fixes.
- Follow-up plan items recorded: basstler-reliability/action-exchange-models, structured-run-listing-requests.

Next:
- Two threads left open on purpose (read.py:98, test_action listing) until those follow-ups land; await review.
