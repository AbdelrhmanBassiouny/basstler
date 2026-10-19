basstler#16 (workflow-cutover / routine-cutover), resolved 2026-10-19.

**Plan**
- The caller is event-only (opened/ready_for_review/closed + dispatch), with no schedule (owner's call).
- The CRAM caller lands with basstler-package's cram-uses-basstler-plugin.
- The release rewrites the ref of every example caller.

**Done**
- Merged main (v0.1.2).
- Shipped docs/examples/stack-maintenance.yml. CheckoutLocation.example_callers() feeds VersionReference.every(). Tests are in (913 pass).
- Recorded the plans (workflow-cutover, basstler-package) and two roadmap rules.

**Next**
- Owner review of #16, then merge (the release bumps both example refs).
- cram-uses-basstler-plugin adds the CRAM caller, then one green run, then delete the live Routine.
- Mark CRAM actions-budget's stack-maintenance-event-only as folded into #16. It lives on CRAM's notes; this session has read-only access there.
