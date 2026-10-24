basstler#16 (workflow-cutover / routine-cutover), review resolved 2026-10-24.

**Plan**
- The caller is event-only (opened/ready_for_review/closed + dispatch) and calls @main with basstler_branch_or_tag, the same as the upstream-reviews caller.
- The branch-based basstler/stack-maintenance caller for mirror forks: proposed as its own item, waiting on the owner.

**Done**
- Merged main (#56, tag-only release). CheckoutLocation and VersionReference are gone.
- b8cda95 fixed 9 of the 12 review threads: workflow comments, renamed input, @main, MaintenanceReport/ReparentResolution as classes, MaintenanceReportKey, tests/workflow_document.py, enum literals. 1153 tests pass.

**Next**
- Owner answers on the open threads: the branch caller (SETUP.md), PullRequestActivity, and the suite-wide literal sweep.
- Add the release:minor label (not set by this session).
- One green run from a real caller, then delete the live Routine.
