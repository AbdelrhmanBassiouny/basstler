Plan (review-triage/mechanical-file-triage, draft #213; follow-up draft #214):
- #213: extensible basstler-review-triage distribution, CI summary, mark-viewed
- #214: keyword-argument judgment (signature-checked) and module-move rename source

Done:
- #213: judgments, change kinds, rename sources, outputs; open PRs triaged
- #214: tree matcher with rules and findings, callee resolutions, definition records;
  CRAM #967 115/154 mechanical in 12 s, 93 MB; 60 triage tests, full suite green

Next:
- User runs `basstler review-triage mark-viewed 210` locally (cloud refuses GraphQL)
- Possible: resolve calls on typed attributes (self.x.m()) to clear more of CRAM's 39
