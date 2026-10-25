PR: https://github.com/AbdelrhmanBassiouny/basstler/pull/72 (stack-maintenance / shared-fork-base-fast-forward)

Plan
- ForkBaseFastForward shared by the pass (RAISED) and session start (REPORTED)

Done
- ForkBaseFastForward + RefusedPushHandling in maintenance/fast_forward.py; PUSH_REFUSED outcome
- GitCommandRunner.fetch_branch / commit_or_none; ForkPublication removed
- tests: diverged fork at session start, refused push raises in pass; suite green (1341)

Next
- CI green on cad412e (main merged, bash -c test fix ported); waiting on review
