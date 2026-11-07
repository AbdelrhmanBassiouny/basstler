PR: https://github.com/AbdelrhmanBassiouny/basstler/pull/156 (draft, release:minor)

Plan
- Parts 1 and 3 of the main-red plan from #155's review: an issue while main's tests fail, and a session-start line.

Done
- main-failure.yml + basstler.main_failure (MainFailureTracker, FinishedRun, Verdict) on shared github/issue.py and github/workflow_run.py models.
- Session-start "main tests:" line.
- Review round 1 (14da2b1c): 7 threads resolved; agent rules PAYLOAD_KEYS_ONLY_IN_THE_MODEL and ASSOCIATE_OR_SUBCLASS_FIRST added.

Next
- Open threads: StrEnum rule (asks whether to clean up the other key enums in their own PR); MainFailureTracker vs Issue shape.
- CI on 14da2b1c not yet read.
- Part 2 (sub-issue of a bug-fixes plan) waits for #144.
