PR: https://github.com/AbdelrhmanBassiouny/basstler/pull/72 (stack-maintenance / shared-fork-base-fast-forward)

Plan
- ForkBaseFastForward in maintenance/fast_forward.py: fetch fork base (--no-write-fetch-head), compare, refuse non-ff, push, re-fetch
- RefusedPushHandling param: pass raises, session start reports
- DefaultBranchSync uses it; ForkPublication replaced by FastForwardOutcome | None (+PUSH_REFUSED)
- commit_or_none / branch fetch move onto GitCommandRunner

Done
- bootstrap commit, draft PR, manifest in progress

Next
- failing tests first (diverged fork at session start), then implement
